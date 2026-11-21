"""Bias audit: who actually ends up in the briefs? Run: python main.py --audit"""
from collections import Counter


def report(store, days=30):
    rows = store.db.execute(
        "SELECT source, org, big_lab, kind FROM briefed WHERE date >= date('now', ?)", (f"-{days} days",)).fetchall()
    if not rows:
        return "No briefed items in this window yet."
    n = len(rows)
    big = sum(r[2] for r in rows)
    src, orgs, kinds = Counter(r[0] for r in rows), Counter(r[1] for r in rows), Counter(r[3] for r in rows)
    lines = [f"Last {days} days: {n} items briefed",
             f"Big-lab share: {big}/{n} ({100*big//n}%)  | long-tail: {n-big}/{n}",
             "By source: " + ", ".join(f"{k}={v}" for k, v in src.most_common()),
             "By kind: " + ", ".join(f"{k}={v}" for k, v in kinds.most_common()),
             "Most frequent orgs/authors: " + ", ".join(f"{k or '?'}({v})" for k, v in orgs.most_common(8))]
    if big / n > 0.6:
        lines.append("WARNING: big labs dominate; consider adding more small-lab feeds or lowering slots.big_lab.")
    if len(src) == 1:
        lines.append("WARNING: only one source is contributing; check other collectors.")
    return "\n".join(lines)
