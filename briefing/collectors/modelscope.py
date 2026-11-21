import datetime as dt
import httpx
from ..store import Item


def parse(models):
    items = []
    for m in models:
        path, name = m.get("Path", ""), m.get("Name", "")
        if not path or not name:
            continue
        ts = m.get("CreatedTime") or 0
        title = f"{path}/{name}"
        items.append(Item(
            id=f"ms:{title}", source="modelscope", title=title,
            url=f"https://www.modelscope.cn/models/{title}",
            summary=" ".join(filter(None, [m.get("ChineseName"), m.get("Description"),
                                           "Tasks: " + ", ".join(t.get("Name", "") for t in (m.get("Tasks") or [])[:5])]))[:600],
            org=path,
            published=dt.datetime.fromtimestamp(ts, dt.timezone.utc).isoformat() if ts > 0 else "",
            meta={"downloads": m.get("Downloads", 0), "stars": m.get("Stars", 0)},
        ))
    return items


def collect(cfg, **_):
    r = httpx.put("https://www.modelscope.cn/api/v1/dolphin/models", timeout=30,
                  json={"PageSize": cfg.get("page_size", 40), "PageNumber": 1,
                        "SortBy": "GmtModified", "Target": "", "Criterion": []})
    r.raise_for_status()
    return parse(((r.json().get("Data") or {}).get("Model") or {}).get("Models") or [])
