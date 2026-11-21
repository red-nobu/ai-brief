"""Slot allocation (long-tail first) + brief composition + HTML."""
import html
import re
from . import llm
from .deepread import confidence_tag

SYSTEM = """You write a concise daily briefing on new multimodal AI work (audio/speech, image, video, translation).
You get pre-extracted notes per item. Rules: use only the notes given; never add numbers or claims that are not
in them; keep the confidence tag exactly as given; call benchmark numbers 'self-reported'. Per item: the title as a
Markdown link, 2-3 sentences (what is new, how it works, why it matters), then 'Confidence: <tag>'.
Group into two sections: '## Under the radar' and '## Big labs' using each item's GROUP field. Output Markdown only."""


def is_big(item, big_orgs):
    org = (item.org or "").lower()
    if item.source == "arxiv":
        return False    # no affiliation data from arXiv
    hay = f"{org} {item.title.lower().split('/')[0]}"
    return any(re.search(rf"(?<![a-z0-9]){re.escape(b)}(?![a-z0-9])", hay) for b in big_orgs)


def select(items, cfg):
    """Fill long-tail slots first, then big-lab slots, then top up from whatever remains."""
    big_orgs = cfg["big_orgs"]
    ranked = sorted((i for i in items if "triage" in i.meta), key=lambda i: i.meta["triage"]["total"], reverse=True)
    for i in ranked:
        i.meta["big_lab"] = is_big(i, big_orgs)
    chosen = []
    for want_big, n in ((False, cfg["slots"]["long_tail"]), (True, cfg["slots"]["big_lab"])):
        chosen += [i for i in ranked if i.meta["big_lab"] == want_big and i not in chosen][:n]
    for i in ranked:   # top up if one side was short
        if len(chosen) >= cfg["max_items_in_brief"]:
            break
        if i not in chosen:
            chosen.append(i)
    return sorted(chosen[: cfg["max_items_in_brief"]], key=lambda i: i.meta["triage"]["total"], reverse=True)


def fallback_markdown(items):
    out = {"Under the radar": [], "Big labs": []}
    for i in items:
        d = i.meta.get("deep") or {}
        line = (f"- [{i.title}]({i.url}) ({i.source})\n  {i.meta['triage']['one_line'] or d.get('method', '')}\n"
                f"  Confidence: {confidence_tag(i)}")
        out["Big labs" if i.meta.get("big_lab") else "Under the radar"].append(line)
    return "\n\n".join(f"## {k}\n" + "\n".join(v) for k, v in out.items() if v)


def compose(items, cfg, use_llm=True):
    if not items:
        return "No new relevant items today."
    if not use_llm:
        return fallback_markdown(items)
    blocks = []
    for i in items:
        d = i.meta.get("deep") or {}
        blocks.append(f"TITLE: {i.title}\nURL: {i.url}\nGROUP: {'Big labs' if i.meta.get('big_lab') else 'Under the radar'}\n"
                      f"KIND: {i.meta['triage']['kind']}\nSUMMARY: {i.meta['triage']['one_line']}\n"
                      f"METHOD: {d.get('method', '')}\nCLAIMS: {d.get('claims', [])}\nNUMBERS: {d.get('numbers', [])}\n"
                      f"CAVEATS: {d.get('caveats', [])}\nCONFIDENCE TAG: {confidence_tag(i)}")
    try:
        return llm.chat(cfg["llm"]["write"], SYSTEM, "\n\n".join(blocks), cfg["llm"].get("ollama_url", ""))
    except Exception as e:
        return f"_(LLM unavailable: {e}; showing raw list)_\n\n" + fallback_markdown(items)


def to_html(md):
    def inline(t):
        t = html.escape(t)
        t = re.sub(r"\[([^\]]+)\]\((https?://[^)\s]+)\)", r'<a href="\2">\1</a>', t)
        return re.sub(r"\*\*([^*]+)\*\*", r"<b>\1</b>", t)
    out = []
    for line in md.splitlines():
        if line.startswith("## "):
            out.append(f"<h2>{inline(line[3:])}</h2>")
        elif line.startswith("# "):
            out.append(f"<h1>{inline(line[2:])}</h1>")
        elif line.strip():
            out.append(f"<p>{inline(line.lstrip('- '))}</p>")
    return "<html><body style='font-family:sans-serif;max-width:700px'>" + "\n".join(out) + "</body></html>"
