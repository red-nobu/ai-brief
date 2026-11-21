"""python main.py --check : tests each dependency separately and says what to fix."""
import os
import smtplib
import httpx
from . import llm


def _row(ok, name, detail=""):
    print(f"[{'PASS' if ok else 'FAIL'}] {name}" + (f" - {detail}" if detail else ""))
    return ok


def run(cfg):
    ok = True
    # 1. env vars
    need = ["SMTP_HOST", "SMTP_USER", "SMTP_PASSWORD", "MAIL_TO"]
    missing = [k for k in need if not os.environ.get(k) or "app-password-here" in os.environ.get(k, "")]
    ok &= _row(not missing, "email settings in .env", f"missing/placeholder: {missing}" if missing else "")
    # 2. SMTP login (does not send anything)
    if not missing:
        try:
            with smtplib.SMTP_SSL(os.environ["SMTP_HOST"], int(os.environ.get("SMTP_PORT", 465)), timeout=20) as s:
                s.login(os.environ["SMTP_USER"], os.environ["SMTP_PASSWORD"])
            ok &= _row(True, "SMTP login")
        except Exception as e:
            ok &= _row(False, "SMTP login", f"{e}. Gmail needs an APP PASSWORD (2-step verification on), not your normal password.")
    # 3. each configured LLM stage
    stages = {k: v for k, v in cfg["llm"].items() if isinstance(v, dict)}
    for name, sc in stages.items():
        p, model = sc["provider"], sc["model"]
        key = {"gemini": "GEMINI_API_KEY", "groq": "GROQ_API_KEY", "anthropic": "ANTHROPIC_API_KEY"}.get(p)
        if key and not os.environ.get(key):
            ok &= _row(False, f"LLM '{name}' ({p}:{model})", f"{key} not set in .env")
            continue
        if p == "ollama":
            try:
                tags = httpx.get(cfg["llm"]["ollama_url"] + "/api/tags", timeout=5).json()
                have = [m["name"] for m in tags.get("models", [])]
                if model not in have:
                    ok &= _row(False, f"LLM '{name}' (ollama:{model})", f"model not pulled. Run: ollama pull {model}. Have: {have}")
                    continue
            except Exception:
                ok &= _row(False, f"LLM '{name}' (ollama:{model})", "Ollama not reachable. Run: ollama serve")
                continue
        try:
            reply = llm.chat(sc, "Reply with the single word: ok", "ping", cfg["llm"].get("ollama_url", ""), timeout=120)
            ok &= _row(bool(reply.strip()), f"LLM '{name}' ({p}:{model})", reply.strip()[:40])
        except Exception as e:
            ok &= _row(False, f"LLM '{name}' ({p}:{model})", f"{e}. Check the key, the model name, and free-tier rate limits.")
    # 4. network sources
    for name, url in {"arXiv": "https://export.arxiv.org/api/query?search_query=cat:cs.SD&max_results=1",
                      "HuggingFace": "https://huggingface.co/api/models?limit=1",
                      "GitHub": "https://api.github.com/rate_limit",
                      "ModelScope": "https://www.modelscope.cn"}.items():
        try:
            httpx.get(url, timeout=20, follow_redirects=True).raise_for_status()
            _row(True, f"source reachable: {name}")
        except Exception as e:
            _row(False, f"source reachable: {name}", str(e)[:100])   # non-fatal: the run skips dead sources
    print("\nAll required checks passed." if ok else "\nFix the FAIL lines above, then re-run --check.")
    return ok
