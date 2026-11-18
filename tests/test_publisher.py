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
        (folder / "02.png").unlink()
        with self.assertRaisesRegex(p.PublisherError, "Numerazione"):
            p.scan_queue()

    def test_wrong_dimensions(self):
        folder = self.add()
        (folder / "02.png").write_bytes(png(1122, 1402))
        with self.assertRaisesRegex(p.PublisherError, "Dimensioni errate"):
            p.scan_queue()

    def test_bad_caption(self):
        folder = self.add()
        (folder / "caption.txt").write_text("", encoding="utf-8")
        with self.assertRaisesRegex(p.PublisherError, "vuota"):
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


    def test_two_slides_allowed(self):
        folder = self.add()
        (folder / "03.png").unlink()
        post = p.scan_queue()[0]
        self.assertEqual([x.name for x in post["images"]], ["01.png", "02.png"])

    def test_four_slides_allowed_and_ordered(self):
        folder = self.add()
        (folder / "04.png").write_bytes(png())
        post = p.scan_queue()[0]
        self.assertEqual([x.name for x in post["images"]], ["01.png", "02.png", "03.png", "04.png"])
        urls = p.media_urls(post, repo="owner/repo", commit="a" * 40)
        self.assertEqual(len(urls), 4)
        self.assertTrue(urls[-1].endswith("04.png"))
        mutation = p.build_mutation(caption=post["caption"], channel_id="ig", urls=urls)
        self.assertEqual(mutation.count("{image: {url:"), 4)
        self.assertLess(mutation.index("01.png"), mutation.index("04.png"))

    def test_twenty_slides_allowed(self):
        folder = self.add()
        for i in range(4, 21):
            (folder / f"{i:02d}.png").write_bytes(png())
        self.assertEqual(len(p.scan_queue()[0]["images"]), 20)
        urls = [f"https://example.org/{i:02d}.png" for i in range(1, 21)]
        self.assertEqual(p.build_mutation(caption="Test", channel_id="ig", urls=urls).count("{image: {url:"), 20)

    def test_more_than_twenty_slides_rejected(self):
        folder = self.add()
        for i in range(4, 22):
            (folder / f"{i:02d}.png").write_bytes(png())
        with self.assertRaisesRegex(p.PublisherError, "da 2 a 20"):
            p.scan_queue()

    def test_one_slide_rejected(self):
        folder = self.add()
        (folder / "02.png").unlink()
        (folder / "03.png").unlink()
        with self.assertRaisesRegex(p.PublisherError, "da 2 a 20"):
            p.scan_queue()

    def test_wrong_image_filename_rejected(self):
        folder = self.add()
        (folder / "copertina.png").write_bytes(png())
        with self.assertRaisesRegex(p.PublisherError, "Nome immagine"):
            p.scan_queue()

    def test_caption_without_hashtags_gets_category_defaults(self):
        folder = self.add("001_curiosita_storia")
        (folder / "caption.txt").write_text("Questo testo descrive una curiosita' senza hashtag aggiunti.", encoding="utf-8")
        post = p.scan_queue()[0]
        self.assertIn("#Misteri", post["caption"])
        self.assertIn("#Curiosita", post["caption"])

    def test_caption_hashtag_file_deduplicates(self):
        folder = self.add()
        (folder / "caption.txt").write_text("Ecco una descrizione gia' verificata. #Mondo", encoding="utf-8")
        (folder / "hashtags.txt").write_text("#Mondo #Scienza #Scienza #Ricerca", encoding="utf-8")
        text = p.scan_queue()[0]["caption"]
        self.assertEqual(text.count("#Mondo"), 1)
        self.assertEqual(text.count("#Scienza"), 1)
        self.assertIn("#Ricerca", text)

    def test_editorial_text_builds_caption_and_keeps_note_private(self):
        folder = self.add("001_curiosita_enigma")
        (folder / "caption.txt").unlink()
        (folder / "sources.txt").unlink()
        editorial = """NOTIZIA 01 — UN MISTERO
CATEGORIA: Misteri
TESTI DEL CAROSELLO
===================
SLIDE 1 — COPERTINA
TITOLO: Un enigma antico
TESTO: Spiegazione nella grafica.

CAPTION INSTAGRAM
=================
Un manoscritto antico e' ancora oggetto di studio. Questo e' il testo pronto per Instagram.

HASHTAG
=======
#Misteri #Storia #Curiosita

FONTI CONSULTABILI
==================
- Istituto A
  https://example.org/research
- Istituto B
  https://example.net/report

NOTA EDITORIALE (NON PUBBLICARE)
===============================
NON SCRIVERE QUESTO NELLA CAPTION.
"""
        (folder / "31_mistero.txt").write_text(editorial, encoding="utf-8")
        post = p.scan_queue()[0]
        self.assertEqual(len(post["sources"]), 2)
        self.assertIn("#Storia", post["caption"])
        self.assertNotIn("NOTA EDITORIALE", post["caption"])
        self.assertNotIn("NON SCRIVERE", post["caption"])
        self.assertNotIn("SLIDE 1", post["caption"])
        self.assertNotIn("FONTI CONSULTABILI", post["caption"])

    def test_editorial_missing_second_source_fails_closed(self):
        folder = self.add()
        (folder / "caption.txt").unlink()
        (folder / "sources.txt").unlink()
        text = "CAPTION INSTAGRAM\n=================\nUna storia ben documentata con testo e fatti verificati.\nHASHTAG\n=======\n#Scienza\nFONTI CONSULTABILI\n==================\nhttps://example.org/only\n"
        (folder / "notizia.txt").write_text(text, encoding="utf-8")
        with self.assertRaisesRegex(p.PublisherError, "almeno due"):
            p.scan_queue()

    def test_editorial_long_caption_fails_no_truncation(self):
        folder = self.add()
        (folder / "caption.txt").unlink()
        (folder / "sources.txt").unlink()
        txt = ("CAPTION INSTAGRAM\n=================\n" + "Parola " * 400
               + "\nHASHTAG\n=======\n#Notizie\nFONTI CONSULTABILI\n==================\n"
               + "https://example.org/one\nhttps://example.net/two\n")
        (folder / "notizia.txt").write_text(txt, encoding="utf-8")
        with self.assertRaisesRegex(p.PublisherError, "2200"):
            p.scan_queue()

    def test_real_editorial_parser_with_four_slides_and_buffer(self):
        folder = self.add()
        (folder / "04.png").write_bytes(png())
        (folder / "caption.txt").unlink()
        (folder / "sources.txt").unlink()
        (folder / "notizia.txt").write_text(
            "CAPTION INSTAGRAM\n=================\nDidascalia di una notizia verificata, qui con maggiori dettagli.\n"
            "HASHTAG\n=======\n#Notizie #Ambiente\n"
            "FONTI CONSULTABILI\n==================\nhttps://example.org/article\nhttps://example.net/article\n",
            encoding="utf-8")
        p.save_state({"posts": {folder.name: {"status": "reserved"}}, "slots": {}})
        fake = {"createPost": {"post": {"id": "buffer-123"}}}
        with patch.object(p, "check_public_png") as media, patch.object(p, "_channel", return_value="ig"), \
             patch.object(p, "_graphql", return_value=fake) as send, \
             patch.dict(os.environ, {"ALLOW_PUBLISH": "true", "BUFFER_API_KEY": "fake"}):
            p.send(repo="owner/repo", commit="a" * 40, post_id=folder.name)
        self.assertEqual(media.call_count, 4)
        self.assertEqual(send.call_count, 1)
        self.assertIn("#Ambiente", send.call_args.args[0])
        self.assertIn("04.png", send.call_args.args[0])

    def test_two_editorial_files_rejected(self):
        folder = self.add()
        (folder / "caption.txt").unlink()
        (folder / "sources.txt").unlink()
        (folder / "notizia.txt").write_text("abc", encoding="utf-8")
        (folder / "altro.txt").write_text("abc", encoding="utf-8")
        with self.assertRaisesRegex(p.PublisherError, "un solo TXT"):
            p.scan_queue()

    def test_compose_editorial_with_one_source_warns_but_exports(self):
        folder = self.base / "out"
        input_file = self.base / "input.txt"
        input_file.write_text(
            "CAPTION INSTAGRAM\n=================\nUn testo verificato da un redattore, pronto per l'uso su Instagram.\n"
            "HASHTAG\n=======\n#Notizie #Scienza\n"
            "FONTI CONSULTABILI\n==================\nhttps://example.org/originale\n", encoding="utf-8")
        from unittest.mock import patch as patch_out
        with patch_out("sys.stdout", new_callable=__import__("io").StringIO) as output:
            p.compose_editorial(input_file, "buona", folder)
        self.assertIn("ATTENZIONE", output.getvalue())
        self.assertIn("#Scienza", (folder / "caption.txt").read_text())
        self.assertEqual((folder / "sources.txt").read_text().strip(), "https://example.org/originale")

    def test_compose_editorial_does_not_overwrite(self):
        input_file = self.base / "input.txt"
        input_file.write_text(
            "CAPTION INSTAGRAM\n=================\nUn testo di prova ben piu' lungo di trenta caratteri e verificato.\n"
            "HASHTAG\n=======\n#Scienza\nFONTI CONSULTABILI\n==================\n"
            "https://example.org/a\nhttps://example.net/b\n", encoding="utf-8")
        target = self.base / "export"
        target.mkdir()
        (target / "caption.txt").write_text("Non sovrascrivere", encoding="utf-8")
        with self.assertRaisesRegex(p.PublisherError, "non sovrascrivo"):
            p.compose_editorial(input_file, "buona", target)
        self.assertEqual((target / "caption.txt").read_text(), "Non sovrascrivere")

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
        with self.assertRaisesRegex(p.PublisherError, "da 2 a 20 URL"):
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
