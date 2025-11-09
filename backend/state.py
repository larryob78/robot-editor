"""Application state management for video editing projects."""

from __future__ import annotations

import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Dict, List, Optional

from .ai import plan_edits
from .models import ExportRequest, InstructionRequest
from .notifications import notify_slack_async
from .video_processing import Operation, VideoProject, save_metadata


class ProjectManager:
    """In-memory registry of projects and asynchronous job manager."""

    def __init__(self, base_dir: Path):
        self.base_dir = base_dir
        self.projects: Dict[str, VideoProject] = {}
        self.jobs: Dict[str, Dict[str, Optional[str]]] = {}
        self.executor = ThreadPoolExecutor(max_workers=2)
        self.lock = threading.Lock()
        self.base_dir.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------
    def create_project(self, name: str, source_path: Path) -> VideoProject:
        project_id = uuid.uuid4().hex
        project_dir = self.base_dir / project_id
        project = VideoProject(project_id, name, project_dir, source_path)
        with self.lock:
            self.projects[project_id] = project
            save_metadata(project)
        notify_slack_async(f"New LuminaCut project '{project.name}' uploaded.")
        return project

    def list_projects(self) -> List[VideoProject]:
        with self.lock:
            return list(self.projects.values())

    def get_project(self, project_id: str) -> Optional[VideoProject]:
        with self.lock:
            return self.projects.get(project_id)

    # ------------------------------------------------------------------
    def submit_instruction(self, project_id: str, request: InstructionRequest) -> Dict[str, str]:
        project = self.get_project(project_id)
        if not project:
            raise KeyError(project_id)

        job_id = uuid.uuid4().hex
        with self.lock:
            self.jobs[job_id] = {"status": "queued", "prompt": request.prompt, "error": None}
            project.status = "queued"

        def task() -> None:
            with self.lock:
                job = self.jobs.get(job_id)
                if job:
                    job["status"] = "processing"
                project.status = "processing"
            try:
                metadata_payload = {
                    "duration": project.metadata.get("duration"),
                    "width": project.metadata.get("width"),
                    "height": project.metadata.get("height"),
                    "fps": project.metadata.get("fps"),
                }
                metadata_payload.update(request.metadata)
                planned_operations = plan_edits(request.prompt, metadata_payload)
                operations = [Operation.from_mapping(item) for item in planned_operations]
                project.apply_operations(operations, generate_preview=request.preview)
                with self.lock:
                    project.status = "ready"
                    job = self.jobs.get(job_id)
                    if job:
                        job["status"] = "completed"
                        job["error"] = None
                    save_metadata(project)
                op_count = len(operations)
                if op_count:
                    notify_slack_async(
                        "✅ LuminaCut applied instruction '",
                        f"{request.prompt}' to project '{project.name}'. ",
                        f"Recorded {op_count} operation{'s' if op_count != 1 else ''}.",
                    )
                else:
                    notify_slack_async(
                        "ℹ️ LuminaCut received instruction '",
                        f"{request.prompt}' for project '{project.name}', but no supported edits were generated.",
                    )
            except Exception as exc:  # pragma: no cover - defensive branch
                with self.lock:
                    project.status = "error"
                    job = self.jobs.get(job_id)
                    if job:
                        job["status"] = "failed"
                        job["error"] = str(exc)
                notify_slack_async(
                    "⚠️ LuminaCut failed to apply instruction '",
                    f"{request.prompt}' to project '{project.name}': {exc}"
                )

        self.executor.submit(task)
        return {"job_id": job_id}

    def job_status(self, job_id: str) -> Dict[str, Optional[str]]:
        with self.lock:
            return self.jobs.get(job_id, {"status": "unknown", "error": "Job not found"})

    def export_project(self, project_id: str, request: ExportRequest) -> Path:
        project = self.get_project(project_id)
        if not project:
            raise KeyError(project_id)
        export_dir = project.storage_dir / "exports"
        export_dir.mkdir(parents=True, exist_ok=True)
        file_name = f"{project.name.replace(' ', '_')}.{request.format}"
        target_path = export_dir / file_name
        project.export(target_path, request.format)
        save_metadata(project)
        notify_slack_async(
            f"📤 LuminaCut exported project '{project.name}' as {request.format.upper()}."
        )
        return target_path


# Shared singleton used by the application
PROJECT_DATA_DIR = Path(__file__).resolve().parent / "data" / "projects"
PROJECT_DATA_DIR.mkdir(parents=True, exist_ok=True)
manager = ProjectManager(PROJECT_DATA_DIR)
