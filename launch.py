#!/usr/bin/env python3
"""Developer convenience script to launch the LuminaCut server."""

from __future__ import annotations

import argparse
import os
import signal
import subprocess
import sys
import time
from pathlib import Path
from typing import Iterable, List

ROOT = Path(__file__).resolve().parent
BACKEND_DIR = ROOT / "backend"
DEFAULT_VENV = ROOT / ".lumina-venv"


class LaunchError(RuntimeError):
    """Raised when a setup step fails and the launch should abort."""


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
    print("Ensuring backend dependencies are available...")
    run([str(pip_bin), "install", "-r", str(requirements)])


def start_backend(backend_python: Path, *, backend_port: int, host: str) -> None:
    env = os.environ.copy()
    env["PATH"] = str(backend_python.parent) + os.pathsep + env.get("PATH", "")
    cmd = [
        str(backend_python),
        "-m",
        "backend.server",
        "--host",
        host,
        "--port",
        str(backend_port),
    ]
    print("Starting backend server...")
    process = subprocess.Popen(cmd, cwd=ROOT, env=env)

    def terminate_process(*_args) -> None:
        print("\nShutting down...")
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()

    signal.signal(signal.SIGINT, terminate_process)
    signal.signal(signal.SIGTERM, terminate_process)

    try:
        while process.poll() is None:
            time.sleep(0.5)
    finally:
        terminate_process()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Launch the LuminaCut backend server")
    parser.add_argument("--backend-port", type=int, default=8000, help="Port for the backend server")
    parser.add_argument("--host", default="0.0.0.0", help="Host interface to bind")
    parser.add_argument(
        "--skip-install",
        action="store_true",
        help="Skip dependency installation checks (virtualenv will still be created)",
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
        start_backend(backend_python, backend_port=args.backend_port, host=args.host)
    except LaunchError as exc:
        print(f"ERROR: {exc}")
        sys.exit(1)


if __name__ == "__main__":
    main()
