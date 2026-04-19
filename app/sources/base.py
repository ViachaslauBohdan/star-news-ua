from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

import requests
import structlog
from bs4 import BeautifulSoup
from tenacity import retry, stop_after_attempt, wait_exponential

from app.models import RawItem
from app.utils.text import compact_whitespace
from app.utils.urls import absolute_url

log = structlog.get_logger()


@dataclass(slots=True)
class SourceConfig:
    name: str
    base_url: str
    type: str = "html"
    selectors: dict[str, str] = field(default_factory=dict)
    extra: dict[str, Any] = field(default_factory=dict)


class BaseSource(ABC):
    def __init__(self, config: SourceConfig, timeout: int = 15, user_agent: str = "UAStarsMoneyBot/1.0"):
        self.config = config
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": user_agent})

    @abstractmethod
    def fetch_items(self) -> list[RawItem]:
        raise NotImplementedError

    @retry(wait=wait_exponential(multiplier=1, min=1, max=8), stop=stop_after_attempt(3))
    def get(self, url: str) -> requests.Response:
        response = self.session.get(url, timeout=self.timeout)
        response.raise_for_status()
        return response

    def soup(self, url: str | None = None) -> BeautifulSoup:
        response = self.get(url or self.config.base_url)
        return BeautifulSoup(response.text, "html.parser")

    def extract_text(self, node: Any, selector: str | None = None) -> str:
        if node is None:
            return ""
        selected = node.select_one(selector) if selector else node
        return compact_whitespace(selected.get_text(" ", strip=True)) if selected else ""

    def extract_href(self, node: Any, selector: str = "a") -> str:
        selected = node.select_one(selector)
        href = selected.get("href") if selected else None
        return absolute_url(self.config.base_url, href or "")

    def safe_fetch(self) -> list[RawItem]:
        try:
            return self.fetch_items()
        except Exception as exc:
            log.warning("source_fetch_failed", source=self.config.name, error=str(exc))
            return []

