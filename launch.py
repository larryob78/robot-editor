#!/usr/bin/env python3
"""Developer convenience script to launch backend and frontend together."""

from __future__ import annotations

import argparse
import os
import signal
import subprocess
import sys
import time
from pathlib import Path
import shutil
from typing import Iterable, List

ROOT = Path(__file__).resolve().parent
BACKEND_DIR = ROOT / "backend"
FRONTEND_DIR = ROOT / "frontend"
DEFAULT_VENV = ROOT / ".lumina-venv"


class LaunchError(RuntimeError):
    """Raised when a setup step fails and the launch should abort."""


def require_tool(tool: str) -> str:
    path = shutil.which(tool)
    if path:
        return path
    raise LaunchError(f"Required tool `{tool}` not found on PATH")


def run(cmd: Iterable[str], *, cwd: Path | None = None, env: dict[str, str] | None = None) -> None:
    cmd_list: List[str] = list(cmd)
    display_cwd = cwd or ROOT
    print(f"\n$ {' '.join(cmd_list)} (cwd={display_cwd})")
    try:
        subprocess.run(cmd_list, cwd=cwd, env=env, check=True)
    except subprocess.CalledProcessError as exc:  # pragma: no cover - interactive helper
        raise LaunchError(f"Command failed: {' '.join(cmd_list)}") from exc


def ensure_virtualenv(venv_dir: Path) -> Path:
    if sys.platform == "win32":
        python_bin = venv_dir / "Scripts" / "python.exe"
    else:
        python_bin = venv_dir / "bin" / "python"

    if not python_bin.exists():
        print(f"Creating virtual environment at {venv_dir}...")
        run([sys.executable, "-m", "venv", str(venv_dir)])
    return python_bin


def install_backend_deps(python_bin: Path) -> None:
    pip_bin = python_bin.with_name("pip.exe" if sys.platform == "win32" else "pip")
    requirements = BACKEND_DIR / "requirements.txt"
    if not requirements.exists():
        raise LaunchError("backend/requirements.txt is missing")
    print("Installing backend dependencies (if needed)...")
    try:
        run([str(pip_bin), "install", "-r", str(requirements)])
    except LaunchError as exc:
        hint = (
            "Failed to install backend dependencies. Ensure you have network access or "
            "install them manually inside the virtual environment."
        )
        raise LaunchError(f"{exc}\n{hint}")


def ensure_frontend_deps(skip_install: bool) -> None:
    node_modules = FRONTEND_DIR / "node_modules"
    if node_modules.exists():
        return
    npm_bin = require_tool("npm")
    if skip_install:
        print("Warning: frontend dependencies not installed. Run `npm install` inside frontend/.")
        return
    print("Installing frontend dependencies (npm install)...")
    try:
        run([npm_bin, "install"], cwd=FRONTEND_DIR)
    except LaunchError as exc:
        hint = (
            "Failed to install frontend dependencies. Verify npm connectivity or rerun "
            "this script with --skip-install after installing manually."
        )
        raise LaunchError(f"{exc}\n{hint}")


def start_processes(backend_python: Path, *, backend_port: int, frontend_port: int) -> None:
    processes: list[subprocess.Popen[str]] = []

    def terminate_processes(*_args) -> None:
        print("\nShutting down...")
        for proc in processes:
            if proc.poll() is None:
                proc.terminate()
        for proc in processes:
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()

    signal.signal(signal.SIGINT, terminate_processes)
    signal.signal(signal.SIGTERM, terminate_processes)

    backend_env = os.environ.copy()
    backend_env["PATH"] = str(backend_python.parent) + os.pathsep + backend_env.get("PATH", "")
    backend_cmd = [
        str(backend_python),
        "-m",
        "uvicorn",
        "backend.app:app",
        "--reload",
        "--port",
        str(backend_port),
        "--host",
        "0.0.0.0",
    ]
    print("Starting backend server...")
    backend_proc = subprocess.Popen(backend_cmd, cwd=ROOT, env=backend_env)
    processes.append(backend_proc)

    frontend_env = os.environ.copy()
    npm_bin = require_tool("npm")
    frontend_cmd = [
        npm_bin,
        "run",
        "dev",
        "--",
        "--host",
        "0.0.0.0",
        "--port",
        str(frontend_port),
    ]
    print("Starting frontend dev server...")
    frontend_proc = subprocess.Popen(frontend_cmd, cwd=FRONTEND_DIR, env=frontend_env)
    processes.append(frontend_proc)

    try:
        while all(proc.poll() is None for proc in processes):
            time.sleep(0.5)
    finally:
        terminate_processes()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Launch LuminaCut backend and frontend together")
    parser.add_argument("--backend-port", type=int, default=8000, help="Port for the FastAPI server")
    parser.add_argument("--frontend-port", type=int, default=5173, help="Port for the Vite dev server")
    parser.add_argument(
        "--skip-install",
        action="store_true",
        help="Skip dependency installation checks (assume pip/npm already ran)",
    )
    parser.add_argument(
        "--venv",
        type=Path,
        default=DEFAULT_VENV,
        help="Path to the Python virtual environment used for the backend",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    try:
        backend_python = ensure_virtualenv(args.venv)
        if not args.skip_install:
            install_backend_deps(backend_python)
            ensure_frontend_deps(skip_install=False)
        else:
            ensure_frontend_deps(skip_install=True)
        start_processes(backend_python, backend_port=args.backend_port, frontend_port=args.frontend_port)
    except LaunchError as exc:
        print(f"ERROR: {exc}")
        sys.exit(1)


if __name__ == "__main__":
    main()
