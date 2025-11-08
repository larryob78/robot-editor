# LuminaCut AI

LuminaCut AI is an autonomous, natural-language-first video editing environment. Upload any major video format, describe your desired edits in plain English, and watch the AI agent transform your footage with live previews. The stack includes a FastAPI backend orchestrating moviepy-powered edits and a Vite + React front-end for a fluid editing experience.

## Features

- **Agentic natural language editing** – heuristically interprets prompts (trim, speed, brightness, volume, highlight) and applies them sequentially.
- **Multi-format ingest & export** – accepts MP4, MOV, AVI, MKV, and WEBM sources with MP4 or MOV export.
- **Live preview generation** – lightweight preview clips rendered after each instruction for near-real-time feedback.
- **Operation timeline** – transparent list of all AI-authored transformations and their parameters.
- **Modern interface** – minimal, responsive UI with contextual suggestions and export controls.

## Project structure

```
backend/      FastAPI application, state manager, and video processing utilities
frontend/     Vite + React client with hooks and UI components
```

## Getting started
### Quick launch

The repo ships with a helper script that provisions a Python virtual environment, installs backend/front-end dependencies, and starts both servers:

```bash
python launch.py
```

The script creates a virtual environment at `.lumina-venv/` and runs `uvicorn` on port 8000 plus the Vite dev server on port 5173. Pass `--skip-install` to skip dependency installation if you manage environments yourself, or `--backend-port` / `--frontend-port` to adjust ports.


### Backend

```bash
cd backend
python -m venv .venv
source .venv/bin/activate  # On Windows use `.venv\\Scripts\\activate`
pip install -r requirements.txt
uvicorn backend.app:app --reload
```

Videos, previews, and exports are stored under `backend/data/`. The API is served at `http://localhost:8000`.

### Frontend

```bash
cd frontend
npm install
npm run dev -- --host 0.0.0.0
```

The dev server proxies `/api` requests to the backend by default. Visit `http://localhost:5173` to launch the UI.

## Example workflow

1. Upload a video file (MP4, MOV, AVI, MKV, WEBM).
2. Type an instruction such as “Trim to the first 30 seconds and brighten the footage”.
3. Wait for the agent to process the job; a preview plays automatically when ready.
4. Inspect the **Agent reasoning** timeline to understand every applied operation.
5. Export the polished clip as MP4 or MOV.

## Notes

- MoviePy relies on ffmpeg. Ensure ffmpeg is available in your environment for rendering and export.
- Instruction parsing uses rule-based heuristics designed for common editing tasks. Extend `backend/video_processing.py` to support more advanced actions or LLM integrations.
