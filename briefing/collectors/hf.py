import httpx
from ..store import Item

API = "https://huggingface.co/api"


def parse_models(rows, tag):
    items = []
    for m in rows:
        mid = m.get("id") or m.get("modelId")
        if not mid:
            continue
        items.append(Item(
            id=f"hf:{mid}",
            source="hf_model",
            title=mid,
            url=f"https://huggingface.co/{mid}",
            summary=f"Hugging Face model, task: {m.get('pipeline_tag') or tag}. Tags: {', '.join((m.get('tags') or [])[:15])}",
            org=mid.split("/")[0] if "/" in mid else "",
            published=m.get("createdAt", ""),
            meta={"likes": m.get("likes", 0), "downloads": m.get("downloads", 0),
                  "pipeline_tag": m.get("pipeline_tag"), "library": m.get("library_name")},
        ))
    return items


def parse_papers(rows):
    items = []
    for row in rows:
        p = row.get("paper", row)
        pid = p.get("id")
        if not pid:
            continue
        items.append(Item(
            id=f"arxiv:{pid}",   # same id as arXiv collector so the two dedupe
            source="hf_paper",
            title=p.get("title", ""),
            url=f"https://huggingface.co/papers/{pid}",
            summary=" ".join((p.get("summary") or "").split()),
            org=(p.get("organization") or {}).get("name", "") if isinstance(p.get("organization"), dict) else "",
            published=p.get("publishedAt", ""),
            meta={"upvotes": p.get("upvotes", 0), "github": p.get("githubRepo")},
        ))
    return items


def collect(cfg):
    items = []
    with httpx.Client(timeout=60, follow_redirects=True) as c:
        for tag in cfg["pipeline_tags"]:
            r = c.get(f"{API}/models", params={"pipeline_tag": tag, "sort": "createdAt",
                                               "direction": -1, "limit": cfg.get("limit_per_tag", 30)})
            r.raise_for_status()
            items += parse_models(r.json(), tag)
        if cfg.get("daily_papers"):
            r = c.get(f"{API}/daily_papers")
            r.raise_for_status()
            items += parse_papers(r.json())
    return items
