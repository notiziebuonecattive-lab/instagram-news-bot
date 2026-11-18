"""Test offline: non viene mai chiamata una API reale."""
import io
import json
import os
import struct
import tempfile
import unittest
import zlib
from datetime import datetime
from pathlib import Path
from unittest.mock import patch
from zoneinfo import ZoneInfo

from bot import publisher as p


def png(w=1080, h=1350):
    def chunk(kind, body):
        data = kind + body
        return struct.pack(">I", len(body)) + data + struct.pack(">I", zlib.crc32(data) & 0xffffffff)
    ihdr = struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0)
    scanline = b"\x00" + b"\x80\x80\x80" * w
    return p.PNG_SIGNATURE + chunk(b"IHDR", ihdr) + chunk(b"IDAT", zlib.compress(scanline * h)) + chunk(b"IEND", b"")


class PublisherTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.queue = self.base / "posts" / "queue"
        self.queue.mkdir(parents=True)
        self.state_path = self.base / "data" / "state.json"
        self.patchers = [patch.object(p, "QUEUE", self.queue), patch.object(p, "STATE_FILE", self.state_path)]
        for patcher in self.patchers:
            patcher.start()
            self.addCleanup(patcher.stop)

    def add(self, name="001_buona_scoperta"):
        folder = self.queue / name
        folder.mkdir()
        for i in range(1, 4):
            (folder / f"0{i}.png").write_bytes(png())
        (folder / "caption.txt").write_text("Una notizia verificata. Questo è il testo del post. #Notizie #Mondo", encoding="utf-8")
        (folder / "sources.txt").write_text("https://example.org/news/one\nhttps://example.net/news/two\n", encoding="utf-8")
        return folder

    def test_empty_queue(self):
        self.assertEqual(p.scan_queue(), [])
        self.assertIsNone(p.pick_next([], p.load_state()))

    def test_valid_post(self):
        self.add()
        items = p.scan_queue()
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["category"], "buona")
        self.assertEqual(len(items[0]["images"]), 3)

    def test_order(self):
        self.add("003_curiosita_polpi")
        self.add("001_buona_scoperta")
        self.add("002_cattiva_evento")
        self.assertEqual([x["sequence"] for x in p.scan_queue()], [1, 2, 3])

    def test_duplicate_number(self):
        self.add("001_buona_scoperta")
        self.add("001_curiosita_polpi")
        with self.assertRaisesRegex(p.PublisherError, "duplicati"):
            p.scan_queue()

    def test_bad_folder_name(self):
        self.add("notizia-senza-numero")
        with self.assertRaisesRegex(p.PublisherError, "Nome cartella"):
            p.scan_queue()

    def test_missing_image(self):
        folder = self.add()
        (folder / "03.png").unlink()
        with self.assertRaisesRegex(p.PublisherError, "Immagine"):
            p.scan_queue()

    def test_wrong_dimensions(self):
        folder = self.add()
        (folder / "02.png").write_bytes(png(1122, 1402))
        with self.assertRaisesRegex(p.PublisherError, "Dimensioni errate"):
            p.scan_queue()

    def test_bad_caption(self):
        folder = self.add()
        (folder / "caption.txt").write_text("Manca hashtag", encoding="utf-8")
        with self.assertRaisesRegex(p.PublisherError, "didascalia"):
            p.scan_queue()

    def test_missing_sources(self):
        folder = self.add()
        (folder / "sources.txt").unlink()
        with self.assertRaisesRegex(p.PublisherError, "sources.txt"):
            p.scan_queue()

    def test_same_sources_domains(self):
        folder = self.add()
        (folder / "sources.txt").write_text("https://www.example.org/a\nhttps://example.org/b")
        with self.assertRaisesRegex(p.PublisherError, "domini"):
            p.scan_queue()

    def test_insecure_source(self):
        folder = self.add()
        (folder / "sources.txt").write_text("http://example.org/a\nhttps://example.net/b")
        with self.assertRaisesRegex(p.PublisherError, "HTTPS"):
            p.scan_queue()

    def test_empty_state(self):
        self.assertEqual(p.load_state(), {"posts": {}, "slots": {}})

    def test_reserve_permission_gate(self):
        self.add()
        with patch.dict(os.environ, {"ALLOW_PUBLISH": "false"}):
            with self.assertRaisesRegex(p.PublisherError, "ALLOW_PUBLISH"):
                p.reserve()
        self.assertFalse(self.state_path.exists())

    def test_reserve_automatic_on_slot(self):
        self.add()
        when = datetime(2026, 11, 17, 12, 7, tzinfo=ZoneInfo("Europe/Rome"))
        with patch.object(p, "local_now", return_value=when), patch.dict(os.environ, {"ALLOW_PUBLISH": "true"}):
            self.assertTrue(p.reserve())
            self.assertEqual(p.load_state()["posts"]["001_buona_scoperta"]["status"], "reserved")
            self.assertFalse(p.reserve())
            self.assertEqual(len(p.load_state()["slots"]), 1)

    def test_reserve_off_schedule(self):
        self.add()
        when = datetime(2026, 11, 18, 12, 7, tzinfo=ZoneInfo("Europe/Rome"))
        with patch.object(p, "local_now", return_value=when), patch.dict(os.environ, {"ALLOW_PUBLISH": "true"}):
            self.assertFalse(p.reserve())
        self.assertFalse(self.state_path.exists())

    def test_reserve_block_uncertain(self):
        self.add("001_buona_scoperta")
        self.add("002_cattiva_evento")
        p.save_state({"posts": {"001_buona_scoperta": {"status": "reserved"}}, "slots": {"2026-11-17": "001_buona_scoperta"}})
        when = datetime(2026, 11, 20, 12, 7, tzinfo=ZoneInfo("Europe/Rome"))
        with patch.object(p, "local_now", return_value=when), patch.dict(os.environ, {"ALLOW_PUBLISH": "true"}):
            with self.assertRaisesRegex(p.PublisherError, "Invio precedente"):
                p.reserve()

    def test_reserved_post_never_selected_again(self):
        self.add("001_buona_scoperta")
        self.add("002_cattiva_evento")
        state = {"posts": {"001_buona_scoperta": {"status": "sent_to_buffer"}}, "slots": {}}
        self.assertEqual(p.pick_next(p.scan_queue(), state)["id"], "002_cattiva_evento")

    def test_buffer_mutation_image_order(self):
        query = p.build_mutation(caption='Un testo "citato"\n#Mondo', channel_id="ig", urls=[
            "https://example.org/01.png", "https://example.org/02.png", "https://example.org/03.png"])
        self.assertIn("mode: shareNow", query)
        self.assertIn("schedulingType: automatic", query)
        self.assertLess(query.index("01.png"), query.index("02.png"))
        self.assertLess(query.index("02.png"), query.index("03.png"))
        self.assertIn('\\"citato\\"', query)

    def test_buffer_reject_wrong_assets(self):
        with self.assertRaisesRegex(p.PublisherError, "tre URL"):
            p.build_mutation(caption="ciao", channel_id="ig", urls=["https://example.org/01.png"])

    def test_media_links_pin_commit(self):
        self.add()
        item = p.scan_queue()[0]
        urls = p.media_urls(item, repo="notiziebuonecattive-lab/instagram-news-bot", commit="a" * 40)
        self.assertEqual(len(urls), 3)
        self.assertIn("/" + "a" * 40 + "/posts/queue/", urls[0])
        self.assertTrue(urls[2].endswith("/03.png"))

    def test_send_gate_fails_before_any_network(self):
        with patch.dict(os.environ, {"ALLOW_PUBLISH": "false"}):
            with self.assertRaisesRegex(p.PublisherError, "ALLOW_PUBLISH"):
                p.send(repo="owner/repo", commit="a" * 40, post_id="001")

    def test_channel_read_uses_graphql_only(self):
        calls = []
        def fake(query, token):
            calls.append(query)
            if "organizations" in query:
                return {"account": {"organizations": [{"id": "org"}]}}
            return {"channels": [{"id": "channel", "service": "instagram"}]}
        with patch.object(p, "_graphql", side_effect=fake), patch.dict(os.environ, {"BUFFER_CHANNEL_ID": ""}):
            self.assertEqual(p._channel("token"), "channel")
        self.assertTrue(all("mutation" not in query.lower() for query in calls))

    def test_send_success_updates_state(self):
        self.add()
        p.save_state({"posts": {"001_buona_scoperta": {"status": "reserved"}},
                      "slots": {"2026-11-17": "001_buona_scoperta"}})
        response = {"createPost": {"post": {"id": "buffer-post-id"}}}
        with patch.object(p, "check_public_png") as check_media, \
             patch.object(p, "_channel", return_value="ig"), \
             patch.object(p, "_graphql", return_value=response) as query, \
             patch.dict(os.environ, {"ALLOW_PUBLISH": "true", "BUFFER_API_KEY": "token"}):
            p.send(repo="owner/repo", commit="a" * 40, post_id="001_buona_scoperta")
        self.assertEqual(check_media.call_count, 3)
        self.assertEqual(query.call_count, 1)
        self.assertEqual(p.load_state()["posts"]["001_buona_scoperta"]["status"], "sent_to_buffer")
        self.assertEqual(p.load_state()["posts"]["001_buona_scoperta"]["buffer_post_id"], "buffer-post-id")

    def test_send_uncertain_keeps_reservation(self):
        self.add()
        p.save_state({"posts": {"001_buona_scoperta": {"status": "reserved"}},
                      "slots": {"2026-11-17": "001_buona_scoperta"}})
        with patch.object(p, "check_public_png"), \
             patch.object(p, "_channel", return_value="ig"), \
             patch.object(p, "_graphql", side_effect=p.PublisherError("timeout")), \
             patch.dict(os.environ, {"ALLOW_PUBLISH": "true", "BUFFER_API_KEY": "token"}):
            with self.assertRaisesRegex(p.PublisherError, "timeout"):
                p.send(repo="owner/repo", commit="a" * 40, post_id="001_buona_scoperta")
        self.assertEqual(p.load_state()["posts"]["001_buona_scoperta"]["status"], "reserved")

    def test_state_persistence(self):
        s = {"posts": {"001_buona_scoperta": {"status": "sent_to_buffer"}}, "slots": {"2026-11-17": "001_buona_scoperta"}}
        p.save_state(s)
        self.assertEqual(p.load_state(), s)


if __name__ == "__main__":
    unittest.main()
