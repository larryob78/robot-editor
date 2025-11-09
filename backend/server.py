"""Minimal HTTP server exposing the LuminaCut API without third-party deps."""

from __future__ import annotations

import argparse
import cgi
import json
import mimetypes
import os
import shutil
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Dict, Tuple
from urllib.parse import parse_qs, urlparse

from .models import ExportRequest, InstructionRequest
from .notifications import clear_slack, configure_slack, slack_status, test_slack_webhook
from .state import manager

ROOT = Path(__file__).resolve().parent.parent
FRONTEND_DIR = ROOT / "frontend"
STATIC_DIR = Path(__file__).resolve().parent / "data"
STATIC_DIR.mkdir(parents=True, exist_ok=True)


def _public_url(path: str | Path | None) -> str | None:
    if not path:
        return None
    candidate = Path(path)
    if not candidate.exists():
        return None
    try:
        relative = candidate.resolve().relative_to(STATIC_DIR.resolve())
    except ValueError:
        return None
    return f"/static/{relative.as_posix()}"


def _serialize_project(project) -> Dict[str, Any]:
    data = project.to_dict()
    data.update(
        {
            "preview_url": _public_url(project.preview_path),
            "current_url": _public_url(project.current_path),
            "original_url": _public_url(project.original_path),
        }
    )
    return data


class LuminaCutHandler(BaseHTTPRequestHandler):
    server_version = "LuminaCutHTTP/0.1"

    def log_message(self, format: str, *args: Any) -> None:  # noqa: A003 - stdlib signature
        # Quieter logging to keep launch output tidy
        return

    # ------------------------------------------------------------------
    def _set_common_headers(self, status: HTTPStatus = HTTPStatus.OK, *, content_type: str = "application/json") -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET,POST,OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")

    def _write_json(self, payload: Dict[str, Any], status: HTTPStatus = HTTPStatus.OK) -> None:
        body = json.dumps(payload).encode("utf-8")
        self._set_common_headers(status)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _serve_file(self, path: Path) -> None:
        if not path.exists() or not path.is_file():
            self.send_error(HTTPStatus.NOT_FOUND, "File not found")
            return
        content_type, _ = mimetypes.guess_type(str(path))
        with path.open("rb") as fp:
            data = fp.read()
        self._set_common_headers(HTTPStatus.OK, content_type=content_type or "application/octet-stream")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _parse_json_body(self) -> Dict[str, Any]:
        length = int(self.headers.get("Content-Length", "0"))
        data = self.rfile.read(length) if length else b""
        if not data:
            return {}
        try:
            return json.loads(data.decode("utf-8"))
        except json.JSONDecodeError:
            self.send_error(HTTPStatus.BAD_REQUEST, "Invalid JSON payload")
            raise

    def _split_path(self) -> Tuple[str, ...]:
        parsed = urlparse(self.path)
        return tuple(part for part in parsed.path.split("/") if part)

    # ------------------------------------------------------------------
    def do_OPTIONS(self) -> None:  # noqa: N802 - stdlib signature
        self._set_common_headers()
        self.end_headers()

    # ------------------------------------------------------------------
    def do_GET(self) -> None:  # noqa: N802 - stdlib signature
        parsed = urlparse(self.path)
        path = parsed.path

        if path in {"/", "/index.html"}:
            index_path = FRONTEND_DIR / "index.html"
            if index_path.exists():
                self._serve_file(index_path)
            else:
                self.send_error(HTTPStatus.NOT_FOUND, "Frontend not found")
            return

        if path.startswith("/assets/") or path.endswith((".js", ".css")):
            asset_path = (FRONTEND_DIR / path.lstrip("/")).resolve()
            if FRONTEND_DIR.resolve() not in asset_path.parents and asset_path != FRONTEND_DIR.resolve():
                self.send_error(HTTPStatus.NOT_FOUND, "Invalid asset path")
                return
            self._serve_file(asset_path)
            return

        if path.startswith("/static/"):
            static_path = STATIC_DIR / path[len("/static/"):]
            self._serve_file(static_path)
            return

        if path == "/health":
            self._write_json({"status": "ok"})
            return

        parts = self._split_path()
        if parts[:3] == ("api", "integrations", "slack") and len(parts) == 3:
            self._write_json({"slack": slack_status()})
            return
        if parts[:2] == ("api", "projects") and len(parts) == 2:
            projects = manager.list_projects()
            payload = {"projects": [_serialize_project(project) for project in projects]}
            self._write_json(payload)
            return

        if parts[:2] == ("api", "projects") and len(parts) == 3:
            project = manager.get_project(parts[2])
            if not project:
                self.send_error(HTTPStatus.NOT_FOUND, "Project not found")
                return
            self._write_json({"project": _serialize_project(project)})
            return

        if parts[:3] == ("api", "projects",) and len(parts) == 4 and parts[3] == "preview":
            project = manager.get_project(parts[2])
            if not project:
                self.send_error(HTTPStatus.NOT_FOUND, "Project not found")
                return
            if not project.preview_path.exists():
                self.send_error(HTTPStatus.NOT_FOUND, "Preview not available")
                return
            self._serve_file(project.preview_path)
            return

        if parts[:2] == ("api", "jobs") and len(parts) == 3:
            status = manager.job_status(parts[2])
            self._write_json(status)
            return

        if parts[:3] == ("api", "projects",) and len(parts) == 4 and parts[3] == "export":
            project = manager.get_project(parts[2])
            if not project:
                self.send_error(HTTPStatus.NOT_FOUND, "Project not found")
                return
            query = parse_qs(parsed.query)
            fmt = query.get("format", ["mp4"])[0]
            request = ExportRequest.from_json({"format": fmt})
            target = manager.export_project(parts[2], request)
            self._serve_file(target)
            return

        self.send_error(HTTPStatus.NOT_FOUND, "Unknown endpoint")

    # ------------------------------------------------------------------
    def do_POST(self) -> None:  # noqa: N802 - stdlib signature
        parts = self._split_path()

        if parts[:3] == ("api", "integrations", "slack") and len(parts) == 3:
            try:
                data = self._parse_json_body()
            except json.JSONDecodeError:
                return
            action = data.get("action")
            if action == "test" and not data.get("webhook_url"):
                ok, message = test_slack_webhook()
                payload = {"slack": slack_status(), "message": message}
                status = HTTPStatus.OK if ok else HTTPStatus.BAD_REQUEST
                self._write_json(payload, status=status)
                return
            webhook_url = data.get("webhook_url")
            if not webhook_url:
                self.send_error(HTTPStatus.BAD_REQUEST, "webhook_url required")
                return
            test_flag = bool(data.get("test", True))
            try:
                message = configure_slack(str(webhook_url), test=test_flag)
            except ValueError as exc:
                self.send_error(HTTPStatus.BAD_REQUEST, str(exc))
                return
            payload = {"slack": slack_status(), "message": message}
            self._write_json(payload)
            return

        if parts[:2] == ("api", "projects") and len(parts) == 2:
            ctype, _ = cgi.parse_header(self.headers.get("Content-Type", ""))
            if ctype != "multipart/form-data":
                self.send_error(HTTPStatus.BAD_REQUEST, "Expected multipart form")
                return
            form = cgi.FieldStorage(  # type: ignore[arg-type]
                fp=self.rfile,
                headers=self.headers,
                environ={
                    "REQUEST_METHOD": "POST",
                    "CONTENT_TYPE": self.headers.get("Content-Type", ""),
                },
            )
            upload = form["file"] if "file" in form else None
            if not upload or not getattr(upload, "file", None):
                self.send_error(HTTPStatus.BAD_REQUEST, "File upload missing")
                return
            filename = getattr(upload, "filename", "upload.mp4")
            name_field = form.getfirst("name", "Untitled Project")
            uploads_dir = STATIC_DIR / "uploads"
            uploads_dir.mkdir(parents=True, exist_ok=True)
            temp_path = uploads_dir / filename
            with temp_path.open("wb") as dest:
                shutil.copyfileobj(upload.file, dest)
            project = manager.create_project(name_field, temp_path)
            self._write_json({"project": _serialize_project(project)}, status=HTTPStatus.CREATED)
            return

        if parts[:3] == ("api", "projects",) and len(parts) == 4 and parts[3] == "instructions":
            project_id = parts[2]
            try:
                data = self._parse_json_body()
                request = InstructionRequest.from_json(data)
            except Exception as exc:  # pragma: no cover - defensive
                self.send_error(HTTPStatus.BAD_REQUEST, str(exc))
                return
            if not os.getenv("OPENAI_API_KEY"):
                self.send_error(HTTPStatus.BAD_GATEWAY, "OPENAI_API_KEY is not configured on the server")
                return
            try:
                job = manager.submit_instruction(project_id, request)
            except KeyError:
                self.send_error(HTTPStatus.NOT_FOUND, "Project not found")
                return
            project = manager.get_project(project_id)
            payload = {"job": job, "project": _serialize_project(project) if project else None}
            self._write_json(payload, status=HTTPStatus.ACCEPTED)
            return

        if parts[:3] == ("api", "projects",) and len(parts) == 4 and parts[3] == "export":
            project_id = parts[2]
            try:
                data = self._parse_json_body()
                request = ExportRequest.from_json(data)
            except Exception as exc:
                self.send_error(HTTPStatus.BAD_REQUEST, str(exc))
                return
            try:
                target = manager.export_project(project_id, request)
            except KeyError:
                self.send_error(HTTPStatus.NOT_FOUND, "Project not found")
                return
            self._serve_file(target)
            return

        if parts[:3] == ("api", "integrations", "slack") and len(parts) == 3:
            clear_slack()
            payload = {"slack": slack_status(), "message": "Slack integration disconnected."}
            self._write_json(payload)
            return

        self.send_error(HTTPStatus.NOT_FOUND, "Unknown endpoint")


def serve(*, host: str, port: int) -> None:
    server_address = (host, port)
    httpd = ThreadingHTTPServer(server_address, LuminaCutHandler)
    print(f"LuminaCut server running at http://{host}:{port}")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        httpd.server_close()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Launch the LuminaCut backend server")
    parser.add_argument("--host", default="0.0.0.0", help="Host interface to bind")
    parser.add_argument("--port", type=int, default=8000, help="Port to listen on")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    serve(host=args.host, port=args.port)


if __name__ == "__main__":
    main()
