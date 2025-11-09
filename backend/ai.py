"""Utilities for calling the OpenAI API to plan video edits."""

from __future__ import annotations

import json
import os
from typing import Any, Dict, List

import openai

SUPPORTED_OPERATIONS = {
    "subclip": {
        "description": "Keep a specific range of the clip.",
        "params": ["start", "end"],
    },
    "trim": {
        "description": "Alias for subclip instructions.",
        "params": ["start", "end"],
    },
    "split": {
        "description": "Split the clip into two segments at a timestamp.",
        "params": ["time"],
    },
    "brightness": {
        "description": "Adjust brightness using a factor between -0.5 and 0.5.",
        "params": ["adjustment"],
    },
    "volume": {
        "description": "Adjust volume with a linear factor (0.5-2.0).",
        "params": ["factor"],
    },
    "speed": {
        "description": "Change playback speed with a factor (0.5-2.0).",
        "params": ["factor"],
    },
}

_SYSTEM_PROMPT = """
You are the LuminaCut edit planner. You receive a JSON payload containing a
natural language instruction and metadata about the currently selected video
clip. Respond with JSON describing the precise editing steps to run. Only use
the operations that are explicitly provided to you. For every operation provide
a concise human readable description.

Return your response as JSON with the following structure:
{
  "operations": [
    {
      "type": "subclip" | "split" | "brightness" | "volume" | "speed",
      "description": "string",
      "params": { ... }
    }
  ]
}

Rules:
- If the instruction cannot be executed with the supported operations, return
  an empty operations array.
- For trim requests you may use either "subclip" or "trim" with "start" and
  "end" seconds.
- Never include explanatory text outside of the JSON structure.
""".strip()


def _validate_operation(raw: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(raw, dict):
        raise ValueError("Each operation must be an object")
    op_type = str(raw.get("type", "")).strip().lower()
    if not op_type:
        raise ValueError("Operation is missing a type")
    if op_type not in SUPPORTED_OPERATIONS:
        raise ValueError(f"Unsupported operation type '{op_type}'")
    description = str(raw.get("description", "")).strip()
    if not description:
        description = op_type
    params = raw.get("params", {}) or {}
    if not isinstance(params, dict):
        raise ValueError(f"Operation '{op_type}' params must be an object")

    validated: Dict[str, Any] = {
        "type": op_type,
        "description": description,
        "params": {},
    }
    spec = SUPPORTED_OPERATIONS[op_type]
    for key in spec["params"]:
        if key in params:
            validated["params"][key] = params[key]

    # Coerce numeric params to floats where possible
    for key, value in list(validated["params"].items()):
        if isinstance(value, (int, float, str)):
            try:
                validated["params"][key] = float(value)
            except (TypeError, ValueError):
                pass
    return validated


def plan_edits(prompt: str, metadata: Dict[str, Any], *, model: str | None = None) -> List[Dict[str, Any]]:
    """Call the OpenAI API to translate a prompt into structured operations."""

    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY environment variable is not set")

    openai.api_key = api_key
    chosen_model = model or os.getenv("LUMINACUT_MODEL", "gpt-4o-mini")

    payload = {
        "instruction": prompt,
        "metadata": metadata or {},
        "allowed_operations": {op: spec for op, spec in SUPPORTED_OPERATIONS.items()},
    }

    response = openai.ChatCompletion.create(
        model=chosen_model,
        temperature=0.2,
        messages=[
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": json.dumps(payload)},
        ],
    )

    message = response["choices"][0]["message"]["content"].strip()
    try:
        data = json.loads(message)
    except json.JSONDecodeError as exc:
        raise RuntimeError("Model response was not valid JSON") from exc

    operations = data.get("operations", [])
    if not isinstance(operations, list):
        raise RuntimeError("Model response did not include an operations list")

    validated = [_validate_operation(op) for op in operations]
    return validated
