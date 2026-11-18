"""CLI: demo gratuita; verifica; tre tipologie; invio Buffer con blocchi di sicurezza."""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import requests

from . import buffer, deepseek, photos, verify
from .render import render, render_carousel
from .site import create_index

DEMO = [
    {"id": "demo-positive", "kind": "positive", "headline": "La ricerca apre nuove possibilità",
     "teaser": "Un esempio di notizia positiva", "summary": "Grafica dimostrativa. Nessuna notizia reale: testo e fotografia sintetici, non pubblicati.",
     "sources": [], "preview": True},
    {"id": "demo-negative", "kind": "negative", "headline": "Una sfida per il nostro pianeta",
     "teaser": "Un esempio di notizia negativa", "summary": "Grafica dimostrativa. Nessuna notizia reale: testo e fotografia sintetici, non pubblicati.",
     "sources": [], "preview": True},
    {"id": "demo-curiosity", "kind": "curiosity", "headline": "Cosa sappiamo davvero dei polpi?",
     "teaser": "La natura può sorprenderci ogni giorno", "summary": "Grafica dimostrativa. Nessuna notizia reale: testo e fotografia sintetici, non pubblicati.",
     "sources": [], "preview": True},
]


def kind_for_schedule(when: date | None = None) -> str:
    """Due pubblicazioni/settimana: le tre categorie ruotano a ogni slot."""
    when = when or datetime.now(ZoneInfo("Europe/Rome")).date()
    if when.isoweekday() not in (2, 5):
        raise ValueError("Oggi non è martedì né venerdì")
    anchor_tuesday = date(2026, 11, 17)
    this_tuesday = when - timedelta(days=(when.isoweekday() - 2) % 7)
    weeks = (this_tuesday - anchor_tuesday).days // 7
    slot = 0 if when.isoweekday() == 2 else 1
    return ("positive", "negative", "curiosity")[(weeks * 2 + slot) % 3]


def load_state(path: Path) -> dict:
    if not path.exists():
        return {"items": []}
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict) or not isinstance(value.get("items"), list):
        raise ValueError("Registro notizie non valido")
    return value


def save_state(path: Path, state: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(".tmp")
    temp.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temp.replace(path)


def caption(story: dict, page_url: str) -> str:
    labels = ", ".join(x["publisher"] for x in story.get("sources", []))
    attribution = story.get("photo") or {}
    photo_text = (f"\nFoto illustrativa: {attribution.get('author', 'Wikimedia Commons')} "
                  f"({attribution.get('license', '')}); crediti nel link in bio.") if attribution else ""
    return (f"{story['headline']}\n\n{story['summary']}\n\n"
            f"Fonti: {labels}. Articoli e date nel link in bio: {page_url}{photo_text}\n\n"
            + " ".join(story.get("hashtags", [])))


def prepare(kind: str, site: Path, state_path: Path, payload_path: Path, reserve: bool) -> None:
    state = load_state(state_path)
    if kind == "demo":
        if reserve:
            raise ValueError("Una demo non può essere pubblicata")
        base = Path(__file__).resolve().parent.parent / "assets" / "demo_photos"
        previews = []
        for item in DEMO:
            item = dict(item)
            item["event_date"] = date.today().isoformat()
            paths = render_carousel(item, site / "posts", photo=base / f"{item['kind']}.jpg", demo=True)
            item["images"] = ["posts/" + x.name for x in paths]
            item["image"] = item["images"][0]
            previews.append(item)
        create_index(site, state, previews)
        payload_path.write_text(json.dumps({"demo": True}), encoding="utf-8")
        print("Demo: 3 caroselli da 3 immagini, nessuna API chiamata e nessun post inviato.")
        return
    if kind not in ("positive", "negative", "curiosity"):
        raise ValueError("Categoria sconosciuta")
    if reserve and os.getenv("ALLOW_PUBLISH", "false").lower() != "true":
        raise ValueError("Pubblicazione bloccata: ALLOW_PUBLISH=true richiesto")

    print("Ricerca reale: può consumare credito DeepSeek.")
    result = deepseek.discover(kind, [i.get("headline", "") for i in state["items"]])
    story = verify.validate_structure(result, kind, state)
    evidence = verify.check_sources(story)
    deepseek.check_against_sources(story, evidence)
    photo = photos.search_photo(story["photo_keywords"])
    original_path = site / "photos" / (story["id"] + ".jpg")
    photos.download_photo(photo, original_path)
    story["photo"] = photo["attribution"]
    story["created_at"] = datetime.now(timezone.utc).isoformat()
    paths = render_carousel(story, site / "posts", photo=original_path)
    story["images"] = ["posts/" + path.name for path in paths]
    story["image"] = story["images"][0]
    story["preview"] = not reserve
    if reserve:
        story["status"] = "reserved"
        state["items"].append(story)
        save_state(state_path, state)
        create_index(site, state)
    else:
        create_index(site, state, [story])
    payload_path.parent.mkdir(parents=True, exist_ok=True)
    payload_path.write_text(json.dumps(story, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Notizia pronta: {story['id']} ({kind}). Prenotata per Buffer: {reserve}")


def check_public_image(url: str) -> None:
    url = verify.safe_https_url(url)
    for attempt in range(7):
        try:
            r = requests.get(url, stream=True, timeout=15, allow_redirects=False)
            if r.status_code == 200 and r.headers.get("Content-Type", "").startswith("image/png"):
                with r:
                    chunk = next(r.iter_content(chunk_size=16), b"")
                    if chunk.startswith(b"\x89PNG\r\n\x1a\n"):
                        return
            r.close()
        except requests.RequestException:
            pass
        if attempt < 6:
            time.sleep(8)
    raise RuntimeError("Immagine GitHub Pages non raggiungibile: non invio nulla a Buffer")


def publish(site: Path, state_path: Path, payload_path: Path, base_url: str) -> None:
    if os.getenv("ALLOW_PUBLISH", "false").lower() != "true":
        raise RuntimeError("Pubblicazione disabilitata: ALLOW_PUBLISH deve essere true")
    story = json.loads(payload_path.read_text(encoding="utf-8"))
    if story.get("demo") or story.get("preview") or story.get("kind") not in ("positive", "negative", "curiosity"):
        raise RuntimeError("Demo, anteprima o categoria non autorizzata")
    state = load_state(state_path)
    match = [r for r in state["items"] if r["id"] == story["id"]]
    if len(match) != 1 or match[0].get("status") != "reserved":
        raise RuntimeError("Post non prenotato o già inviato: operazione bloccata")
    page_url = base_url.rstrip("/") + "/"
    images = story.get("images")
    if not isinstance(images, list) or len(images) != 3:
        raise RuntimeError("Carosello incompleto: servono esattamente tre immagini")
    image_urls = []
    for path in images:
        if not isinstance(path, str) or not path.startswith("posts/") or ".." in path:
            raise RuntimeError("Percorso immagine non valido")
        url = page_url + path
        check_public_image(url)
        image_urls.append(url)
    channel = buffer.instagram_channel()
    print("Canale Instagram Buffer:", channel.get("name", ""))
    # Un unico tentativo: se Buffer riceve il post ma il client va in timeout,
    # occorre verificare manualmente la coda Buffer prima di qualsiasi retry.
    post_id = buffer.share_now(text=caption(story, page_url), image_urls=image_urls, channel_id=channel["id"])
    match[0]["status"] = "sent_to_buffer"
    match[0]["buffer_post_id"] = post_id
    match[0]["buffer_sent_at"] = datetime.now(timezone.utc).isoformat()
    save_state(state_path, state)
    create_index(site, state)
    print("Post accettato da Buffer, non necessariamente pubblicato su Instagram. ID:", post_id)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Notizie Instagram: 3 categorie, 2 slot settimanali")
    sub = parser.add_subparsers(dest="cmd", required=True)
    cmd = sub.add_parser("prepare", help="Genera anteprima o notizia")
    cmd.add_argument("--kind", choices=["demo", "positive", "negative", "curiosity"], default="demo")
    cmd.add_argument("--reserve", action="store_true")
    cmd = sub.add_parser("publish", help="Invia a Buffer la notizia già prenotata")
    cmd.add_argument("--base-url", required=True)
    sub.add_parser("check-buffer", help="Controllo Buffer di sola lettura")
    sub.add_parser("choose-kind", help="Seleziona automaticamente la categoria odierna")
    for name in ("prepare", "publish"):
        cmd = sub.choices[name]
        cmd.add_argument("--site", type=Path, default=Path("site"))
        cmd.add_argument("--state", type=Path, default=Path("data/state.json"))
        cmd.add_argument("--payload", type=Path, default=Path("payload.json"))
    args = parser.parse_args(argv)
    try:
        if args.cmd == "prepare":
            prepare(args.kind, args.site, args.state, args.payload, args.reserve)
        elif args.cmd == "publish":
            publish(args.site, args.state, args.payload, args.base_url)
        elif args.cmd == "choose-kind":
            print(kind_for_schedule())
        else:
            c = buffer.instagram_channel()
            print("Buffer: Instagram collegato come", c.get("name", ""), "(ID", c["id"], ")")
        return 0
    except Exception as exc:
        print("OPERAZIONE BLOCCATA:", exc, file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
