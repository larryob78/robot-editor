"""Slack integration utilities for LuminaCut."""

from __future__ import annotations

import json
import os
import threading
from datetime import datetime
from pathlib import Path
from typing import Dict, Optional, Tuple
from urllib import error, request

DATA_DIR = Path(__file__).resolve().parent / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)
SLACK_CONFIG_PATH = DATA_DIR / "slack.json"

_lock = threading.Lock()
_last_status: Dict[str, Optional[str]] = {"last_tested": None, "last_error": None}


def _load_file_config() -> Optional[str]:
    if not SLACK_CONFIG_PATH.exists():
        return None
    try:
        with SLACK_CONFIG_PATH.open("r", encoding="utf-8") as handle:
            payload = json.load(handle)
    except (json.JSONDecodeError, OSError):
        return None
    url = payload.get("webhook_url")
    if isinstance(url, str) and url.strip():
        return url.strip()
    return None


def _save_file_config(url: Optional[str]) -> None:
    with _lock:
        if not url:
            if SLACK_CONFIG_PATH.exists():
                SLACK_CONFIG_PATH.unlink()
            return
        SLACK_CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
        with SLACK_CONFIG_PATH.open("w", encoding="utf-8") as handle:
            json.dump({"webhook_url": url}, handle)


def _load_webhook() -> Tuple[Optional[str], Optional[str]]:
    env_value = os.getenv("SLACK_WEBHOOK_URL", "").strip()
    if env_value:
        return env_value, "env"
    file_value = _load_file_config()
    if file_value:
        return file_value, "file"
    return None, None


def _mask(url: str) -> str:
    if len(url) <= 16:
        return url
    return f"{url[:12]}…{url[-4:]}"


def _send_slack_message(webhook_url: str, text: str) -> Tuple[bool, Optional[str]]:
    payload = json.dumps({"text": text}).encode("utf-8")
    req = request.Request(
        webhook_url,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with request.urlopen(req, timeout=10) as resp:
            if 200 <= resp.status < 300:
                return True, None
            return False, f"Slack responded with status {resp.status}"
    except error.URLError as exc:
        return False, str(exc.reason or exc)


def slack_status() -> Dict[str, Optional[str]]:
    webhook, source = _load_webhook()
    status: Dict[str, Optional[str]] = {
        "connected": bool(webhook),
        "webhook_mask": _mask(webhook) if webhook else None,
        "source": source,
        "last_tested": _last_status.get("last_tested"),
        "last_error": _last_status.get("last_error"),
    }
    return status


def configure_slack(webhook_url: str, *, test: bool = True) -> str:
    url = (webhook_url or "").strip()
    if not url:
        raise ValueError("webhook_url cannot be empty")
    if "hooks.slack.com" not in url:
        raise ValueError("Provided URL does not appear to be a Slack webhook")

    if test:
        success, error_message = _send_slack_message(
            url,
            "LuminaCut connected successfully. You'll now receive project updates here.",
        )
        timestamp = datetime.utcnow().isoformat() + "Z"
        _last_status["last_tested"] = timestamp
        if not success:
            _last_status["last_error"] = error_message or "Unknown Slack error"
            raise ValueError(error_message or "Unable to reach Slack webhook")
        _last_status["last_error"] = None
    _save_file_config(url)
    return "Slack webhook saved."


def test_slack_webhook() -> Tuple[bool, str]:
    webhook, _ = _load_webhook()
    if not webhook:
        return False, "Slack webhook is not configured."
    success, error_message = _send_slack_message(
        webhook,
        "LuminaCut test notification: Slack connection verified.",
    )
    timestamp = datetime.utcnow().isoformat() + "Z"
    _last_status["last_tested"] = timestamp
    if success:
        _last_status["last_error"] = None
        return True, "Slack webhook test message delivered."
    _last_status["last_error"] = error_message or "Unknown Slack error"
    return False, _last_status["last_error"] or "Slack webhook test failed."


def clear_slack() -> None:
    _save_file_config(None)
    _last_status["last_error"] = None
    _last_status["last_tested"] = None


def notify_slack_async(message: str) -> None:
    webhook, _ = _load_webhook()
    if not webhook:
        return

    def _worker() -> None:
        success, error_message = _send_slack_message(webhook, message)
        if not success:
            _last_status["last_error"] = error_message or "Failed to post Slack notification"

    thread = threading.Thread(target=_worker, daemon=True)
    thread.start()
