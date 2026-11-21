"""Loopback-only HTTP API and static application host."""

import argparse
import json
import mimetypes
import secrets
import threading
import urllib.parse
import webbrowser
from datetime import date, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from .coach import Coach, Connections, research, videos
from .coach_skills import skill_catalog
from .store import CATALOG, Store, insights
from .transcription import LocalTranscriber

WEB = Path(__file__).parent / "web"


def seed_demo(store):
    with store.connect() as con:
        initialized = con.execute("SELECT 1 FROM settings WHERE key='demo_initialized'").fetchone()
    if initialized:
        return
    if store.entries():
        with store.connect() as con:
            con.execute("INSERT OR REPLACE INTO settings VALUES ('demo_initialized', 'true')")
        return
    store.save_profile(
        {
            "name": "Alex",
            "focus": "Build stronger arms and stay consistent",
            "experience": "intermediate",
            "protein_goal": 130,
        }
    )
    ids = [
        "Barbell_Bench_Press_-_Medium_Grip",
        "Barbell_Curl",
        "Barbell_Full_Squat",
        "Bent_Over_Barbell_Row",
        "Triceps_Pushdown",
        "Dumbbell_Alternate_Bicep_Curl",
    ]
    today = date.today()
    for ago in range(83, -1, -1):
        day = today - timedelta(days=ago)
        progress = (83 - ago) / 83
        if day.weekday() in (0, 2, 4):
            chosen = ids[:2] + [ids[4]] if day.weekday() == 0 else ids[2:4] + [ids[5]]
            store.save(
                "workout",
                {
                    "date": day.isoformat(),
                    "name": ["Upper body", "Lower & pull", "Full body"][day.weekday() // 2],
                    "duration": 45 + ago % 20,
                    "notes": "Illustrative demo session",
                    "exercises": [
                        {
                            "exercise_id": eid,
                            "sets": [
                                {
                                    "weight": round((25 + i * 10 + progress * 15) / 2.5) * 2.5,
                                    "reps": 8 + ago % 3,
                                }
                                for _ in range(3)
                            ],
                        }
                        for i, eid in enumerate(chosen)
                    ],
                },
            )
        if ago % 9 != 0:
            for description, protein in [
                ("Eggs, toast and yogurt", 28),
                ("Chicken, rice and vegetables", 42 + ago % 10),
                ("Paneer bowl and a protein shake", 38 + ago % 16),
            ]:
                store.save(
                    "meal",
                    {"date": day.isoformat(), "description": description, "protein": protein},
                )
        if ago % 7 != 0:
            store.save(
                "supplement",
                {"date": day.isoformat(), "name": "Creatine", "amount": 5, "unit": "g"},
            )
        if ago % 7 == 0:
            store.save(
                "body", {"date": day.isoformat(), "weight_kg": round(74 + progress * 1.7, 1)}
            )
    store.save(
        "plan",
        {
            "date": (today + timedelta(days=1)).isoformat(),
            "name": "Upper body · arm focus",
            "duration": 50,
            "notes": "Choose comfortable loads. Add reps before weight.",
            "exercises": [
                {"exercise_id": eid, "sets": [{"weight": 0, "reps": 10} for _ in range(3)]}
                for eid in ids[:2] + [ids[4]]
            ],
        },
    )
    with store.connect() as con:
        con.execute("INSERT OR REPLACE INTO settings VALUES ('demo_initialized', 'true')")


class AppServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, address, directory, demo=False):
        self.store = Store(directory)
        self.connections = Connections(self.store.directory)
        self.coach = Coach(self.store, self.connections)
        self.transcriber = LocalTranscriber()
        self.token = secrets.token_urlsafe(32)
        self.demo = demo
        if demo:
            seed_demo(self.store)
        super().__init__(address, Handler)
        self.store.recover_chat_requests()


class Handler(BaseHTTPRequestHandler):
    server_version = "FormAndFuel/1.0"

    def log_message(self, fmt, *args):
        # No request bodies, queries, credentials or user fitness text in access logs.
        pass

    def send(self, value, status=200, mime="application/json; charset=utf-8"):
        body = json.dumps(value).encode() if mime.startswith("application/json") else value
        try:
            self.send_response(status)
            self.send_header("Content-Type", mime)
            self.send_header("Content-Length", str(len(body)))
            self.send_header(
                "Cache-Control", "no-store" if mime.startswith("application/json") else "no-cache"
            )
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Referrer-Policy", "no-referrer")
            self.send_header(
                "Content-Security-Policy",
                "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; frame-src 'none'; connect-src 'self'; object-src 'none'; base-uri 'self'; frame-ancestors 'none'",
            )
            self.end_headers()
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError):
            # A page refresh does not cancel or duplicate the persisted coaching turn.
            pass

    def stream_chat(self, body):
        self.send_response(200)
        self.send_header("Content-Type", "application/x-ndjson; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Connection", "close")
        self.end_headers()
        self.close_connection = True

        write_lock = threading.Lock()

        def emit(event):
            try:
                with write_lock:
                    self.wfile.write((json.dumps(event) + "\n").encode())
                    self.wfile.flush()
            except (BrokenPipeError, ConnectionResetError):
                pass  # Persisted request IDs still prevent duplicate journal actions.

        emit({"type": "stage", "message": "Received. Understanding your request…"})
        try:
            result = self.server.coach.chat(
                body.get("message"),
                self.server.store.coach_consent()["accepted"],
                body.get("date"),
                body.get("request_id"),
                body.get("research", False),
                body.get("revise_draft_id"),
                body.get("logging_kind"),
                body.get("approve_draft_id"),
                progress=emit,
                edit_message_id=body.get("edit_message_id"),
            )
            emit({"type": "final", "response": result})
        except ValueError as error:
            emit({"type": "error", "message": str(error)})
        except Exception:
            emit(
                {
                    "type": "error",
                    "message": "The coach could not finish. Your request is retained; please retry.",
                }
            )

    def trusted_host(self):
        expected = f"127.0.0.1:{self.server.server_port}"
        return self.headers.get("Host") == expected

    def do_GET(self):
        if not self.trusted_host():
            return self.send({"error": "Use the 127.0.0.1 address shown by the launcher."}, 403)
        path = urllib.parse.urlsplit(self.path).path
        if path == "/api/health":
            return self.send({"app": "form-and-fuel", "demo": self.server.demo})
        if path == "/api/chat-state":
            return self.send(
                {
                    "messages": self.server.store.messages(),
                    "chat_hidden_drafts": self.server.store.chat_hidden_drafts(),
                    "drafts": self.server.store.drafts(),
                    "chat_status": {
                        "busy": self.server.coach.current_request is not None,
                        "request_id": self.server.coach.current_request,
                    },
                    "rate_limits": {},
                    "coach_consent": self.server.store.coach_consent(),
                }
            )
        if path == "/api/coach-status":
            return self.send({})
        if path == "/api/session":
            return self.send({"token": self.server.token})
        if path == "/api/state":
            s = self.server.store
            return self.send(
                {
                    "entries": s.entries(),
                    "profile": s.profile(),
                    "insights": insights(s.entries(), s.profile()),
                    "messages": s.messages(),
                    "chat_hidden_drafts": s.chat_hidden_drafts(),
                    "drafts": s.drafts(),
                    "connections": self.server.connections.public(),
                    "coach_consent": s.coach_consent(),
                    "chat_status": {
                        "busy": self.server.coach.current_request is not None,
                        "request_id": self.server.coach.current_request,
                    },
                    "token": self.server.token,
                    "demo": self.server.demo,
                    "today": date.today().isoformat(),
                }
            )
        if path == "/api/profile":
            return self.send(self.server.store.profile())
        if path == "/api/coach-skills":
            return self.send(skill_catalog())
        if path == "/api/exercise-search":
            params = urllib.parse.parse_qs(urllib.parse.urlsplit(self.path).query)
            query = params.get("q", [""])[0].strip()
            try:
                limit = int(params.get("limit", ["30"])[0])
                if len(query) > 200 or not 1 <= limit <= 100:
                    raise ValueError("Use a short exercise search and at most 100 results.")
                items = self.server.coach.retrieval.search_exercises(
                    query,
                    limit=limit,
                    tracked=params.get("tracked", ["0"])[0] == "1",
                    body_part=params.get("body_part", [""])[0],
                )
                return self.send({"query": query, "items": items})
            except ValueError as error:
                return self.send({"error": str(error)}, 400)
        if path == "/api/exercises":
            return self.send(CATALOG)
        if path == "/api/export":
            s = self.server.store
            return self.send(
                {
                    "app": "blaze-athletics",
                    "version": 1,
                    "profile": s.profile(),
                    "entries": s.entries(),
                    "messages": s.messages(include_archived=True),
                    "drafts": s.drafts(),
                }
            )
        relative = "index.html" if path == "/" else urllib.parse.unquote(path.lstrip("/"))
        target = (WEB / relative).resolve()
        if WEB.resolve() not in target.parents or not target.is_file():
            return self.send({"error": "Not found"}, 404)
        self.send(
            target.read_bytes(),
            mime=mimetypes.guess_type(str(target))[0] or "application/octet-stream",
        )

    def do_POST(self):
        expected = f"http://127.0.0.1:{self.server.server_port}"
        if not self.trusted_host() or self.headers.get("Origin", expected) != expected:
            return self.send({"error": "Request rejected. Use this app’s local address."}, 403)
        if self.headers.get("X-App-Token") != self.server.token:
            return self.send(
                {
                    "error": "Your app session has restarted. Reconnect and try again.",
                    "code": "session_expired",
                },
                403,
            )
        try:
            size = int(self.headers.get("Content-Length", "0"))
            path = urllib.parse.urlsplit(self.path).path
            if not 0 < size <= (12_100_000 if path == "/api/transcribe" else 2_000_000):
                raise ValueError("Request is empty or too large.")
            if self.headers.get_content_type() != "application/json":
                raise ValueError("Use application/json.")
            body = json.loads(self.rfile.read(size))
            if not isinstance(body, dict):
                raise ValueError("Request must be an object.")
            path = urllib.parse.urlsplit(self.path).path
            store = self.server.store
            if path == "/api/transcribe":
                result = self.server.transcriber.transcribe(body)
            elif path == "/api/new-chat":
                if not self.server.coach.lock.acquire(blocking=False):
                    raise ValueError("Wait for the coach to finish before starting a new chat.")
                try:
                    store.start_chat()
                finally:
                    self.server.coach.lock.release()
                result = {"ok": True}
            elif path == "/api/entry":
                result = store.save(body.get("kind"), body, body.get("id"))
            elif path == "/api/delete":
                store.delete(body.get("id"))
                result = {"ok": True}
            elif path == "/api/reset":
                if body.get("confirm") != "RESET":
                    raise ValueError("Type RESET to confirm clearing your journal.")
                if not self.server.coach.lock.acquire(blocking=False):
                    raise ValueError("Wait for the coach to finish before resetting the journal.")
                try:
                    store.reset()
                    if body.get("clear_connections") is True:
                        self.server.connections.clear()
                finally:
                    self.server.coach.lock.release()
                result = {"ok": True}
            elif path == "/api/supplements":
                result = store.add_supplement(body.get("name"))
            elif path == "/api/profile":
                result = store.save_profile(body)
            elif path == "/api/connections":
                result = self.server.connections.save(body)
            elif path == "/api/connection-test":
                result = self.server.coach.test_connection(body.get("provider"), body.get("model"))
            elif path == "/api/models":
                if body.get("provider", "ollama") != "ollama":
                    raise ValueError("Unknown provider.")
                result = {"models": self.server.connections.models(body["provider"])}
            elif path == "/api/coach-consent":
                if not self.server.coach.lock.acquire(blocking=False):
                    raise ValueError(
                        "Wait for the current answer before changing sharing permissions."
                    )
                try:
                    result = store.set_coach_consent(body.get("accepted"), body.get("version"))
                finally:
                    self.server.coach.lock.release()
            elif path == "/api/chat":
                if body.get("stream") is True:
                    return self.stream_chat(body)
                result = self.server.coach.chat(
                    body.get("message"),
                    store.coach_consent()["accepted"],
                    body.get("date"),
                    body.get("request_id"),
                    body.get("research", False),
                    body.get("revise_draft_id"),
                    body.get("logging_kind"),
                    body.get("approve_draft_id"),
                    edit_message_id=body.get("edit_message_id"),
                )
            elif path == "/api/draft-preview":
                result = store.preview(body.get("id"))
            elif path == "/api/approve":
                result = store.approve(body.get("id"), body.get("data"))
            elif path == "/api/dismiss":
                store.dismiss(body.get("id"))
                result = {"ok": True}
            elif path == "/api/research":
                result = {"papers": research(body.get("query"))}
            elif path == "/api/videos":
                result = videos(body.get("query"), self.server.connections)
            elif path == "/api/context":
                result = self.server.coach.context(body.get("date"))
            else:
                return self.send({"error": "Not found"}, 404)
            self.send(result)
        except (ValueError, json.JSONDecodeError) as error:
            self.send({"error": str(error)}, 400)
        except Exception:
            self.send(
                {
                    "error": "Something went wrong. Reload and try again; your saved data is retained."
                },
                500,
            )


def main():
    parser = argparse.ArgumentParser(description="Blaze Athletics — local fitness journal")
    parser.add_argument("--port", type=int, default=8877)
    parser.add_argument("--data-dir", type=Path)
    parser.add_argument(
        "--demo", action="store_true", help="Use a separate illustrative demo workspace"
    )
    parser.add_argument("--open", action="store_true", help="Open the browser")
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[2]
    default = root / "data" if (root / "launch.py").exists() else Path.home() / ".form-and-fuel"
    directory = args.data_dir or (default.parent / ".demo" if args.demo else default)
    server = None
    for port in range(args.port, args.port + 10):
        try:
            server = AppServer(("127.0.0.1", port), directory, args.demo)
            break
        except OSError:
            # Reuse only the same app and workspace mode, never some other service.
            try:
                from .coach import request_json

                health = request_json(f"http://127.0.0.1:{port}/api/health", timeout=1)
                if (
                    health.get("app") == "form-and-fuel"
                    and health.get("demo") == args.demo
                    and args.data_dir is None
                ):
                    if args.open:
                        webbrowser.open(f"http://127.0.0.1:{port}")
                    print(f"Blaze Athletics already running: http://127.0.0.1:{port}")
                    return
            except ValueError:
                pass
    if server is None:
        raise SystemExit("No available port. Choose another with --port.")
    server.coach.retrieval.start()
    url = f"http://127.0.0.1:{server.server_port}"
    print(f"Blaze Athletics: {url}\nWorkspace: {directory}\nPress Ctrl-C to stop.", flush=True)
    if args.open:
        threading.Timer(0.5, lambda: webbrowser.open(url)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.coach.retrieval.stop.set()
        server.server_close()


if __name__ == "__main__":
    main()
