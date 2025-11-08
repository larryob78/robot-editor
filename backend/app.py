"""FastAPI application exposing the AI-assisted video editing backend."""

from __future__ import annotations

import shutil
import uuid
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .models import ExportRequest, InstructionRequest
from .state import manager


def _public_url(path: Path) -> str | None:
    try:
        relative = path.relative_to(STATIC_DIR)
    except ValueError:
        return None
    return f"/static/{relative.as_posix()}"


def _serialize_project(project) -> dict:
    data = project.to_dict()
    data.update(
        {
            "preview_url": _public_url(project.preview_path) if project.preview_path.exists() else None,
            "current_url": _public_url(project.current_path) if project.current_path.exists() else None,
            "original_url": _public_url(project.original_path)
            if Path(project.original_path).exists()
            else None,
        }
    )
    return data

app = FastAPI(
    title="LuminaCut AI",
    description="AI-assisted, natural-language-first video editing pipeline.",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

STATIC_DIR = Path(__file__).resolve().parent / "data"
STATIC_DIR.mkdir(parents=True, exist_ok=True)
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


@app.get("/health")
def healthcheck() -> dict:
    return {"status": "ok"}


@app.get("/api/projects")
def list_projects() -> dict:
    projects = manager.list_projects()
    return {"projects": [_serialize_project(project) for project in projects]}


@app.get("/api/projects/{project_id}")
def fetch_project(project_id: str) -> dict:
    project = manager.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    return {"project": _serialize_project(project)}


@app.post("/api/projects")
async def create_project(name: str = Form("Untitled Project"), file: UploadFile = File(...)) -> dict:
    uploads_dir = STATIC_DIR / "uploads"
    uploads_dir.mkdir(parents=True, exist_ok=True)
    file_extension = Path(file.filename).suffix or ".mp4"
    temp_path = uploads_dir / f"{uuid.uuid4().hex}{file_extension}"
    with temp_path.open("wb") as buffer:
        shutil.copyfileobj(file.file, buffer)
    project = manager.create_project(name, temp_path)
    return {"project": _serialize_project(project)}


@app.post("/api/projects/{project_id}/instructions")
async def apply_instruction(project_id: str, request: InstructionRequest) -> dict:
    try:
        job = manager.submit_instruction(project_id, request)
    except KeyError:
        raise HTTPException(status_code=404, detail="Project not found")
    project = manager.get_project(project_id)
    return {"job": job, "project": _serialize_project(project) if project else None}


@app.get("/api/jobs/{job_id}")
def job_status(job_id: str) -> dict:
    return manager.job_status(job_id)


@app.get("/api/projects/{project_id}/preview")
def project_preview(project_id: str) -> FileResponse:
    project = manager.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    if not project.preview_path.exists():
        raise HTTPException(status_code=404, detail="Preview not available yet")
    return FileResponse(str(project.preview_path), media_type="video/mp4")


@app.post("/api/projects/{project_id}/export")
def export_project(project_id: str, request: ExportRequest) -> FileResponse:
    try:
        target_path = manager.export_project(project_id, request)
    except KeyError:
        raise HTTPException(status_code=404, detail="Project not found")
    media_type = "video/mp4" if request.format == "mp4" else "video/quicktime"
    return FileResponse(str(target_path), media_type=media_type, filename=target_path.name)
