"""Lightweight request/response models used by the backend server."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List


@dataclass
class OperationModel:
    """Serialized representation of a video editing operation."""

    type: str
    description: str
    params: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ProjectModel:
    id: str
    name: str
    original_path: str
    current_path: str
    preview_path: str | None
    status: str
    operations: List[OperationModel] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class InstructionRequest:
    prompt: str
    preview: bool = True

    @classmethod
    def from_json(cls, data: Dict[str, Any]) -> "InstructionRequest":
        prompt = str(data.get("prompt", "")).strip()
        preview = bool(data.get("preview", True))
        if not prompt:
            raise ValueError("Instruction prompt cannot be empty")
        return cls(prompt=prompt, preview=preview)


@dataclass
class ExportRequest:
    format: str = "mp4"

    @classmethod
    def from_json(cls, data: Dict[str, Any]) -> "ExportRequest":
        fmt = str(data.get("format", "mp4")).lower()
        if fmt not in {"mp4", "mov"}:
            raise ValueError("format must be either 'mp4' or 'mov'")
        return cls(format=fmt)
