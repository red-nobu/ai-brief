import datetime as dt
import os
import time
import httpx
from ..store import Item


def parse(rows):
    items = []
    for r in rows:
        items.append(Item(
            id=f"gh:{r['full_name']}", source="github", title=r["full_name"], url=r["html_url"],
            summary=(r.get("description") or "") + f" Topics: {', '.join(r.get('topics') or [])}",
            org=(r.get("owner") or {}).get("login", ""), published=r.get("created_at", ""),
            meta={"stars": r.get("stargazers_count", 0), "language": r.get("language"),
                  "license": (r.get("license") or {}).get("spdx_id")},
        ))
    return items


def collect(cfg, lookback_hours=48):
    since = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(hours=lookback_hours)).strftime("%Y-%m-%d")
    headers = {"Accept": "application/vnd.github+json"}
    if os.environ.get("GITHUB_TOKEN"):  # optional; raises the search rate limit
        headers["Authorization"] = f"Bearer {os.environ['GITHUB_TOKEN']}"
    seen, items = set(), []
    with httpx.Client(timeout=30, headers=headers) as c:
        for q in cfg["queries"]:
            time.sleep(2)   # unauthenticated search allows ~10 requests/minute
            r = c.get("https://api.github.com/search/repositories", params={
                "q": f'{q} created:>{since} stars:>={cfg.get("min_stars", 10)}',
                "sort": "stars", "order": "desc", "per_page": cfg.get("per_query", 15)})
            if r.status_code in (403, 429):   # rate limited: keep what we have
                break
            r.raise_for_status()
            for it in parse(r.json().get("items", [])):
                if it.id not in seen:
                    seen.add(it.id)
                    items.append(it)
    return items
