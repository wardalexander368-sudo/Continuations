"""Launch metadata: the JSON each pump.fun launch points to (description, links, image).

A create event carries a metadata `uri`. Most are IPFS links on ipfs.io, which
no longer serves them (HTTP 429, "switching to a service worker gateway"), so
IPFS paths are fetched through pump.fun's Pinata gateway, then dweb.link.
Other hosts (launch tools such as j7tracker, uxento, rapidlaunch) are fetched
as given.

`link_features` turns the metadata into numbers in code (lengths, which links
exist, which tool launched it). Jev is asked only about the text
(`tartar/jev.py`).
"""

from __future__ import annotations

import json
import re
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib.parse import urlparse

import httpx

IPFS_GATEWAYS = ("https://pump.mypinata.cloud/ipfs/", "https://dweb.link/ipfs/")
_IPFS_PATH = re.compile(r"/ipfs/([A-Za-z0-9]+)(/.*)?$")
SOCIAL_HOSTS = ("x.com", "twitter.com", "instagram.com", "tiktok.com", "youtube.com", "facebook.com", "reddit.com", "t.me")


def candidate_urls(uri: str) -> list[str]:
    """Where to fetch `uri`, best first."""
    if not uri:
        return []
    if uri.startswith("ipfs://"):
        cid = uri[len("ipfs://") :]
        return [g + cid for g in IPFS_GATEWAYS]
    match = _IPFS_PATH.search(urlparse(uri).path)
    if match and urlparse(uri).netloc in ("ipfs.io", "cloudflare-ipfs.com", "gateway.pinata.cloud", "cf-ipfs.com"):
        rest = match.group(1) + (match.group(2) or "")
        return [g + rest for g in IPFS_GATEWAYS]
    return [uri]


def fetch_one(client: httpx.Client, uri: str) -> dict | None:
    for url in candidate_urls(uri):
        try:
            response = client.get(url, follow_redirects=True)
        except httpx.HTTPError:
            continue
        if response.status_code == 200:
            try:
                data = response.json()
            except ValueError:
                return None
            return data if isinstance(data, dict) else None
    return None


def fetch_metadata(launches: dict[str, str], cache: str | Path, workers: int = 8, timeout: float = 15.0) -> dict[str, dict | None]:
    """Metadata by mint for {mint: uri}, cached in a JSON-lines file (None when it could not be fetched)."""
    cache = Path(cache)
    known: dict[str, dict | None] = {}
    if cache.exists():
        for line in cache.read_text().splitlines():
            if line.strip():
                row = json.loads(line)
                known[row["mint"]] = row["meta"]
    todo = [(mint, uri) for mint, uri in launches.items() if mint not in known and uri]
    if todo:
        cache.parent.mkdir(parents=True, exist_ok=True)
        with httpx.Client(timeout=timeout, limits=httpx.Limits(max_connections=workers)) as client, cache.open("a") as out:
            with ThreadPoolExecutor(max_workers=workers) as pool:
                for (mint, _), meta in zip(todo, pool.map(lambda item: fetch_one(client, item[1]), todo)):
                    known[mint] = meta
                    out.write(json.dumps({"mint": mint, "meta": meta}) + "\n")
    return {mint: known.get(mint) for mint in launches}


def _host(url) -> str:
    try:
        host = urlparse(str(url)).netloc.lower()
    except ValueError:
        return ""
    return host[4:] if host.startswith("www.") else host


def link_features(meta: dict | None, uri: str = "") -> dict[str, float]:
    """Numbers computed in code from the metadata (NaN-free; 0/1 flags)."""
    meta = meta or {}
    description = str(meta.get("description") or "")
    twitter, website, telegram = str(meta.get("twitter") or ""), str(meta.get("website") or ""), str(meta.get("telegram") or "")
    return {
        "meta_found": float(bool(meta)),
        "desc_chars": float(len(description)),
        "desc_words": float(len(description.split())),
        "has_twitter": float(bool(twitter)),
        "twitter_is_post": float("/status/" in twitter),  # a link to a post (often someone else's) rather than a profile
        "twitter_is_community": float("/communities/" in twitter or bool(meta.get("coin_community"))),
        "has_website": float(bool(website)),
        "website_is_social": float(any(_host(website).endswith(h) for h in SOCIAL_HOSTS)),
        "has_telegram": float(bool(telegram)),
        "ipfs_uri": float("/ipfs/" in uri or uri.startswith("ipfs://")),  # pump.fun's own uploader
        "tool_uri": float(bool(uri) and "/ipfs/" not in uri),  # a third-party launch tool's metadata host
    }


LINK_FEATURES = tuple(link_features(None))
