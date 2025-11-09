# LuminaCut AI

LuminaCut AI is an autonomous, natural-language-driven video editing environment. Upload footage, describe your edits in plain English, and let the backend orchestrate OpenAI-powered edit plans that are executed with real `ffmpeg` transformations. The backend exposes a lightweight HTTP API and serves the static HTML/CSS/JS client from the same process.

## Features

- **Agentic OpenAI planning** – forwards every instruction (plus clip metadata) to the OpenAI API to obtain structured edit steps.
- **Real ffmpeg operations** – trim, split, brightness, volume, and speed adjustments are applied using `ffmpeg` so previews reflect the actual output.
- **Format-agnostic ingest & export** – accepts any browser-supported video upload and re-encodes to MP4 or MOV.
- **Instant preview refresh** – previews mirror the current clip and are regenerated after each instruction for rapid feedback.
- **Operation timeline** – transparent list of every AI-authored transformation with human-friendly descriptions.
- **Classic quick tools** – dedicated buttons for trimming the head or tail, isolating a range, or splitting at a timecode.
- **Slack notifications** – optional webhook integration to broadcast project updates to your team automatically.

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

> **Important:** LuminaCut requires the `OPENAI_API_KEY` environment variable at runtime. Export the key before launching:
> 
> ```bash
> export OPENAI_API_KEY=sk-...
> python launch.py
> ```
> 
> Optional overrides:
> 
> - `LUMINACUT_MODEL` – override the default `gpt-4o-mini` planning model.
> - `FFMPEG_BIN` / `FFPROBE_BIN` – point to custom ffmpeg binaries if they are not on `PATH`.

### Manual launch

```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r backend/requirements.txt
python -m backend.server --host 0.0.0.0 --port 8000
```

Open `http://localhost:8000` in your browser to access the UI. Uploaded files, project metadata, previews, and exports are stored under `backend/data/`.

Ensure `ffmpeg`/`ffprobe` are available on your system `PATH`. Most package managers (`brew install ffmpeg`, `apt install ffmpeg`, etc.) provide them.

### Optional Slack integration

Provide an incoming webhook URL to mirror LuminaCut activity into a Slack channel. You can either:

- Set the `SLACK_WEBHOOK_URL` environment variable before launching the server, **or**
- Use the **Slack integration** card in the UI to paste the webhook URL and run a connection test.

When connected, LuminaCut posts notifications for new uploads, instruction completions or failures, and exports.

## Example workflow

1. Upload a video file from your machine.
2. Submit an instruction such as “Trim to the first 20 seconds and increase the volume by 15%”.
3. Wait for the job to complete; the preview refreshes automatically once processing finishes.
4. Review the operation history to confirm what the AI agent applied.
5. Export the clip as MP4 or MOV.

## Notes

- LuminaCut stores projects on disk inside `backend/data/projects/`. Remove the folder to reset the environment.
- Slack notifications are optional; leave the webhook unset if you do not wish to broadcast events.
