"""Fetch fuller text for an item (model card, README, abstract) - used by triage and deep read."""
import httpx


def _get(url, limit):
    try:
        r = httpx.get(url, timeout=20, follow_redirects=True, headers={"User-Agent": "ai-briefing/0.1"})
        if r.status_code == 200:
            return r.text[:limit]
    except Exception:
        pass
    return ""


def full_text(item, limit=6000):
    if item.source == "hf_model":
        return _get(f"https://huggingface.co/{item.title}/raw/main/README.md", limit)
    if item.source == "github":
        for b in ("main", "master"):
            t = _get(f"https://raw.githubusercontent.com/{item.title}/{b}/README.md", limit)
            if t:
                return t
        return ""
    if item.source in ("arxiv", "hf_paper"):
        return item.summary   # abstract; PDF parsing is out of scope
    return item.summary
