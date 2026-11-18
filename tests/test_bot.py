import json
from datetime import date
from pathlib import Path

import pytest
from bs4 import BeautifulSoup

from newsbot import buffer, deepseek, verify, photos
from newsbot.cli import caption, load_state, prepare, publish, kind_for_schedule
from newsbot.render import render, render_carousel


def story():
    return {
        "headline": "Progresso concreto dopo un importante risultato della ricerca",
        "summary": " ".join(["Una notizia viene descritta con precisione e senza dichiarazioni non dimostrate."] * 11),
        "event_date": "2026-11-17",
        "teaser": "Una breve spiegazione verificabile della notizia",
        "photo_keywords": "scientist research laboratory",
        "sources": [
            {"url": "https://www.reuters.com/world/actual-story-1", "publisher": "Reuters", "published_at": "2026-11-17"},
            {"url": "https://apnews.com/article/actual-story-2", "publisher": "AP News", "published_at": "2026-11-17"},
        ],
        "hashtags": ["#Notizie", "#Mondo", "#Scienza"],
    }


def test_structure_success():
    s = verify.validate_structure(story(), "positive", {"items": []}, today=date(2026, 11, 18))
    assert s["id"] and s["kind"] == "positive" and len(s["sources"]) == 2


def test_duplicate_source():
    s = verify.validate_structure(story(), "positive", {"items": []}, today=date(2026, 11, 18))
    with pytest.raises(verify.ValidationError, match="fonte"):
        verify.validate_structure(story(), "positive", {"items": [s]}, today=date(2026, 11, 18))


def test_duplicate_domain():
    value = story()
    value["sources"][1]["url"] = "https://news.reuters.com/breaking/other"
    with pytest.raises(verify.ValidationError, match="stesso editore"):
        verify.validate_structure(value, "positive", {"items": []}, today=date(2026, 11, 18))


def test_insecure_url():
    for url in ("http://example.org/post", "https://localhost/post", "https://127.0.0.1/private"):
        with pytest.raises(verify.ValidationError):
            verify.safe_https_url(url)


def test_date_metadata():
    s = BeautifulSoup('<meta property="article:published_time" content="2026-11-17T08:00:00Z">', "html.parser")
    assert verify._published(s) == date(2026, 11, 17)
    s2 = BeautifulSoup('<script type="application/ld+json">{"datePublished":"2026-11-16"}</script>', "html.parser")
    assert verify._published(s2) == date(2026, 11, 16)


def test_parsing_json_markdown():
    assert deepseek.parse_json('```json\n{"headline":"Titolo"}\n```')["headline"] == "Titolo"
    with pytest.raises(deepseek.ResearchError):
        deepseek.parse_json("Testo senza JSON")


def test_render(tmp_path):
    item = story() | {"kind": "negative"}
    p = tmp_path / "image.png"
    photo = Path(__file__).resolve().parent.parent / "assets" / "demo_photos" / "negative.jpg"
    render(item, p, demo=True, photo=photo)
    from PIL import Image
    with Image.open(p) as im:
        assert im.size == (1080, 1350)
        assert im.format == "PNG"


def test_demo_does_not_call_api(monkeypatch, tmp_path):
    monkeypatch.setattr(deepseek, "discover", lambda *a: pytest.fail("chiamata API vietata in demo"))
    site, state, payload = tmp_path / "site", tmp_path / "state.json", tmp_path / "payload.json"
    prepare("demo", site, state, payload, reserve=False)
    assert (site / "index.html").exists()
    assert len(list((site / "posts").glob("*.png"))) == 9
    assert json.loads(payload.read_text())["demo"]
    assert not state.exists()


def test_demo_cannot_be_reserved(tmp_path):
    with pytest.raises(ValueError):
        prepare("demo", tmp_path / "site", tmp_path / "state.json", tmp_path / "payload.json", True)


def test_publish_requires_double_gate(monkeypatch, tmp_path):
    monkeypatch.delenv("ALLOW_PUBLISH", raising=False)
    with pytest.raises(RuntimeError, match="disabilitata"):
        publish(tmp_path, tmp_path / "state", tmp_path / "payload", "https://example.org/")


def test_buffer_mutation(monkeypatch):
    def fake_graphql(query):
        assert "mode: shareNow" in query
        assert "assets: [{image:" in query
        assert "schedulingType: automatic" in query
        return {"createPost": {"post": {"id": "post123"}}}
    monkeypatch.setattr(buffer, "graphql", fake_graphql)
    assert buffer.share_now(text='Ciao "mondo"', image_url="https://example.org/post.png", channel_id="id") == "post123"


def test_buffer_query_reads_only(monkeypatch):
    queries = []
    def fake(query):
        queries.append(query)
        if "organizations" in query:
            return {"account": {"organizations": [{"id": "org"}]}}
        return {"channels": [{"id": "ig", "name": "notizie", "service": "instagram"}]}
    monkeypatch.delenv("BUFFER_CHANNEL_ID", raising=False)
    monkeypatch.setattr(buffer, "graphql", fake)
    assert buffer.instagram_channel()["id"] == "ig"
    assert not any("mutation" in q.lower() for q in queries)


def test_reserve_flow_mock(monkeypatch, tmp_path):
    s = story()
    monkeypatch.setenv("ALLOW_PUBLISH", "true")
    monkeypatch.setattr(deepseek, "discover", lambda *a: s)
    monkeypatch.setattr(verify, "check_sources", lambda *a, **k: [{"url": "https://a.com", "text": "evidence"}, {"url": "https://b.com", "text": "evidence"}])
    monkeypatch.setattr(deepseek, "check_against_sources", lambda *a: None)
    monkeypatch.setattr(photos, "search_photo", lambda *a: {"url": "https://upload.wikimedia.org/fake.jpg", "attribution": {"author": "Example", "license": "CC0", "source_page": "https://commons.wikimedia.org/wiki/File:Fake.jpg"}})
    from shutil import copy2
    demo_photo = Path(__file__).resolve().parent.parent / "assets" / "demo_photos" / "positive.jpg"
    monkeypatch.setattr(photos, "download_photo", lambda item, target: (target.parent.mkdir(parents=True, exist_ok=True), copy2(demo_photo, target)))
    # Simuliamo la validazione già verificata per non dipendere dalla data attuale.
    monkeypatch.setattr(verify, "validate_structure", lambda d, k, state:
                        {**d, "kind": k, "id": "1234567890abcdef"})
    site, state, payload = tmp_path / "site", tmp_path / "state.json", tmp_path / "payload.json"
    prepare("positive", site, state, payload, reserve=True)
    assert load_state(state)["items"][0]["status"] == "reserved"
    assert len(load_state(state)["items"][0]["images"]) == 3
    assert not json.loads(payload.read_text())["preview"]
    calls = []
    monkeypatch.setattr("newsbot.cli.check_public_image", lambda *a: None)
    monkeypatch.setattr(buffer, "instagram_channel", lambda: {"id": "ig", "name": "Test"})
    def fake_send(**kwargs):
        calls.append(kwargs)
        return "buffer-id"
    monkeypatch.setattr(buffer, "share_now", fake_send)
    publish(site, state, payload, "https://example.org/pages/")
    assert len(calls) == 1
    assert len(calls[0]["image_urls"]) == 3
    assert load_state(state)["items"][0]["status"] == "sent_to_buffer"
    with pytest.raises(RuntimeError):
        publish(site, state, payload, "https://example.org/pages/")
    assert len(calls) == 1


def test_caption_has_references():
    s = story()
    result = caption(s, "https://example.org/")
    assert "Reuters" in result and "AP News" in result and "#Scienza" in result

class FakeHttpResponse:
    status_code = 200
    headers = {"Content-Type": "text/html; charset=utf-8"}
    def raise_for_status(self):
        return None
    def iter_content(self, chunk_size):
        html = ('<html><head><meta property="article:published_time" '
                'content="2026-11-17T11:00:00Z"></head><body>'
                '<article>' + ('Important event confirmed in this article. ' * 30) + '</article>'
                '</body></html>')
        yield html.encode()
    def close(self):
        pass


def test_article_fetch_metadata_and_text():
    class Session:
        def get(self, url, **kwargs):
            assert kwargs.get("allow_redirects") is False
            return FakeHttpResponse()
    source = verify.fetch_article("https://www.reuters.com/world/article", today=date(2026, 11, 18), session=Session())
    assert source["published_at"] == "2026-11-17"
    assert len(source["text"]) >= 450


def test_web_search_is_mandatory(monkeypatch):
    class NoWebResponse:
        def raise_for_status(self):
            pass
        def json(self):
            return {"choices": [{"finish_reason": "stop", "message": {"content": '{"headline":"test"}', "server_tool_calls": []}}],
                    "usage": {"server_tool_use": {"web_search_requests": 0}}}
    monkeypatch.setenv("DEEPSEEK_API_KEY", "fakekey")
    monkeypatch.setattr(deepseek.requests, "post", lambda *a, **kw: NoWebResponse())
    with pytest.raises(deepseek.ResearchError, match="ricerca web"):
        deepseek._api([{"role": "user", "content": "news"}], use_web=True)


def test_buffer_rejects_uncertain_mutation(monkeypatch):
    monkeypatch.setattr(buffer, "graphql", lambda query: {"createPost": {"message": "permission denied"}})
    with pytest.raises(buffer.BufferError):
        buffer.share_now(text="x", image_url="https://example.org/image.png", channel_id="ig")


def test_three_categories_render(tmp_path):
    from PIL import Image
    assets = Path(__file__).resolve().parent.parent / "assets" / "demo_photos"
    for kind in ("positive", "negative", "curiosity"):
        dest = tmp_path / f"{kind}.png"
        render(story() | {"kind": kind}, dest, photo=assets / f"{kind}.jpg", demo=True)
        with Image.open(dest) as im:
            assert im.size == (1080, 1350)
            assert im.getpixel((15, 500)) != (0, 0, 0)


def test_render_rejects_missing_photo(tmp_path):
    with pytest.raises(ValueError, match="Fotografia"):
        render(story() | {"kind": "curiosity"}, tmp_path / "x.png", photo=tmp_path / "missing.jpg")


def test_rotation_two_posts_per_week_three_kinds():
    assert kind_for_schedule(date(2026, 11, 17)) == "positive"
    assert kind_for_schedule(date(2026, 11, 20)) == "negative"
    assert kind_for_schedule(date(2026, 11, 24)) == "curiosity"
    assert kind_for_schedule(date(2026, 11, 27)) == "positive"
    assert kind_for_schedule(date(2026, 12, 1)) == "negative"
    with pytest.raises(ValueError):
        kind_for_schedule(date(2026, 11, 18))


def test_curiosity_allows_older_verified_sources():
    s = story()
    s["event_date"] = "2026-09-25"
    for src in s["sources"]:
        src["published_at"] = "2026-09-25"
    assert verify.validate_structure(s, "curiosity", {"items": []}, today=date(2026, 11, 18))["kind"] == "curiosity"
    with pytest.raises(verify.ValidationError):
        verify.validate_structure(s, "positive", {"items": []}, today=date(2026, 11, 18))


def test_photo_search_requires_licensed_attribution(monkeypatch):
    sample = {
      "query": {"pages": [
        {"title": "File:Test SA.jpg", "imageinfo": [{"mime":"image/jpeg", "width":2000, "height":1000,
          "thumburl":"https://upload.wikimedia.org/example-sa.jpg",
          "extmetadata":{"LicenseShortName":{"value":"CC BY-SA 4.0"}, "Artist":{"value":"Example"}}}]},
        {"title": "File:Test BY.jpg", "imageinfo": [{"mime":"image/jpeg", "width":2000, "height":1000,
          "thumburl":"https://upload.wikimedia.org/example.jpg",
          "extmetadata":{"LicenseShortName":{"value":"CC BY 4.0"}, "Artist":{"value":"Example"}}}]},
      ]}}
    class Resp:
        def raise_for_status(self): pass
        def json(self): return sample
    class Session:
        def get(self, *args, **kwargs): return Resp()
    pic = photos.search_photo("scientist laboratory", session=Session())
    assert pic["attribution"]["license"] == "CC BY 4.0"
    assert pic["url"].endswith("example.jpg")


def test_photo_search_fails_closed_on_no_rights():
    class Resp:
        def raise_for_status(self): pass
        def json(self): return {"query": {"pages": []}}
    class Session:
        def get(self, *args, **kwargs): return Resp()
    with pytest.raises(photos.PhotoError):
        photos.search_photo("forest conservation", session=Session())


def test_caption_photo_credit():
    s = story() | {"photo": {"author": "Example author", "license": "CC BY 4.0"}}
    assert "Foto illustrativa" in caption(s, "https://test.example/with")


def test_carousel_templates_and_alpha(tmp_path):
    from PIL import Image
    base=Path(__file__).resolve().parent.parent
    for kind in ('positive','negative','curiosity'):
        photo=base/'assets'/'demo_photos'/f'{kind}.jpg'
        story_data=story() | {'kind':kind,'id':f'demo-{kind}'}
        files=render_carousel(story_data,tmp_path,photo=photo,demo=True)
        assert len(files)==3
        for path in files:
            with Image.open(path) as im:
                assert im.size == (1080,1350)
                assert im.mode == 'RGB'
    for label in ('verde','rosso','celeste'):
        with Image.open(base/'assets'/'templates'/f'copertina_{label}.png') as a:
            with Image.open(base/'assets'/'templates'/f'interna_{label}.png') as b:
                assert a.mode=='RGBA' and b.mode=='RGBA'
                assert a.size==b.size==(1122,1402)


def test_buffer_carousel_order_and_safety(monkeypatch):
    sent=[]
    def fake(q):
        sent.append(q)
        return {'createPost':{'post':{'id':'sent'}}}
    monkeypatch.setattr(buffer,'graphql',fake)
    urls=['https://example.org/01.png','https://example.org/02.png','https://example.org/03.png']
    assert buffer.share_now(text='Test',image_urls=urls,channel_id='ig')=='sent'
    assert len(sent)==1 and all(x in sent[0] for x in urls)
    assert sent[0].index(urls[0]) < sent[0].index(urls[1]) < sent[0].index(urls[2])
    with pytest.raises(buffer.BufferError):
        buffer.share_now(text='Test',image_urls=['http://notsecure.com/0.png'],channel_id='ig')
