from __future__ import annotations

import json
from types import SimpleNamespace

from api import cron


class DummyRequest:
    def __init__(self, headers: dict[str, str] | None = None):
        self.headers = headers or {}


def test_cron_rejects_invalid_secret(monkeypatch):
    monkeypatch.setattr(cron, "get_settings", lambda: SimpleNamespace(cron_secret="secret", log_level="INFO"))
    body, status, _headers = cron.handler(DummyRequest(headers={"authorization": "Bearer wrong"}))
    payload = json.loads(body)
    assert status == 401
    assert payload["ok"] is False


def test_cron_runs_once(monkeypatch):
    monkeypatch.setattr(cron, "get_settings", lambda: SimpleNamespace(cron_secret="secret", log_level="INFO"))
    async def fake_run_once():
        return {
            "ok": True,
            "scanned_sources": 1,
            "discovered_count": 2,
            "relevant_count": 1,
            "published_count": 1,
            "error_count": 0,
            "notes": [],
        }
    monkeypatch.setattr(
        cron,
        "_run_once",
        fake_run_once,
    )
    body, status, _headers = cron.handler(DummyRequest(headers={"authorization": "Bearer secret"}))
    payload = json.loads(body)
    assert status == 200
    assert payload["ok"] is True
