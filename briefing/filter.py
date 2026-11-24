"""Cheap pre-filter: keyword relevance + a per-source cap so one noisy source can't flood triage."""
from collections import defaultdict
from itertools import zip_longest


def keyword_score(item, interests):
    text = f"{item.title} {item.summary}".lower()
    return sum(1 for k in interests if k in text)


def _bypass(item):
    """Skip the keyword check for: watchlist hits, and HF models fetched by an audio tag (already tag-filtered).
    The catch-all any-to-any tag is NOT trusted: it is mostly image/video omni models."""
    if item.meta.get("watch"):
        return True
    return item.source == "hf_model" and item.meta.get("query_tag") != "any-to-any"


def _fair_by_tag(rows, cap):
    """Round-robin across the HF tags, trending first within each tag. Without this the first tag in the config
    (ASR, full of whisper finetunes) fills the whole cap and the other tags never reach triage."""
    groups = defaultdict(list)
    for s, n, i in rows:
        groups[i.meta.get("query_tag")].append((not i.meta.get("trending"), -s, n, i))
    queues = [[t[3] for t in sorted(g, key=lambda t: t[:3])] for g in groups.values()]
    out = []
    for batch in zip_longest(*queues):
        out += [i for i in batch if i is not None]
        if len(out) >= cap:
            break
    return out[:cap]


def prefilter(items, cfg):
    interests = cfg["interests"]
    tcfg = cfg["triage"]
    caps = tcfg.get("source_caps") or {}
    skip = set(tcfg.get("skip_derivatives") or [])   # e.g. converted / adapter / merge copies of someone else's model
    keep = []
    for n, i in enumerate(items):
        if i.meta.get("derivative") in skip and not i.meta.get("watch"):
            continue
        s = keyword_score(i, interests)
        if s > 0 or _bypass(i):
            keep.append((s, n, i))
    out = [i for _, _, i in keep if i.meta.get("watch")]   # watchlist: always reaches triage, outside the caps
    by_src = defaultdict(list)
    for s, n, i in keep:
        if not i.meta.get("watch"):
            by_src[i.source].append((s, n, i))
    for src, lst in by_src.items():
        cap = caps.get(src, tcfg["max_per_source"])
        lst.sort(key=lambda t: (-t[0], t[1]))   # keyword score, then source (recency) order on ties
        out += _fair_by_tag(lst, cap) if src == "hf_model" else [i for _, _, i in lst[:cap]]
    return out