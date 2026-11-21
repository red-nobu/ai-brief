"""Cheap pre-filter: keyword relevance + a per-source cap so one noisy source can't flood triage."""
from collections import defaultdict


def keyword_score(item, interests):
    text = f"{item.title} {item.summary}".lower()
    return sum(1 for k in interests if k in text)


def prefilter(items, cfg):
    interests = cfg["interests"]
    cap = cfg["triage"]["max_per_source"]
    scored = [(keyword_score(i, interests), i) for i in items]
    keep = [(s, i) for s, i in scored if s > 0 or i.source == "hf_model"]  # HF models already tag-filtered
    by_src = defaultdict(list)
    for s, i in keep:
        by_src[i.source].append((s, i))
    out = []
    for lst in by_src.values():
        lst.sort(key=lambda t: t[0], reverse=True)   # stable: keeps source (recency) order on ties
        out += [i for _, i in lst[:cap]]
    return out
