import re
import xml.etree.ElementTree as ET
import httpx
from ..store import Item

NS = {"a": "http://www.w3.org/2005/Atom"}


def parse(xml_text):
    root = ET.fromstring(xml_text)
    items = []
    for e in root.findall("a:entry", NS):
        url = e.findtext("a:id", "", NS).strip()
        arx_id = re.sub(r"v\d+$", "", url.rsplit("/abs/", 1)[-1])  # drop version so it dedupes with HF papers
        authors = [a.findtext("a:name", "", NS) for a in e.findall("a:author", NS)]
        items.append(Item(
            id=f"arxiv:{arx_id}",
            source="arxiv",
            title=" ".join(e.findtext("a:title", "", NS).split()),
            url=url,
            summary=" ".join(e.findtext("a:summary", "", NS).split()),
            org=", ".join(authors[:3]),
            published=e.findtext("a:published", "", NS),
            meta={"authors": authors, "categories": [c.get("term") for c in e.findall("a:category", NS)]},
        ))
    return items


def collect(cfg):
    cats = " OR ".join(f"cat:{c}" for c in cfg["categories"])
    r = httpx.get(
        "https://export.arxiv.org/api/query",
        params={"search_query": cats, "sortBy": "submittedDate", "sortOrder": "descending",
                "max_results": cfg.get("max_results", 100)},
        timeout=60, follow_redirects=True,
    )
    r.raise_for_status()
    return parse(r.text)
