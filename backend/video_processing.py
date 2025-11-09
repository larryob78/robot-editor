"""Core video processing utilities used by the AI editing pipeline."""

from __future__ import annotations

import json
import math
import os
import shutil
import subprocess
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

FFMPEG_BIN = os.getenv("FFMPEG_BIN", "ffmpeg")
FFPROBE_BIN = os.getenv("FFPROBE_BIN", "ffprobe")


class VideoProcessingError(RuntimeError):
    """Raised when an ffmpeg command fails."""


def _run_command(cmd: List[str]) -> None:
    try:
        subprocess.run(cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    except subprocess.CalledProcessError as exc:  # pragma: no cover - defensive logging
        raise VideoProcessingError(exc.stderr.decode("utf-8", "ignore")) from exc


def probe_media(path: Path) -> Dict[str, Any]:
    """Return media metadata using ffprobe."""

    if not path.exists():
        return {}

    cmd = [
        FFPROBE_BIN,
        "-v",
        "error",
        "-print_format",
        "json",
        "-show_streams",
        "-show_format",
        str(path),
    ]
    try:
        result = subprocess.run(cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    except subprocess.CalledProcessError:
        return {}
    try:
        payload = json.loads(result.stdout.decode("utf-8"))
    except json.JSONDecodeError:
        return {}

    metadata: Dict[str, Any] = {}
    if "format" in payload:
        fmt = payload["format"]
        duration = fmt.get("duration")
        if duration is not None:
            try:
                metadata["duration"] = float(duration)
            except (TypeError, ValueError):
                pass
    for stream in payload.get("streams", []):
        if stream.get("codec_type") == "video":
            width = stream.get("width")
            height = stream.get("height")
            if width:
                metadata["width"] = width
            if height:
                metadata["height"] = height
            r_frame_rate = stream.get("r_frame_rate")
            if r_frame_rate and r_frame_rate != "0/0":
                try:
                    num, den = r_frame_rate.split("/")
                    if float(den) != 0:
                        metadata["fps"] = float(num) / float(den)
                except Exception:  # pragma: no cover - parsing guard
                    pass
    return metadata


@dataclass
class Operation:
    """Internal representation of a single video editing step."""

    type: str
    description: str
    params: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_mapping(cls, data: Dict[str, Any]) -> "Operation":
        op_type = str(data.get("type", "")).strip()
        if not op_type:
            raise ValueError("operation missing type")
        description = str(data.get("description", op_type)).strip()
        params = data.get("params", {}) or {}
        if not isinstance(params, dict):
            raise ValueError("operation params must be a dictionary")
        return cls(type=op_type, description=description, params=dict(params))

    def to_dict(self) -> Dict[str, Any]:
        return {
            "type": self.type,
            "description": self.description,
            "params": self.params,
        }


def _temp_path(parent: Path, suffix: str = ".mp4") -> Path:
    handle = tempfile.NamedTemporaryFile(delete=False, suffix=suffix, dir=parent)
    tmp_path = Path(handle.name)
    handle.close()
    return tmp_path


def _apply_subclip(source: Path, dest: Path, start: float, end: Optional[float]) -> None:
    start = max(start, 0.0)
    cmd = [FFMPEG_BIN, "-y", "-i", str(source)]
    if start > 0:
        cmd.extend(["-ss", f"{start:.3f}"])
    if end is not None and end > start:
        duration = end - start if start > 0 else end
        cmd.extend(["-t", f"{duration:.3f}"])
    cmd.extend(["-c", "copy", str(dest)])
    _run_command(cmd)


def _apply_split(source: Path, dest: Path, split_time: float, duration: Optional[float]) -> Dict[str, Any]:
    split_time = max(split_time, 0.0)
    if duration is not None:
        split_time = min(split_time, duration)

    first = _temp_path(dest.parent, suffix="-part1.mp4")
    second = _temp_path(dest.parent, suffix="-part2.mp4")
    _apply_subclip(source, first, 0.0, split_time if split_time > 0 else None)
    if duration is not None and math.isclose(split_time, duration, abs_tol=0.01):
        # No second part if split at end
        shutil.copy2(first, dest)
        first.unlink(missing_ok=True)
        second.unlink(missing_ok=True)
        return {"segments": [{"start": 0.0, "end": split_time}]}
    _apply_subclip(source, second, split_time, None)

    concat_list = dest.parent / "concat.txt"
    with concat_list.open("w", encoding="utf-8") as fh:
        fh.write(f"file '{first.as_posix()}'\n")
        fh.write(f"file '{second.as_posix()}'\n")

    cmd = [
        FFMPEG_BIN,
        "-y",
        "-f",
        "concat",
        "-safe",
        "0",
        "-i",
        str(concat_list),
        "-c",
        "copy",
        str(dest),
    ]
    _run_command(cmd)
    concat_list.unlink(missing_ok=True)
    first.unlink(missing_ok=True)
    second.unlink(missing_ok=True)
    return {"segments": [{"start": 0.0, "end": split_time}, {"start": split_time, "end": duration}]}


def _apply_brightness(source: Path, dest: Path, adjustment: float) -> None:
    adjustment = max(min(adjustment, 0.5), -0.5)
    cmd = [
        FFMPEG_BIN,
        "-y",
        "-i",
        str(source),
        "-vf",
        f"eq=brightness={adjustment:.3f}",
        "-c:a",
        "copy",
        str(dest),
    ]
    _run_command(cmd)


def _apply_volume(source: Path, dest: Path, factor: float) -> None:
    factor = max(min(factor, 2.0), 0.5)
    cmd = [
        FFMPEG_BIN,
        "-y",
        "-i",
        str(source),
        "-af",
        f"volume={factor:.2f}",
        str(dest),
    ]
    try:
        _run_command(cmd)
    except VideoProcessingError:
        # Fall back to copying if the clip has no audio stream.
        shutil.copy2(source, dest)


def _apply_speed(source: Path, dest: Path, factor: float) -> None:
    factor = max(min(factor, 2.0), 0.5)
    atempo_chain: List[str] = []
    remaining = factor
    while remaining > 2.0:
        atempo_chain.append("atempo=2.0")
        remaining /= 2.0
    while remaining < 0.5:
        atempo_chain.append("atempo=0.5")
        remaining *= 2.0
    atempo_chain.append(f"atempo={remaining:.3f}")
    audio_filter = ",".join(atempo_chain)
    video_filter = f"setpts={1/factor:.3f}*PTS"

    cmd = [
        FFMPEG_BIN,
        "-y",
        "-i",
        str(source),
        "-filter_complex",
        f"[0:v]{video_filter}[v];[0:a]{audio_filter}[a]",
        "-map",
        "[v]",
        "-map",
        "[a]",
        str(dest),
    ]
    try:
        _run_command(cmd)
    except VideoProcessingError:
        # Retry without audio if the source clip does not include it.
        cmd = [
            FFMPEG_BIN,
            "-y",
            "-i",
            str(source),
            "-filter:v",
            video_filter,
            "-an",
            str(dest),
        ]
        _run_command(cmd)


class VideoProject:
    """Container object encapsulating a video project and its edit history."""

    def __init__(self, project_id: str, name: str, storage_dir: Path, original_path: Path):
        self.id = project_id
        self.name = name
        self.storage_dir = storage_dir
        original_extension = original_path.suffix or ".mp4"
        self.original_path = storage_dir / f"source{original_extension}"
        self.current_path = storage_dir / "current.mp4"
        self.preview_path = storage_dir / "preview.mp4"
        self.status = "idle"
        self.operations: List[Operation] = []
        self.metadata: Dict[str, Any] = {}
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        if original_path != self.original_path:
            shutil.copy2(original_path, self.original_path)
        shutil.copy2(self.original_path, self.current_path)
        self.refresh_metadata()
        self.generate_preview()

    # --- Serialization helpers -------------------------------------------------
    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "original_path": str(self.original_path),
            "current_path": str(self.current_path),
            "preview_path": str(self.preview_path) if self.preview_path.exists() else None,
            "status": self.status,
            "operations": [op.to_dict() for op in self.operations],
            "metadata": self.metadata,
        }

    # --- Metadata helpers ------------------------------------------------------
    def refresh_metadata(self) -> None:
        info = probe_media(self.current_path)
        self.metadata.update(info)
        self.metadata["last_updated"] = time.time()

    # --- Editing helpers -------------------------------------------------------
    def apply_operations(self, operations: Iterable[Operation], generate_preview: bool = True) -> None:
        operations = list(operations)
        if not operations:
            return

        working = self.current_path
        updated_segments: List[Dict[str, Any]] = []
        for operation in operations:
            temp_output = _temp_path(self.storage_dir)
            if operation.type in {"subclip", "trim"}:
                start = float(operation.params.get("start", 0.0))
                end = operation.params.get("end")
                end_value = float(end) if end is not None else None
                _apply_subclip(working, temp_output, start, end_value)
            elif operation.type == "split":
                split_time = float(operation.params.get("time", 0.0))
                metadata = _apply_split(working, temp_output, split_time, self.metadata.get("duration"))
                if metadata.get("segments"):
                    updated_segments = metadata["segments"]
            elif operation.type == "brightness":
                adjustment = float(operation.params.get("adjustment", 0.0))
                _apply_brightness(working, temp_output, adjustment)
            elif operation.type == "volume":
                factor = float(operation.params.get("factor", 1.0))
                _apply_volume(working, temp_output, factor)
            elif operation.type == "speed":
                factor = float(operation.params.get("factor", 1.0))
                _apply_speed(working, temp_output, factor)
            else:
                temp_output.unlink(missing_ok=True)
                raise ValueError(f"Unsupported operation: {operation.type}")

            shutil.move(temp_output, self.current_path)
            working = self.current_path
            self.operations.append(operation)

        if updated_segments:
            self.metadata["segments"] = updated_segments
        self.refresh_metadata()
        if generate_preview:
            self.generate_preview()
        self.status = "ready"

    def generate_preview(self, max_duration: int = 12, width: int = 720) -> None:
        if not self.current_path.exists():
            return
        cmd = [
            FFMPEG_BIN,
            "-y",
            "-i",
            str(self.current_path),
            "-vf",
            f"scale='min({width},iw)':-2",
            "-t",
            str(max_duration),
            "-an",
            str(self.preview_path),
        ]
        try:
            _run_command(cmd)
        except VideoProcessingError:
            shutil.copy2(self.current_path, self.preview_path)
        self.metadata["preview_generated"] = time.time()

    def export(self, target_path: Path, container: str) -> Path:  # noqa: ARG002
        target_path.parent.mkdir(parents=True, exist_ok=True)
        cmd = [FFMPEG_BIN, "-y", "-i", str(self.current_path), "-c", "copy", str(target_path)]
        try:
            _run_command(cmd)
        except VideoProcessingError:
            shutil.copy2(self.current_path, target_path)
        return target_path


def save_metadata(project: VideoProject) -> None:
    metadata_path = project.storage_dir / "metadata.json"
    with metadata_path.open("w", encoding="utf-8") as fp:
        json.dump(project.to_dict(), fp, indent=2)
