from __future__ import annotations

from abc import ABC, abstractmethod
import json
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

import requests
import structlog
from bs4 import BeautifulSoup
from tenacity import retry, stop_after_attempt, wait_exponential

from app.models import RawItem
from app.utils.dates import parse_date
from app.utils.text import compact_whitespace
from app.utils.urls import absolute_url, is_probable_image_url

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

    def soup_from_html(self, html: str) -> BeautifulSoup:
        return BeautifulSoup(html, "html.parser")

    def extract_text(self, node: Any, selector: str | None = None) -> str:
        if node is None:
            return ""
        selected = node.select_one(selector) if selector else node
        return compact_whitespace(selected.get_text(" ", strip=True)) if selected else ""

    def extract_href(self, node: Any, selector: str | None = "a") -> str:
        selected = node.select_one(selector) if selector else node
        href = selected.get("href") if selected else None
        return absolute_url(self.config.base_url, href or "")

    def extract_image_url(self, node: Any) -> str:
        if node is None:
            return ""
        for selector in ("img", "picture img", "[data-src]", "[data-lazy-src]", "[style]"):
            selected = node.select_one(selector) if selector != "[style]" else node
            if not selected:
                continue
            candidates = [
                selected.get("src"),
                selected.get("data-src"),
                selected.get("data-lazy-src"),
                selected.get("data-original"),
                selected.get("data-img"),
            ]
            srcset = selected.get("srcset") or selected.get("data-srcset")
            if srcset:
                candidates.extend(part.strip().split(" ")[0] for part in srcset.split(","))
            for candidate in candidates:
                image_url = absolute_url(self.config.base_url, candidate or "")
                if is_probable_image_url(image_url):
                    return image_url
        return ""

    def extract_meta_image_url(self, soup: BeautifulSoup, page_url: str | None = None) -> str:
        base_url = page_url or self.config.base_url
        candidates: list[str] = []
        meta_selectors = (
            'meta[property="og:image"]',
            'meta[property="og:image:secure_url"]',
            'meta[name="twitter:image"]',
            'meta[name="twitter:image:src"]',
            'meta[itemprop="image"]',
        )
        for selector in meta_selectors:
            selected = soup.select_one(selector)
            if selected:
                candidates.append(selected.get("content") or "")
        image_link = soup.select_one('link[rel="image_src"], link[as="image"]')
        if image_link:
            candidates.append(image_link.get("href") or "")
        for candidate in candidates:
            image_url = absolute_url(base_url, candidate.strip())
            if is_probable_image_url(image_url):
                return image_url
        return ""

    def extract_meta_published_at(self, soup: BeautifulSoup) -> datetime | None:
        meta_selectors = (
            'meta[property="article:published_time"]',
            'meta[property="og:article:published_time"]',
            'meta[name="pubdate"]',
            'meta[name="publishdate"]',
            'meta[name="date"]',
            'meta[itemprop="datePublished"]',
            "time[datetime]",
        )
        for selector in meta_selectors:
            selected = soup.select_one(selector)
            if not selected:
                continue
            raw_value = selected.get("content") or selected.get("datetime") or selected.get_text(" ", strip=True)
            parsed = parse_date(raw_value)
            if parsed:
                return parsed
        for script in soup.select('script[type="application/ld+json"]'):
            parsed = self._published_at_from_json_ld(script.string or script.get_text(" ", strip=True))
            if parsed:
                return parsed
        return None

    def _published_at_from_json_ld(self, value: str) -> datetime | None:
        try:
            payload = json.loads(value)
        except json.JSONDecodeError:
            return None
        queue = payload if isinstance(payload, list) else [payload]
        while queue:
            node = queue.pop(0)
            if not isinstance(node, dict):
                continue
            for key in ("datePublished", "dateCreated", "uploadDate"):
                parsed = parse_date(str(node.get(key) or ""))
                if parsed:
                    return parsed
            graph = node.get("@graph")
            if isinstance(graph, list):
                queue.extend(graph)
        return None

    def extract_page_metadata(self, url: str) -> dict:
        if not url or url.startswith("javascript:"):
            return {}
        try:
            soup = self.soup(url)
        except Exception as exc:
            log.warning("article_metadata_fetch_failed", source=self.config.name, url=url, error=str(exc))
            return {}
        published_at = self.extract_meta_published_at(soup)
        image_url = self.extract_meta_image_url(soup, url)
        return {"published_at": published_at, "image_url": image_url}

    def extract_page_image_url(self, url: str) -> str:
        if not url:
            return ""
        try:
            return self.extract_meta_image_url(self.soup(url), url)
        except Exception as exc:
            log.warning("article_image_fetch_failed", source=self.config.name, url=url, error=str(exc))
            return ""

    def safe_fetch(self) -> list[RawItem]:
        try:
            return self.fetch_items()
        except Exception as exc:
            log.warning("source_fetch_failed", source=self.config.name, error=str(exc))
            return []
