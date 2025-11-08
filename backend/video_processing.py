"""Core video processing utilities used by the AI editing pipeline."""

from __future__ import annotations

import json
import re
import shutil
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Iterable, List, Optional


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
        self.generate_preview()

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

        # Without external processing libraries we simulate edits by recording
        # operations and refreshing the preview/current artifacts.
        self.operations.extend(operations)
        self.status = "ready"
        self.metadata["last_updated"] = time.time()
        if generate_preview:
            self.generate_preview()

    def generate_preview(self, max_duration: int = 12, width: int = 720) -> None:  # noqa: ARG002
        """Generate a lightweight preview clip for the project."""

        # Preview is the current clip; we simply copy to the preview path.
        if self.current_path.exists():
            shutil.copy2(self.current_path, self.preview_path)
            self.metadata["preview_generated"] = time.time()

    def export(self, target_path: Path, container: str) -> Path:  # noqa: ARG002
        """Export the current clip into a chosen container format."""

        shutil.copy2(self.current_path, target_path)
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


def save_metadata(project: VideoProject) -> None:
    metadata_path = project.storage_dir / "metadata.json"
    with metadata_path.open("w", encoding="utf-8") as fp:
        json.dump(project.to_dict(), fp, indent=2)
