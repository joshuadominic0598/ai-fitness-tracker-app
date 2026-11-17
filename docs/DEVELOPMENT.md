# Running and contributing

The app serves a browser interface on `http://127.0.0.1:8877`. It runs on Python 3.10+; the optional agent uses a local Ollama installation and an installed Qwen model. No hosted model provider or API key is supported.

## Start from a fresh clone

```sh
git clone https://github.com/joshuadominic0598/ai-fitness-tracker-app.git
cd ai-fitness-tracker-app
python3 scripts/start.py
```

`start.py` creates `.venv-agent` and installs the project dependencies on first use. On Windows, use `py -3 scripts/start.py`. The Mac and Windows launchers call the same bootstrap. Python, Git and Ollama are installed separately; the bootstrap does not change system settings or download the Qwen model automatically.

Open Ollama and run `ollama pull qwen3:8b` for coaching. If Ollama isn't running, start the Ollama desktop app or run `ollama serve`. The app accepts only loopback Ollama addresses and local Qwen models. Qwen3 8B is the default; a smaller installed Qwen model can be selected in Settings on a computer with less memory. There is no automatic model or remote fallback.

To install directly instead:

```sh
python3 -m venv .venv-agent
.venv-agent/bin/python -m pip install -e '.[dev]'
.venv-agent/bin/python launch.py --open
```

Use `.venv-agent\Scripts\python.exe` on Windows. For an isolated sample journal, append `--demo`. For isolated development or tests, pass `--data-dir /path/to/temporary/journal --port 8890`. Never point synthetic tests at a personal journal.

## Voice input

Record or upload audio in the AI coach composer, including when opened from Track → Log using AI. The transcript is appended to the current message, remains editable, and is never sent automatically. Existing text and edits made during transcription are preserved. Stop or cancel audio before sending; leaving the screen or starting a new chat discards any late result.

Speech recognition uses [faster-whisper](https://github.com/SYSTRAN/faster-whisper), with multilingual Whisper `base` on the CPU in INT8 mode. It is installed by the normal bootstrap. There is no API key, cloud inference, browser speech service, GPU requirement or separate FFmpeg installation. Qwen remains the coaching agent.

The first transcription downloads the speech model from Hugging Face; the interface explains this wait. Later launches try the local model cache first, so cached transcription works offline. A failed download leaves the typed message unchanged and can be retried. Model weights use the standard Hugging Face cache outside the repository.

Clips are limited to 2 minutes and 8 MB. Microphone recording requires browser permission; upload works without microphone access. WAV, MP3, M4A, OGG, WebM, FLAC and other formats supported by bundled PyAV can be decoded. Long audio is rejected before model inference, including compressed files. Recordings and decoded samples stay in memory during processing; they are not written to journal storage or sent to Ollama. Cancel discards the client result; a transcription already running on the local server may finish before another can start.

The token-protected `/api/transcribe` endpoint only returns transcript text and model/language metadata. Unit and HTTP tests check bounds, errors, cache loading, concurrent work and journal isolation; JavaScript tests cover recording, permission denial, cancellation and editable insertion. A real-model smoke test requires the downloaded weights and is separate from CI.

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
