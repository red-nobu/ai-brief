"""Deep read of the selected items: extract method, claims, numbers, caveats from fuller text."""
import json
import logging
import re
from . import llm
from .fetch import full_text

log = logging.getLogger("briefing")
SYSTEM = """Extract facts from the text. Reply ONLY JSON:
{"method":"1-2 sentences on how it works","claims":["..."],"numbers":["metric: value on dataset vs baseline, only if stated"],
 "caveats":["..."],"weights_released":true|false|null,"claims_sota":true|false,"sota_has_baselines":true|false}
Only state what the text says. If a claim has no numbers or baselines, set sota_has_baselines=false. Never invent numbers."""


def deepread(items, cfg):
    for it in items:
        try:
            reply = llm.chat(cfg["llm"]["write"], SYSTEM, f"{it.title}\n\n{full_text(it, 6000)}",
                             cfg["llm"].get("ollama_url", ""))
            m = re.search(r"\{.*\}", reply, re.S)
            it.meta["deep"] = json.loads(m.group(0)) if m else {}
        except Exception as e:
            log.warning("deep read failed for %s: %s", it.id, e)
    return items


def confidence_tag(it):
    d = it.meta.get("deep") or {}
    if it.source == "hf_model" or it.source == "modelscope":
        weights = "weights on hub"
    elif d.get("weights_released") is True:
        weights = "weights released"
    elif d.get("weights_released") is False:
        weights = "no weights"
    else:
        weights = "weights unclear"
    if d.get("claims_sota") and not d.get("sota_has_baselines"):
        evidence = "SOTA claim without baselines"
    elif d.get("numbers"):
        evidence = "numbers self-reported"
    else:
        evidence = "no numbers given"
    return f"{weights}; {evidence}"
