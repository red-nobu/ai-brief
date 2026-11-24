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
KINDS = {"new_architecture", "new_model", "finetune", "method", "framework", "benchmark", "dataset", "survey", "other"}
PENALISED = ("finetune", "other")   # halved, unless the numbers back them up (see parse_scores)


def parse_scores(text, relevance_gate=8.0, derivative=None):
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.S)   # thinking models can leak their reasoning into the reply
    m = re.search(r"\{.*\}", text, re.S)
    if not m:
        raise ValueError("no JSON in model reply")
    d = json.loads(m.group(0))
    missing = [k for k in WEIGHTS if k not in d]
    if missing:
        raise ValueError(f"reply is missing {missing}")   # used to be silently scored 0
    s = {k: max(0, min(10, float(d[k]))) for k in WEIGHTS}
    kind = str(d.get("kind", "other")).strip().lower()
    s["kind"] = kind if kind in KINDS else "other"
    if derivative == "finetune" and s["kind"] not in PENALISED:
        s["kind"] = "finetune"   # the card describes the base model's features; the Hub's model tree says it is a finetune
    s["one_line"] = str(d.get("one_line", ""))[:300]
    total = sum(s[k] * w for k, w in WEIGHTS.items())
    total *= min(1.0, s["relevance"] / relevance_gate)   # off-topic work can't ride on novelty/evidence/openness
    if s["kind"] in PENALISED and s["evidence"] < 6:      # a finetune that beats named baselines is what we want to see
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
    min_rel = cfg["triage"].get("min_relevance", 0)
    gate = cfg["triage"].get("relevance_gate", 8.0)
    out, dropped = [], 0
    for it in items:
        try:
            reply = llm.chat(cfg["llm"]["triage"], rubric, blind_text(it), cfg["llm"].get("ollama_url", ""))
            it.meta["triage"] = parse_scores(reply, gate, it.meta.get("derivative"))
        except Exception as e:   # one bad reply never kills the run
            log.warning("triage failed for %s: %s", it.id, e)
            continue
        if it.meta["triage"]["relevance"] < min_rel:   # not about audio: don't let it compete for a slot
            dropped += 1
            continue
        out.append(it)
    if dropped:
        log.info("triage: %d items below min_relevance=%s dropped", dropped, min_rel)
    return out