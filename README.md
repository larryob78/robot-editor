# LuminaCut AI

LuminaCut AI is an autonomous, natural-language-driven video editing environment. Upload footage, describe your edits in plain English, and review the simulated changes instantly – all without third-party Python packages. The backend is a lightweight HTTP server powered by the Python standard library, and the frontend is a static HTML/CSS/JS experience served from the same process.

## Features

- **Agentic natural language editing** – heuristically interprets prompts (trim, speed, brightness, volume, highlight) and records the resulting operations.
- **Format-agnostic ingest & export** – accepts any browser-supported video upload and returns the untouched source as MP4 or MOV exports.
- **Instant preview refresh** – previews mirror the current clip and are regenerated after each instruction for rapid feedback.
- **Operation timeline** – transparent list of every AI-authored transformation with human-friendly descriptions.
- **Zero-install dependencies** – everything runs on the Python standard library, making it ideal for offline or firewalled environments.

## Project structure

```
backend/      Minimal HTTP API, project state manager, and instruction parser
frontend/     Static HTML/CSS/JS UI served directly by the backend
launch.py     Helper script that provisions a venv and runs the backend
```

## Getting started

### Quick launch

Use the helper script to create an isolated virtual environment and start the backend:

```bash
python launch.py
```

By default the server binds to `0.0.0.0:8000`. Pass `--host` or `--backend-port` to customise the bind address, or `--skip-install` if you do not want the script to run `pip install -r backend/requirements.txt`.

### Manual launch

```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r backend/requirements.txt
python -m backend.server --host 0.0.0.0 --port 8000
```

Open `http://localhost:8000` in your browser to access the UI. Uploaded files, project metadata, previews, and exports are stored under `backend/data/`.

## Example workflow

1. Upload a video file from your machine.
2. Submit an instruction such as “Trim to the first 20 seconds and increase the volume by 15%”.
3. Wait for the job to complete; the preview refreshes automatically once processing finishes.
4. Review the operation history to confirm what the AI agent applied.
5. Export the clip as MP4 or MOV.

## Notes

- The offline build simulates edits by recording operations and refreshing previews/exports. Extend `backend/video_processing.py` to integrate real processing libraries if you have external dependencies available.
- Projects are stored on disk inside `backend/data/projects/`. Remove the folder to reset the environment.
