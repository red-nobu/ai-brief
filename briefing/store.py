"""SQLite state: items seen so far, so each brief only contains new things."""
import json
import sqlite3
from dataclasses import dataclass, field, asdict


@dataclass
class Item:
    id: str            # globally unique, e.g. "arxiv:2401.00001", "hf:org/model"
    source: str        # arxiv | hf_model | hf_paper | github | rss
    title: str
    url: str
    summary: str = ""
    org: str = ""      # author/org; hidden from first-pass triage on purpose
    published: str = ""  # ISO 8601 UTC
    meta: dict = field(default_factory=dict)


SCHEMA = """
CREATE TABLE IF NOT EXISTS items (
  id TEXT PRIMARY KEY, source TEXT, title TEXT, url TEXT, summary TEXT,
  org TEXT, published TEXT, meta TEXT,
  first_seen TEXT DEFAULT CURRENT_TIMESTAMP,
  score REAL, reported INTEGER DEFAULT 0
);
CREATE TABLE IF NOT EXISTS briefed (
  id TEXT PRIMARY KEY, date TEXT DEFAULT CURRENT_DATE, source TEXT, org TEXT,
  big_lab INTEGER, kind TEXT, score REAL
);
"""


class Store:
    def __init__(self, path="briefing.db"):
        self.db = sqlite3.connect(path)
        self.db.executescript(SCHEMA)

    def add_new(self, items):
        """Insert unseen items; return only the ones that were new."""
        new = []
        for it in items:
            cur = self.db.execute(
                "INSERT OR IGNORE INTO items (id,source,title,url,summary,org,published,meta)"
                " VALUES (?,?,?,?,?,?,?,?)",
                (it.id, it.source, it.title, it.url, it.summary, it.org,
                 it.published, json.dumps(it.meta)),
            )
            if cur.rowcount:
                new.append(it)
        self.db.commit()
        return new

    def mark_reported(self, ids):
        self.db.executemany("UPDATE items SET reported=1 WHERE id=?", [(i,) for i in ids])
        self.db.commit()

    def record_briefed(self, items):
        self.db.executemany(
            "INSERT OR REPLACE INTO briefed (id,source,org,big_lab,kind,score) VALUES (?,?,?,?,?,?)",
            [(i.id, i.source, i.org, int(i.meta.get("big_lab", False)),
              i.meta.get("triage", {}).get("kind"), i.meta.get("triage", {}).get("total")) for i in items])
        self.db.commit()
