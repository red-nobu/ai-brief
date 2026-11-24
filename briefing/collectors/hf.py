import datetime as dt
import logging
import re
import httpx
from ..store import Item

log = logging.getLogger("briefing")
API = "https://huggingface.co/api"


_REL = re.compile(r"^base_model:(quantized|finetune|adapter|merge):(.+)$")   # the Hub's "model tree" tags
_CONVERTED = re.compile(r"(?i)(^|[-_.])(gguf|awq|gptq|exl[23]|mlx|onnx|bnb|int4|int8|fp8|nvfp4)([-_.]|$)")
_PRIORITY = ("converted", "adapter", "merge", "finetune")


def _derivative(mid, tags, library=None):
    """(kind, base_model) when the repo is a copy of another model, else (None, None).
    kind: converted (quantised / GGUF / ONNX / MLX), adapter (LoRA), merge, finetune."""
    tags = tags or []
    found = {}
    for t in tags:
        m = _REL.match(t)
        if m:
            found[("converted" if m.group(1) == "quantized" else m.group(1))] = m.group(2)
    if library == "gguf" or "gguf" in tags or _CONVERTED.search(mid.split("/")[-1]):
        found.setdefault("converted", None)
    for kind in _PRIORITY:
        if kind in found:
            return kind, found[kind]
    return None, None


def _license(tags):
    """Hub tags carry 'license:apache-2.0'; for 'license:other' the real name is in 'license_name:...'."""
    tags = tags or []
    lic = next((t.split(":", 1)[1] for t in tags if t.startswith("license:")), None)
    if lic == "other":
        lic = next((t.split(":", 1)[1] for t in tags if t.startswith("license_name:")), lic)
    return lic


def parse_models(rows, tag):
    items = []
    for m in rows:
        mid = m.get("id") or m.get("modelId")
        if not mid:
            continue
        derivative, base = _derivative(mid, m.get("tags"), m.get("library_name"))
        items.append(Item(
            id=f"hf:{mid}",
            source="hf_model",
            title=mid,
            url=f"https://huggingface.co/{mid}",
            summary=f"Hugging Face model, task: {m.get('pipeline_tag') or tag}. Tags: {', '.join((m.get('tags') or [])[:15])}",
            org=mid.split("/")[0] if "/" in mid else "",
            published=m.get("createdAt", ""),
            meta={"likes": m.get("likes", 0), "downloads": m.get("downloads", 0),
                  "pipeline_tag": m.get("pipeline_tag"), "library": m.get("library_name"),
                  "query_tag": tag, "license": _license(m.get("tags")),
                  "derivative": derivative, "base_model": base},
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


def _models(c, params, since=None, cap=100):
    """GET /models, following the Hub's Link-header pagination. Stops at `cap` rows, or (for createdAt-sorted
    queries) at the first row older than `since`."""
    rows, url, q = [], f"{API}/models", {**params, "limit": min(cap, 100)}
    while url and len(rows) < cap:
        r = c.get(url, params=q)
        r.raise_for_status()
        for m in r.json():
            if since and (m.get("createdAt") or "9999") < since:
                return rows
            rows.append(m)
        nxt = r.links.get("next")
        url, q = (str(r.url.join(nxt["url"])), None) if nxt else (None, None)
    return rows[:cap]


def collect(cfg):
    hours = cfg.get("lookback_hours")   # new: cover the whole window instead of only the newest N per tag
    since = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(hours=hours)).strftime("%Y-%m-%dT%H:%M:%S") if hours else None
    cap = cfg.get("max_per_tag", 100) if hours else cfg.get("limit_per_tag", 30)
    days = cfg.get("trending_max_age_days")   # trending also lists years-old favourites (whisper-large-v3): cap the age
    t_since = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=days)).strftime("%Y-%m-%dT%H:%M:%S") if days else None
    items, by_id = [], {}

    def add(new, **flags):
        for it in new:
            if it.id in by_id:   # same model via another query: keep one copy, but keep its flags
                by_id[it.id].meta.update(flags)
                continue
            it.meta.update(flags)
            by_id[it.id] = it
            items.append(it)

    with httpx.Client(timeout=60, follow_redirects=True) as c:
        for tag in cfg["pipeline_tags"]:
            base = {"pipeline_tag": tag, "direction": -1}
            add(parse_models(_models(c, {**base, "sort": "createdAt"}, since, cap), tag))
            if cfg.get("trending_per_tag"):   # what is getting attention now, even if uploaded days ago
                try:
                    rows = _models(c, {**base, "sort": "trendingScore"}, None, cfg["trending_per_tag"])
                    if t_since:
                        rows = [m for m in rows if (m.get("createdAt") or "9999") >= t_since]
                    add(parse_models(rows, tag), trending=True)
                except Exception as e:
                    log.warning("hf trending (%s) failed: %s", tag, e)
        for who in cfg.get("watch_authors", []):   # people/orgs we always want to see, whatever the tag or keywords
            try:
                rows = _models(c, {"author": who, "sort": "createdAt", "direction": -1}, since, cfg.get("watch_cap", 20))
                add(parse_models(rows, "watch"), watch=True)
            except Exception as e:
                log.warning("hf watch (%s) failed: %s", who, e)
        if cfg.get("daily_papers"):
            r = c.get(f"{API}/daily_papers")
            r.raise_for_status()
            items += parse_papers(r.json())
    return items