"""LLM triage with the rubric. Org / stars / likes are NOT shown to the model."""
import json
import logging
import pathlib
import re
from . import llm
from .fetch import full_text

log = logging.getLogger("briefing")
RUBRIC = pathlib.Path(__file__).resolve().parent.parent / "rubric.md"
WEIGHTS = {"novelty": 0.35, "evidence": 0.25, "openness": 0.15, "relevance": 0.25}


def parse_scores(text):
    m = re.search(r"\{.*\}", text, re.S)
    if not m:
        raise ValueError("no JSON in model reply")
    d = json.loads(m.group(0))
    s = {k: max(0, min(10, float(d.get(k, 0)))) for k in WEIGHTS}
    s["kind"] = str(d.get("kind", "other"))
    s["one_line"] = str(d.get("one_line", ""))[:300]
    total = sum(s[k] * w for k, w in WEIGHTS.items())
    if s["kind"] in ("finetune", "other"):
        total *= 0.5
    s["total"] = round(total, 2)
    return s


def blind_text(item):
    """What the model sees: kind of source + title + text. No org, stars, likes."""
    body = full_text(item, 1800) if item.source in ("hf_model", "github") else item.summary[:1800]
    label = {"hf_model": "model card", "github": "repo README", "rss": "blog post",
             "arxiv": "paper abstract", "hf_paper": "paper abstract", "modelscope": "model listing"}.get(item.source, "item")
    return f"[{label}] {item.title}\n\n{body}"


def triage(items, cfg):
    rubric = RUBRIC.read_text()
    out = []
    for it in items:
        try:
            reply = llm.chat(cfg["llm"]["triage"], rubric, blind_text(it), cfg["llm"].get("ollama_url", ""))
            it.meta["triage"] = parse_scores(reply)
        except Exception as e:   # one bad reply never kills the run
            log.warning("triage failed for %s: %s", it.id, e)
            continue
        out.append(it)
    return out
