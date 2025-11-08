from typing import List, Optional
from pydantic import BaseModel, Field


class OperationModel(BaseModel):
    """Serialized representation of a video editing operation."""

    type: str
    description: str
    params: dict


class ProjectModel(BaseModel):
    id: str
    name: str
    original_path: str
    current_path: str
    preview_path: Optional[str]
    status: str
    operations: List[OperationModel] = Field(default_factory=list)


class InstructionRequest(BaseModel):
    prompt: str = Field(..., description="Natural language instruction for the AI editor")
    preview: bool = Field(
        True,
        description="Whether to generate an optimized preview clip after the instruction is applied.",
    )


class ExportRequest(BaseModel):
    format: str = Field(
        "mp4",
        regex="^(mp4|mov)$",
        description="Desired output format for the exported video.",
    )
