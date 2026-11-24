# Running and contributing

The app serves a browser interface on `http://127.0.0.1:8877`. It runs on Python 3.10+; the optional agent uses a local Ollama installation and an installed Qwen model. No hosted model provider or API key is supported.

## Start from a fresh clone

```sh
git clone https://github.com/joshuadominic0598/ai-fitness-tracker-app.git
cd ai-fitness-tracker-app
python3 scripts/start.py
```

`start.py` creates `.venv-agent` and installs the project dependencies on first use. On Windows, use `py -3 scripts/start.py`. The Mac and Windows launchers call the same bootstrap. Python, Git and Ollama are installed separately; the bootstrap does not change system settings or download the Qwen model automatically.

Open Ollama and run `ollama pull qwen3:8b` for coaching and `ollama pull embeddinggemma` for local semantic retrieval. If Ollama isn't running, start the Ollama desktop app or run `ollama serve`. The app accepts only loopback Ollama addresses and local Qwen models. Qwen3 8B is the default; a smaller installed Qwen model can be selected in Settings on a computer with less memory. There is no automatic model or remote fallback.

To install directly instead:

```sh
python3 -m venv .venv-agent
.venv-agent/bin/python -m pip install -e '.[dev]'
.venv-agent/bin/python launch.py --open
```

Use `.venv-agent\Scripts\python.exe` on Windows. For an isolated sample journal, append `--demo`. For isolated development or tests, pass `--data-dir /path/to/temporary/journal --port 8890`. Never point synthetic tests at a personal journal.

## Home workouts

Named section headings have information icons supplied by `web/section-info.js`. Hover the heading, focus the icon, or tap it to read the explanation; Escape or an outside click dismisses it. Explanations are positioned within the viewport and reattach when a panel is redrawn. Longer home-workout help is shown there instead of repeating it inside the card.

Home strength sessions use the `home_workout` entry kind with the same exercise/set validation as gym `workout` records. Each save creates a separate home session unless an existing home entry ID is explicitly edited. Several home sessions can share a date with each other and with a gym workout; they never participate in the gym-only daily consolidation or proposal replacement. Cross-category edits between gym/home sessions are rejected. Cardio exercises must be logged through the separate cardio tracker.

Both strength categories feed body-map emphasis/calibration, set volume, exercise history, search of tracked movements, frequency, personal records and strength trends. Gym day counts, weekly gym goals and gym consistency continue to use only `workout` records. The training heatmap shows home-only days in their own color. AI home logging retains its category through clarification, preview, correction and approval. A shorthand such as “10 pushups and 20 situps” retains both exercises.

## Cardio and food calories

Track separates strength training (`workout` records) from cardio (`cardio` records). Cardio logs store an activity from the grouped sports/aerobic list, minutes, and the user's overall felt intensity (`moderate` or `high`). They never add strength-training days, sets, muscle-map volume or personal records.

Set goals includes a weekly cardio target with moderate and high-intensity minutes. Both fields add to a single flexible target: `moderate + 2 × high`, in moderate-equivalent minutes. Logged sessions use the same conversion, so either intensity can substitute for the other. Actual minutes remain visible separately. Targets default to off (both zero); the adult 150/75-minute guideline is a linked reference. Weeks run Monday–Sunday, include today, and exclude future records. The cardio calendar shows cumulative weekly goal credit. This goal is separate from the existing six consistency scores.

Meals can store `calories` in kcal at meal and item level, independently of protein grams. Calories are optional in manual meal forms; a blank value stays unknown. AI meal previews still estimate calories alongside protein. Totals identify missing calorie entries; the completed-day average stays unavailable when any meal in that window has unknown calories. New AI previews store a short meal/day description, total protein, a protein range containing the main value, and total kcal. Qwen estimates whole-meal totals directly; ingredient arrays, arithmetic expressions and calculator agreement are not required. Unknown portions use plausible assumptions and a wider range. Range order and boundary values are normalized without rejecting the estimate; missing required totals receive one completion attempt. Historical item breakdowns remain readable, but new AI estimates discard them. No historical calories are fabricated, and no energy expenditure or calorie target is inferred from cardio.

## Voice input

Select the microphone icon beside Send in the AI coach composer, including when opened from Track → Log using AI. The transcript is appended to the current message, remains editable, and is never sent automatically. Existing text and edits made during transcription are preserved. Select the stop icon to transcribe, or cancel audio before sending; leaving the screen or starting a new chat discards any late result.

Speech recognition uses [faster-whisper](https://github.com/SYSTRAN/faster-whisper), with multilingual Whisper `base` on the CPU in INT8 mode. It is installed by the normal bootstrap. There is no API key, cloud inference, browser speech service, GPU requirement or separate FFmpeg installation. Qwen remains the coaching agent.

The first transcription downloads the speech model from Hugging Face; the interface explains this wait. Later launches try the local model cache first, so cached transcription works offline. A failed download leaves the typed message unchanged and can be retried. Model weights use the standard Hugging Face cache outside the repository.

Recordings are limited to 2 minutes and 8 MB. Microphone recording requires browser permission. There is no file-upload control. The browser chooses a supported recording format, such as WebM/Opus or MP4, which bundled PyAV decodes locally. Long audio is rejected before model inference, including compressed files. Recordings and decoded samples stay in memory during processing; they are not written to journal storage or sent to Ollama. Cancel discards the client result; a transcription already running on the local server may finish before another can start.

The token-protected `/api/transcribe` endpoint only returns transcript text and model/language metadata. Unit and HTTP tests check bounds, errors, cache loading, concurrent work and journal isolation; JavaScript tests cover recording, permission denial, cancellation and editable insertion. A real-model smoke test requires the downloaded weights and is separate from CI.

## Local data and backups

Personal records, settings, conversations and pending approvals live in `data/`, which is ignored by Git. Demo mode uses `.demo/`. A fresh clone creates its own empty journal. Settings → Export journal backup exports records, goals, conversations (including archived chats) and pending previews. JSON import is not implemented. For a complete restorable backup, stop the app, copy the whole `data/` folder, and restore it while the server is stopped.

A new chat archives earlier messages and excludes them from model history. Previous pending previews remain accessible in Track. Approving a newer workout retires older workout-only proposals for that same day; proposals for other dates, plans and mixed log batches are kept. Startup also repairs older journals that retained these superseded workout proposals. Saving a workout updates that date while preserving other exercises unless explicitly edited. Nothing the agent proposes is saved before approval.

Earlier provider settings are migrated to the local configuration: unsupported provider options and credentials are removed from `connections.json`. The default is Qwen3 8B. Public Research remains opt-in and uses public queries with external search/Europe PMC; ordinary inference uses only local Ollama.

## Checks

```sh
.venv-agent/bin/python -m pip install -e '.[dev]'
.venv-agent/bin/ruff check src tests scripts launch.py
.venv-agent/bin/ruff format --check src tests scripts launch.py
.venv-agent/bin/python -m unittest discover -s tests -v
node --check src/fitness_tracker/web/app.js
```

Run each `tests/test_*.cjs` file with Node 22+ as well. CI runs Python 3.10 and 3.12 on macOS and Linux. The macOS jobs use the standard `macos-15-intel` runners to avoid the capacity constraints affecting hosted Apple Silicon runners; both Python versions run the full suite. Tests use isolated journals and mocked model responses; live Qwen checks are separate and require Ollama. No keys, databases, local environments or generated test output belong in commits.

## Structure

- `src/fitness_tracker/store.py`: validation, SQLite records and approval transactions.
- `coach.py`, `local_model.py`: Qwen configuration, chat and loopback model transport.
- `agent_graph.py`, `agent_tools.py`, `coach_skills/`: optional research and bounded tool use.
- `workout_notes.py`, `exercise_matching.py`, `workout_preview.py`: source quantities, library matching, batching and partial previews.
- `web/`: browser interface, charts, date controls and workout editing.
- `scripts/start.py`: portable first-run setup and launcher.

See [Coach workflow](COACH_WORKFLOW.md) for pending-task state, local retrieval, context boundaries and streamed responses.

Exercise pickers and the personal-record filter use `/api/exercise-search` for ranked local vector and fuzzy keyword matches. The endpoint accepts `q`, `limit` (1–100), `tracked=1`, and `body_part`; it returns exercise IDs with scores. Keyword results remain available if local embeddings are unavailable. New manual workouts start empty; recent-exercise buttons explicitly recall past sets, while search adds fresh, unfilled sets.
