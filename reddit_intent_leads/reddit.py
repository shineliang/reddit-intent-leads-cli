from __future__ import annotations

import hashlib
import json
import os
import random
import time
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Any, Iterable

USER_AGENT = "reddit-intent-leads/0.1 (+https://github.com; contact: local)"


def _sha1(s: str) -> str:
    return hashlib.sha1(s.encode("utf-8")).hexdigest()


def _mkdirp(p: str) -> None:
    os.makedirs(p, exist_ok=True)


def http_get_json(url: str, *, cache_dir: str | None = None, sleep_s: float = 1.0) -> Any:
    cache_path = None
    if cache_dir:
        _mkdirp(cache_dir)
        cache_path = os.path.join(cache_dir, f"{_sha1(url)}.json")
        if os.path.exists(cache_path):
            with open(cache_path, "r", encoding="utf-8") as f:
                return json.load(f)

    req = urllib.request.Request(
        url,
        headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
        method="GET",
    )

    last_err: Exception | None = None
    for attempt in range(1, 6):
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                raw = resp.read().decode("utf-8")
                obj = json.loads(raw)
            if cache_path:
                with open(cache_path, "w", encoding="utf-8") as f:
                    json.dump(obj, f)
            time.sleep(max(0.0, sleep_s) + random.uniform(0.0, sleep_s * 0.3))
            return obj
        except Exception as e:
            last_err = e
            msg = str(e)
            if "HTTP Error 429" in msg:
                backoff = min(60.0, (sleep_s * 5) * (2 ** (attempt - 1)))
                time.sleep(backoff + random.uniform(0.0, 1.0))
                continue
            raise

    if last_err:
        raise last_err
    raise RuntimeError("unknown http error")


@dataclass
class Lead:
    kind: str  # post|comment
    subreddit: str
    title: str
    author: str
    created_utc: int
    score: int
    url: str
    text: str
    intent_score: float
    signals: list[str]


def search_posts(*, query: str, subs: list[str], limit: int, after_utc: int, cache_dir: str | None, sleep_s: float) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    q = query.strip()

    # per-subreddit search tends to be more reliable than global.
    for sub in subs:
        after = None
        while len(out) < limit:
            params = {
                "q": q,
                "restrict_sr": 1,
                "sort": "new",
                "t": "all",
                "limit": 100,
            }
            if after:
                params["after"] = after
            url = f"https://www.reddit.com/r/{sub}/search.json?{urllib.parse.urlencode(params)}"
            try:
                obj = http_get_json(url, cache_dir=cache_dir, sleep_s=sleep_s)
            except Exception:
                break

            children = (((obj or {}).get("data") or {}).get("children") or [])
            if not children:
                break

            for ch in children:
                d = (ch or {}).get("data") or {}
                created = int(d.get("created_utc") or 0)
                if created < after_utc:
                    continue
                out.append(d)
                if len(out) >= limit:
                    break

            after = ((obj.get("data") or {}).get("after"))
            if not after:
                break

    return out[:limit]


def fetch_comments(permalink: str, *, max_comments: int, cache_dir: str | None, sleep_s: float) -> list[dict[str, Any]]:
    url = f"https://www.reddit.com{permalink}.json?limit=500"
    try:
        obj = http_get_json(url, cache_dir=cache_dir, sleep_s=sleep_s)
    except Exception:
        return []

    if not isinstance(obj, list) or len(obj) < 2:
        return []

    listing = obj[1]
    children = (((listing or {}).get("data") or {}).get("children") or [])

    out: list[dict[str, Any]] = []

    def walk(nodes: Iterable[dict[str, Any]]):
        nonlocal out
        for n in nodes:
            kind = (n or {}).get("kind")
            d = (n or {}).get("data") or {}
            if kind == "t1":
                body = (d.get("body") or "").strip()
                if body:
                    out.append(
                        {
                            "id": d.get("id"),
                            "author": d.get("author") or "",
                            "created_utc": int(d.get("created_utc") or 0),
                            "score": int(d.get("score") or 0),
                            "body": body,
                        }
                    )
                    if len(out) >= max_comments:
                        return
                replies = d.get("replies")
                if replies and isinstance(replies, dict):
                    rchildren = (((replies.get("data") or {}).get("children")) or [])
                    if rchildren:
                        walk(rchildren)
                        if len(out) >= max_comments:
                            return
            elif kind == "more":
                continue

    walk(children)
    return out[:max_comments]
