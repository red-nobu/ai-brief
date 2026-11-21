from briefing.collectors import arxiv, hf
from briefing.store import Store, Item

ARXIV = """<feed xmlns="http://www.w3.org/2005/Atom"><entry>
<id>http://arxiv.org/abs/2611.00001v1</id><title>  A  New
 TTS Model </title><summary> Does speech. </summary>
<published>2026-11-19T00:00:00Z</published><author><name>A. Person</name></author>
<category term="cs.SD"/></entry></feed>"""


def test_arxiv_parse():
    [it] = arxiv.parse(ARXIV)
    assert it.id == "arxiv:2611.00001" and it.title == "A New TTS Model"
    assert it.meta["categories"] == ["cs.SD"]


def test_hf_parse():
    [m] = hf.parse_models([{"id": "org/tts", "pipeline_tag": "text-to-speech", "likes": 3, "tags": ["a"]}], "text-to-speech")
    assert m.org == "org" and m.meta["likes"] == 3
    [p] = hf.parse_papers([{"paper": {"id": "2611.1", "title": "T", "summary": "S", "upvotes": 5}}])
    assert p.id == "arxiv:2611.1"


def test_dedupe_across_runs():
    s = Store(":memory:")
    items = [Item("a", "arxiv", "t", "u"), Item("b", "arxiv", "t2", "u2")]
    assert len(s.add_new(items)) == 2
    assert s.add_new(items) == []


# ---- step 2/3 ----
from briefing import triage as tri, write, filter as flt
from briefing.collectors import rss, modelscope, github

CFG = {"interests": ["speech", "image"], "triage": {"max_per_source": 2},
       "big_orgs": ["google", "openai"], "slots": {"long_tail": 2, "big_lab": 1}, "max_items_in_brief": 3}


def test_triage_parse_and_finetune_penalty():
    s = tri.parse_scores('Sure! {"novelty":8,"evidence":6,"openness":10,"relevance":9,"kind":"new_model","one_line":"x"}')
    assert s["total"] == round(8*.35 + 6*.25 + 10*.15 + 9*.25, 2)
    f = tri.parse_scores('{"novelty":8,"evidence":6,"openness":10,"relevance":9,"kind":"finetune"}')
    assert f["total"] == round(s["total"] / 2, 2)
    import pytest
    with pytest.raises(ValueError):
        tri.parse_scores("no json here")


def test_triage_is_blind_to_org(monkeypatch):
    seen = {}
    monkeypatch.setattr(tri.llm, "chat", lambda cfg, sys, user, url="": seen.setdefault("u", user) and
                        '{"novelty":5,"evidence":5,"openness":5,"relevance":5,"kind":"new_model","one_line":""}')
    it = Item("x", "arxiv", "Some Title", "u", "an abstract", org="Google DeepMind", meta={"likes": 999})
    tri.triage([it], {"llm": {"triage": {}, "ollama_url": ""}})
    assert "Google" not in seen["u"] and "999" not in seen["u"]


def test_slots_fill_long_tail_before_big_labs():
    def mk(i, org, total):
        it = Item(i, "github", i, "u", org=org)
        it.meta["triage"] = {"total": total, "kind": "new_model", "one_line": ""}
        return it
    items = [mk("g1", "google", 9), mk("g2", "openai", 8.5), mk("s1", "tiny", 3), mk("s2", "small", 2), mk("g3", "google", 8)]
    chosen = write.select(items, CFG)
    ids = {i.id for i in chosen}
    assert {"s1", "s2"} <= ids and len(chosen) == 3


def test_prefilter_caps_and_keywords():
    items = [Item(str(n), "arxiv", "speech model", "u") for n in range(5)] + [Item("z", "arxiv", "robots", "u")]
    out = flt.prefilter(items, CFG)
    assert len(out) == 2 and all("speech" in i.title for i in out)


def test_rss_parse_rss_and_atom():
    r = rss.parse("<rss><channel><item><title>T</title><link>http://a/1</link>"
                  "<pubDate>Fri, 20 Nov 2026 10:00:00 GMT</pubDate></item></channel></rss>", "Feed")
    assert r[0][0].id == "rss:http://a/1" and r[0][1] is not None
    a = rss.parse('<feed xmlns="http://www.w3.org/2005/Atom"><entry><title>T2</title>'
                  '<link href="http://a/2"/><updated>2026-11-20T10:00:00Z</updated></entry></feed>', "Feed")
    assert a[0][0].url == "http://a/2"


def test_modelscope_and_github_parse():
    [m] = modelscope.parse([{"Path": "org", "Name": "mdl", "CreatedTime": 1793438910, "Downloads": 5}])
    assert m.id == "ms:org/mdl"
    [g] = github.parse([{"full_name": "o/r", "html_url": "u", "owner": {"login": "o"}, "stargazers_count": 40, "topics": ["tts"]}])
    assert g.org == "o" and g.meta["stars"] == 40


def test_big_org_word_boundary():
    assert write.is_big(Item("a", "hf_paper", "t", "u", org="Meta AI"), ["meta"])
    assert not write.is_big(Item("b", "hf_model", "metadata-tools/x", "u", org="metadata-tools"), ["meta"])
    assert not write.is_big(Item("c", "arxiv", "t", "u", org="Google"), ["google"])   # arXiv: no affiliations


def test_send_builds_multipart_and_logs_in(monkeypatch):
    from briefing import send
    calls = {}

    class FakeSMTP:
        def __init__(self, host, port): calls["host"] = (host, port)
        def __enter__(self): return self
        def __exit__(self, *a): pass
        def login(self, u, p): calls["login"] = (u, p)
        def send_message(self, m): calls["msg"] = m

    monkeypatch.setattr(send.smtplib, "SMTP_SSL", FakeSMTP)
    for k, v in {"SMTP_HOST": "h", "SMTP_USER": "u@x", "SMTP_PASSWORD": "pw", "MAIL_TO": "to@x"}.items():
        monkeypatch.setenv(k, v)
    send.send("subj", "plain", "<p>html</p>")
    m = calls["msg"]
    assert calls["login"] == ("u@x", "pw") and m["To"] == "to@x" and m["Subject"] == "subj"
    assert m.get_body(("plain",)).get_content().strip() == "plain" and m.get_body(("html",)) is not None


def test_audit_and_briefed_roundtrip():
    from briefing import audit
    s = Store(":memory:")
    a, b = Item("a", "github", "o/a", "u", org="google"), Item("b", "arxiv", "t", "u", org="x")
    a.meta.update(big_lab=True, triage={"kind": "new_model", "total": 5})
    b.meta.update(big_lab=False, triage={"kind": "framework", "total": 4})
    s.record_briefed([a, b])
    r = audit.report(s)
    assert "2 items" in r and "50%" in r


def test_html_links_and_escaping():
    h = write.to_html("## T\n- [a<b](https://x.y/z) and **bold**")
    assert '<a href="https://x.y/z">a&lt;b</a>' in h and "<b>bold</b>" in h and "<h2>T</h2>" in h
