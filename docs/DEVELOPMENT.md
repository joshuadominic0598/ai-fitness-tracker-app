# Running and contributing

The app serves a browser interface on `http://127.0.0.1:8877`. It runs on Python 3.10+; the optional agent uses a local Ollama installation and an installed Qwen model. No hosted model provider or API key is supported.

## Start from a fresh clone

```sh
git clone https://github.com/joshuadominic0598/ai-fitness-tracker-app.git
cd ai-fitness-tracker-app
python3 scripts/start.py
```

`start.py` creates `.venv-agent` and installs the project dependencies on first use. On Windows, use `py -3 scripts/start.py`. The Mac and Windows launchers call the same bootstrap. Python, Git and Ollama are installed separately; the bootstrap does not change system settings or download a model automatically.

Open Ollama and run `ollama pull qwen3:8b` for coaching. If Ollama isn't running, start the Ollama desktop app or run `ollama serve`. The app accepts only loopback Ollama addresses and local Qwen models. Qwen3 8B is the default; a smaller installed Qwen model can be selected in Settings on a computer with less memory. There is no automatic model or remote fallback.

To install directly instead:

```sh
python3 -m venv .venv-agent
.venv-agent/bin/python -m pip install -e '.[dev]'
.venv-agent/bin/python launch.py --open
```

Use `.venv-agent\Scripts\python.exe` on Windows. For an isolated sample journal, append `--demo`. For isolated development or tests, pass `--data-dir /path/to/temporary/journal --port 8890`. Never point synthetic tests at a personal journal.

## Local data and backups

Personal records, settings, conversations and pending approvals live in `data/`, which is ignored by Git. Demo mode uses `.demo/`. A fresh clone creates its own empty journal. Settings → Export journal backup exports records, goals, conversations (including archived chats) and pending previews. JSON import is not implemented. For a complete restorable backup, stop the app, copy the whole `data/` folder, and restore it while the server is stopped.

A new chat archives earlier messages and excludes them from model history. Previous pending previews remain accessible in Track. Saving a workout updates that date while preserving other exercises unless explicitly edited. Nothing the agent proposes is saved before approval.

Earlier provider settings are migrated to the local configuration: unsupported provider options and credentials are removed from `connections.json`. The default is Qwen3 8B. Public Research remains opt-in and uses public queries with external search/Europe PMC; ordinary inference uses only local Ollama.

## Checks

```sh
.venv-agent/bin/python -m pip install -e '.[dev]'
.venv-agent/bin/ruff check src tests scripts launch.py
.venv-agent/bin/ruff format --check src tests scripts launch.py
.venv-agent/bin/python -m unittest discover -s tests -v
node --check src/fitness_tracker/web/app.js
```

Run each `tests/test_*.cjs` file with Node 22+ as well. CI runs Python 3.10 and 3.12 on macOS and Linux. Tests use isolated journals and mocked model responses; live Qwen checks are separate and require Ollama. No keys, databases, local environments or generated test output belong in commits.

## Structure

- `src/fitness_tracker/store.py`: validation, SQLite records and approval transactions.
- `coach.py`, `local_model.py`: Qwen configuration, chat and loopback model transport.
- `agent_graph.py`, `agent_tools.py`, `coach_skills/`: optional research and bounded tool use.
- `workout_notes.py`, `exercise_matching.py`, `workout_preview.py`: source quantities, library matching, batching and partial previews.
- `web/`: browser interface, charts, date controls and workout editing.
- `scripts/start.py`: portable first-run setup and launcher.
