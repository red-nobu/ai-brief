import datetime as dt
import email.utils
import xml.etree.ElementTree as ET
import httpx
from ..store import Item

ATOM = "{http://www.w3.org/2005/Atom}"


def _date(s):
    if not s:
        return None
    try:
        return email.utils.parsedate_to_datetime(s).astimezone(dt.timezone.utc)
    except Exception:
        try:
            return dt.datetime.fromisoformat(s.replace("Z", "+00:00"))
        except Exception:
            return None


def parse(xml_text, feed_name):
    root = ET.fromstring(xml_text)
    out = []
    for e in list(root.iter("item")) + list(root.iter(f"{ATOM}entry")):
        title = (e.findtext("title") or e.findtext(f"{ATOM}title") or "").strip()
        link = e.findtext("link") or ""
        if not link:
            le = e.find(f"{ATOM}link")
            link = le.get("href", "") if le is not None else ""
        desc = e.findtext("description") or e.findtext(f"{ATOM}summary") or e.findtext(f"{ATOM}content") or ""
        when = _date(e.findtext("pubDate") or e.findtext(f"{ATOM}published") or e.findtext(f"{ATOM}updated"))
        if title and link:
            out.append((Item(id=f"rss:{link.strip()}", source="rss", title=title, url=link.strip(),
                             summary=" ".join(desc.split())[:1200], org=feed_name,
                             published=when.isoformat() if when else ""), when))
    return out


def collect(cfg, lookback_hours=48):
    cutoff = dt.datetime.now(dt.timezone.utc) - dt.timedelta(hours=lookback_hours)
    items = []
    with httpx.Client(timeout=30, follow_redirects=True, headers={"User-Agent": "ai-briefing/0.1"}) as c:
        for f in cfg["feeds"]:
            try:   # a dead feed must not lose the others
                r = c.get(f["url"])
                r.raise_for_status()
                items += [it for it, when in parse(r.text, f["name"]) if when is None or when >= cutoff]
            except Exception:
                continue
    return items
