"""Public video metadata search; no account, API key, embeds or private journal query."""

import re
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import urlsplit

POOL = ThreadPoolExecutor(max_workers=2, thread_name_prefix="public-tutorial")


def find_tutorial(exercise, timeout=3):
    from ddgs import DDGS

    def search():
        rows = DDGS(timeout=2).videos(
            re.sub(r"\bcurls\b", "curl", exercise, flags=re.I)
            + " proper form 60 seconds site:youtube.com",
            max_results=10,
        )
        items = []
        for row in rows:
            url = row.get("content", "")
            parsed = urlsplit(url)
            if (
                parsed.scheme != "https"
                or parsed.hostname not in ("youtube.com", "www.youtube.com", "youtu.be")
                or parsed.username
                or parsed.password
            ):
                continue
            duration = str(row.get("duration", ""))
            seconds = None
            if re.fullmatch(r"\d{1,2}:\d{2}(?::\d{2})?", duration):
                seconds = 0
                for part in duration.split(":"):
                    seconds = seconds * 60 + int(part)
            items.append(
                {
                    "title": str(row.get("title", exercise + " demonstration"))[:180],
                    "url": url,
                    "seconds": seconds,
                }
            )
        items.sort(
            key=lambda item: (
                not (30 <= (item["seconds"] or 0) <= 60),
                item["seconds"] is None,
                abs((item["seconds"] or 90) - 45),
            )
        )
        return items[:1]

    future = POOL.submit(search)
    try:
        return future.result(timeout=max(0.1, timeout))
    except Exception:
        future.cancel()
        return []
