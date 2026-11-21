import argparse
import datetime as dt
import logging
import os
import pathlib
import yaml
from briefing.collectors import arxiv, hf, github, rss, modelscope
from briefing.store import Store
from briefing import write, send, filter as flt, triage as tri, deepread, audit, check

log = logging.getLogger("briefing")
LOOKBACK = {"github", "rss"}   # collectors that take lookback_hours
COLLECTORS = {"arxiv": arxiv.collect, "huggingface": hf.collect, "github": github.collect,
              "modelscope": modelscope.collect, "rss": rss.collect}


def load_env(path=".env"):
    p = pathlib.Path(path)
    if p.exists():
        for line in p.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip())


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true", help="print brief; don't email or mark items as seen")
    ap.add_argument("--no-llm", action="store_true", help="skip all LLM calls (keyword ranking only)")
    ap.add_argument("--check", action="store_true", help="test email, LLMs and sources, then exit")
    ap.add_argument("--audit", action="store_true", help="print bias report over the last 30 days, then exit")
    ap.add_argument("--db", default="briefing.db")
    a = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)
    load_env()
    cfg = yaml.safe_load(open("config.yaml"))
    if a.check:
        raise SystemExit(0 if check.run(cfg) else 1)
    store = Store(a.db)
    if a.audit:
        print(audit.report(store))
        return

    items = []
    for name, fn in COLLECTORS.items():   # one source failing must not kill the run
        try:
            kw = {"lookback_hours": cfg["lookback_hours"]} if name in LOOKBACK else {}
            got = fn(cfg["sources"][name], **kw)
            log.info("%s: %d items", name, len(got))
            items += got
        except Exception as e:
            log.warning("%s failed: %s", name, e)

    items = list({i.id: i for i in reversed(items)}.values())[::-1]   # same id from two sources: keep first (arXiv abstract)
    new = items if a.dry_run else store.add_new(items)
    if a.dry_run:   # still skip things already briefed, so dry-runs match real runs
        done = {r[0] for r in store.db.execute("SELECT id FROM items WHERE reported=1")}
        new = [i for i in items if i.id not in done]
    log.info("%d new items", len(new))

    cand = flt.prefilter(new, cfg)
    log.info("%d candidates after pre-filter", len(cand))
    if a.no_llm:   # keyword-only fallback: fake a triage score so selection still works
        for i in cand:
            k = flt.keyword_score(i, cfg["interests"])
            i.meta["triage"] = {"total": float(k), "kind": "unscored", "one_line": i.summary[:160]}
        scored = cand
    else:
        scored = tri.triage(cand, cfg)
        if not scored and cand:
            log.warning("triage produced nothing (is the LLM reachable? run --check)")
    chosen = write.select(scored, cfg)
    if not a.no_llm:
        deepread.deepread(chosen[: cfg["triage"]["deep_read_top"]], cfg)
    md = write.compose(chosen, cfg, use_llm=not a.no_llm)

    if a.dry_run:
        print(md)
        return
    send.send(f"AI briefing {dt.date.today()}", md, write.to_html(md))
    store.mark_reported([i.id for i in chosen])
    store.record_briefed(chosen)


if __name__ == "__main__":
    main()
