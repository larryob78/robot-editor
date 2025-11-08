"""Core video processing utilities used by the AI editing pipeline."""

from __future__ import annotations

import json
import math
import re
import shutil
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Iterable, List, Optional

from moviepy.editor import VideoFileClip, concatenate_videoclips, vfx


@dataclass
class Operation:
    """Internal representation of a single video editing step."""

    type: str
    description: str
    params: Dict[str, float] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, object]:
        return {
            "type": self.type,
            "description": self.description,
            "params": self.params,
        }


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
        self.metadata: Dict[str, object] = {}
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        if original_path != self.original_path:
            shutil.copy2(original_path, self.original_path)
        shutil.copy2(self.original_path, self.current_path)

    # --- Serialization helpers -------------------------------------------------
    def to_dict(self) -> Dict[str, object]:
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

    # --- Editing helpers -------------------------------------------------------
    def apply_operations(self, operations: Iterable[Operation], generate_preview: bool = True) -> None:
        """Apply a series of operations to the current video clip."""

        operations = list(operations)
        if not operations:
            return

        clip = VideoFileClip(str(self.current_path))
        try:
            for operation in operations:
                clip = _apply_operation(clip, operation)
            temp_path = self.storage_dir / f"temp_{uuid.uuid4().hex}.mp4"
            clip.write_videofile(
                str(temp_path),
                codec="libx264",
                audio_codec="aac",
                temp_audiofile=str(self.storage_dir / "temp-audio.m4a"),
                remove_temp=True,
                verbose=False,
                logger=None,
            )
            shutil.move(str(temp_path), self.current_path)
            if generate_preview:
                self.generate_preview()
            self.operations.extend(operations)
        finally:
            clip.close()

    def generate_preview(self, max_duration: int = 12, width: int = 720) -> None:
        """Generate a lightweight preview clip for the project."""

        clip = VideoFileClip(str(self.current_path))
        try:
            duration = min(max_duration, math.floor(clip.duration))
            preview_clip = clip.subclip(0, duration) if duration < clip.duration else clip
            preview_clip = preview_clip.resize(width=width)
            preview_clip.write_videofile(
                str(self.preview_path),
                codec="libx264",
                audio_codec="aac",
                temp_audiofile=str(self.storage_dir / "preview-audio.m4a"),
                remove_temp=True,
                verbose=False,
                logger=None,
            )
        finally:
            clip.close()

    def export(self, target_path: Path, container: str) -> Path:
        """Export the current clip into a chosen container format."""

        clip = VideoFileClip(str(self.current_path))
        try:
            codec = "libx264" if container == "mp4" else "mpeg4"
            audio_codec = "aac" if container == "mp4" else "aac"
            clip.write_videofile(
                str(target_path),
                codec=codec,
                audio_codec=audio_codec,
                temp_audiofile=str(self.storage_dir / "export-audio.m4a"),
                remove_temp=True,
                verbose=False,
                logger=None,
            )
        finally:
            clip.close()
        return target_path


# ----------------------------------------------------------------------------
# Natural language instruction parsing
# ----------------------------------------------------------------------------


def parse_instructions(prompt: str, clip_duration: Optional[float]) -> List[Operation]:
    """Translate a natural language prompt into concrete video operations."""

    prompt_normalized = prompt.strip().lower()
    operations: List[Operation] = []

    if not prompt_normalized:
        return operations

    duration = clip_duration or 0

    # Trim instructions --------------------------------------------------------
    trim_pattern = re.compile(r"trim (?:the )?(?:video )?(?:to|at) (?:(first|last) )?(\d+)(?:\s*(seconds|secs|s))")
    match = trim_pattern.search(prompt_normalized)
    if match:
        position, value, _ = match.groups()
        seconds = float(value)
        if position == "last" and duration:
            start_time = max(duration - seconds, 0)
            operations.append(
                Operation(
                    type="subclip",
                    description=f"Trim video to last {seconds:.0f} seconds",
                    params={"start": start_time, "end": duration},
                )
            )
        else:
            end_time = seconds if duration == 0 else min(seconds, duration)
            operations.append(
                Operation(
                    type="subclip",
                    description=f"Trim video to first {end_time:.0f} seconds",
                    params={"start": 0.0, "end": end_time},
                )
            )

    # Cut out silence or dead air
    if "remove silence" in prompt_normalized or "remove dead air" in prompt_normalized:
        operations.append(
            Operation(
                type="denoise",
                description="Reduce silence by normalizing audio",
                params={"volume": 1.3},
            )
        )

    # Speed adjustments --------------------------------------------------------
    speed_pattern = re.compile(r"(speed|slow) (?:it )?(?:down|up)?(?: by)? (\d+(?:\.\d+)?)x")
    match = speed_pattern.search(prompt_normalized)
    if match:
        verb, factor_text = match.groups()
        factor = float(factor_text)
        if "slow" in verb or "down" in prompt_normalized:
            factor = 1 / factor if factor != 0 else 1
            description = f"Slow video to {factor:.2f}x"
        else:
            description = f"Speed video to {factor:.2f}x"
        operations.append(Operation(type="speed", description=description, params={"factor": factor}))

    # Brightness adjustments ---------------------------------------------------
    if "brighten" in prompt_normalized or "increase brightness" in prompt_normalized:
        operations.append(
            Operation(type="brightness", description="Increase brightness", params={"factor": 1.2})
        )
    elif "darken" in prompt_normalized or "decrease brightness" in prompt_normalized:
        operations.append(
            Operation(type="brightness", description="Decrease brightness", params={"factor": 0.8})
        )

    # Volume adjustments -------------------------------------------------------
    volume_pattern = re.compile(r"(increase|decrease) volume(?: by)? (\d+)%")
    match = volume_pattern.search(prompt_normalized)
    if match:
        direction, amount = match.groups()
        amount_float = float(amount) / 100.0
        factor = 1 + amount_float if direction == "increase" else 1 - amount_float
        operations.append(
            Operation(
                type="volume",
                description=f"{direction.capitalize()} volume by {amount}%",
                params={"factor": factor},
            )
        )

    # Split and highlight moments
    highlight_pattern = re.compile(r"highlight (?:the )?(\d+)(?:st|nd|rd|th)? (?:segment|scene)")
    match = highlight_pattern.search(prompt_normalized)
    if match and duration:
        segment_index = int(match.group(1))
        segment_length = duration / 4
        start = max(segment_length * (segment_index - 1), 0)
        end = min(start + segment_length, duration)
        operations.append(
            Operation(
                type="highlight",
                description=f"Highlight segment {segment_index}",
                params={"start": start, "end": end},
            )
        )

    # Fallback operation captures the instruction text for auditing ------------
    if not operations:
        operations.append(Operation(type="note", description=prompt, params={}))

    return operations


# ----------------------------------------------------------------------------
# Low-level operation primitives
# ----------------------------------------------------------------------------


def _apply_operation(clip: VideoFileClip, operation: Operation) -> VideoFileClip:
    """Apply a low-level operation to a clip and return the resulting clip."""

    if operation.type == "subclip":
        start = operation.params.get("start", 0)
        end = operation.params.get("end", clip.duration)
        return clip.subclip(start, end)
    if operation.type == "speed":
        factor = operation.params.get("factor", 1.0)
        return clip.fx(vfx.speedx, factor)
    if operation.type == "brightness":
        factor = operation.params.get("factor", 1.0)
        return clip.fx(vfx.colorx, factor)
    if operation.type == "volume":
        factor = operation.params.get("factor", 1.0)
        return clip.volumex(factor)
    if operation.type == "highlight":
        start = operation.params.get("start", 0)
        end = operation.params.get("end", clip.duration)
        highlight_segment = clip.subclip(start, end).fx(vfx.colorx, 1.3)
        pre = clip.subclip(0, start) if start > 0 else None
        post = clip.subclip(end, clip.duration) if end < clip.duration else None
        clips: List[VideoFileClip] = []
        if pre:
            clips.append(pre)
        clips.append(highlight_segment)
        if post:
            clips.append(post)
        return concatenate_videoclips(clips)
    if operation.type == "denoise":
        volume = operation.params.get("volume", 1.0)
        return clip.volumex(volume)
    if operation.type == "note":
        return clip
    return clip


def save_metadata(project: VideoProject) -> None:
    metadata_path = project.storage_dir / "metadata.json"
    with metadata_path.open("w", encoding="utf-8") as fp:
        json.dump(project.to_dict(), fp, indent=2)
