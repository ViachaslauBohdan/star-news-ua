from __future__ import annotations

from urllib.parse import parse_qsl, urlencode, urljoin, urlparse, urlunparse


TRACKING_PREFIXES = ("utm_",)
TRACKING_PARAMS = {"fbclid", "gclid", "yclid", "mc_cid", "mc_eid"}


def absolute_url(base_url: str, url: str) -> str:
    return urljoin(base_url, url)


def is_probable_image_url(url: str | None) -> bool:
    if not url:
        return False
    lowered = url.casefold().split("?", 1)[0]
    return lowered.endswith((".jpg", ".jpeg", ".png", ".webp", ".gif"))


def canonicalize_url(url: str) -> str:
    parsed = urlparse(url.strip())
    scheme = parsed.scheme.lower() or "https"
    netloc = parsed.netloc.lower()
    path = parsed.path.rstrip("/") or "/"
    query = urlencode(
        [
            (k, v)
            for k, v in parse_qsl(parsed.query, keep_blank_values=False)
            if k not in TRACKING_PARAMS and not any(k.startswith(prefix) for prefix in TRACKING_PREFIXES)
        ]
    )
    return urlunparse((scheme, netloc, path, "", query, ""))
