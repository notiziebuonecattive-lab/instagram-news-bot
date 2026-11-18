"""CLI: demo gratuito, ricerca live, registrazione e invio protetto a Buffer."""
import argparse
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import requests

from . import buffer, deepseek, verify
from .render import render
from .site import create_index

DEMO = [
    {"id": "demo-positive", "kind": "positive", "headline": "Il lato positivo del mondo, una notizia alla volta",
     "summary": "Questa è soltanto una prova del modello grafico. Non rappresenta una notizia reale e non verrà pubblicata automaticamente.",
     "sources": [], "preview": True},
    {"id": "demo-negative", "kind": "negative", "headline": "Anche le notizie difficili meritano contesto",
     "summary": "Questa è soltanto una prova del modello grafico. Non rappresenta una notizia reale e non verrà pubblicata automaticamente.",
     "sources": [], "preview": True},
]


def load_state(path: Path) -> dict:
    if not path.exists():
        return {"items": []}
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict) or not isinstance(value.get("items"), list):
        raise ValueError("Registro notizie non valido")
    return value


def save_state(path: Path, state: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp.replace(path)


def caption(story: dict, page_url: str) -> str:
    labels = ", ".join(x["publisher"] for x in story.get("sources", []))
    return (f"{story['headline']}\n\n{story['summary']}\n\n"
            f"Fonti: {labels}. Articoli e date nel link in bio: {page_url}\n\n"
            + " ".join(story.get("hashtags", [])))


def prepare(kind: str, site: Path, state_path: Path, payload_path: Path, reserve: bool) -> None:
    state = load_state(state_path)
    if kind == "demo":
        if reserve:
            raise ValueError("Una demo non può essere pubblicata")
        for item in DEMO:
            item["image"] = f"posts/{item['id']}.png"
            render(item, site / item["image"], demo=True)
        create_index(site, state, DEMO)
        payload_path.write_text(json.dumps({"demo": True}), encoding="utf-8")
        print("Demo completata: 2 immagini di esempio, nessuna API chiamata.")
        return
    if kind not in ("positive", "negative"):
        raise ValueError("Categoria sconosciuta")
    if reserve and os.getenv("ALLOW_PUBLISH", "false").lower() != "true":
        raise ValueError("Pubblicazione bloccata. Impostare prima ALLOW_PUBLISH=true nelle Variables")
    print("Ricerca reale: può consumare credito DeepSeek.")
    result = deepseek.discover(kind, [i.get("headline", "") for i in state["items"]])
    story = verify.validate_structure(result, kind, state)
    evidence = verify.check_sources(story)
    deepseek.check_against_sources(story, evidence)
    story["image"] = "posts/" + story["id"] + ".png"
    story["created_at"] = datetime.now(timezone.utc).isoformat()
    # Le evidenze sono usate solo per verifica; la didascalia è già nel record.
    render(story, site / story["image"])
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
    print(f"Notizia preparata: {story['id']} ({kind}). Riservata per Buffer: {reserve}")


def check_public_image(url: str) -> None:
    url = verify.safe_https_url(url)
    for i in range(7):
        try:
            # GET a risposta stream: GitHub Pages può non propagare subito la nuova versione.
            r = requests.get(url, stream=True, timeout=15, allow_redirects=False)
            if r.status_code == 200 and r.headers.get("Content-Type", "").startswith("image/png"):
                with r:
                    chunk = next(r.iter_content(chunk_size=16), b"")
                    if chunk.startswith(b"\x89PNG\r\n\x1a\n"):
                        return
            r.close()
        except requests.RequestException:
            pass
        if i < 6:
            time.sleep(8)
    raise RuntimeError("Immagine GitHub Pages non raggiungibile: Buffer non sarà chiamato")


def publish(site: Path, state_path: Path, payload_path: Path, base_url: str) -> None:
    if os.getenv("ALLOW_PUBLISH", "false").lower() != "true":
        raise RuntimeError("Pubblicazione disabilitata: ALLOW_PUBLISH deve essere true")
    story = json.loads(payload_path.read_text(encoding="utf-8"))
    if story.get("demo") or story.get("preview"):
        raise RuntimeError("È vietato pubblicare una demo o una preview")
    state = load_state(state_path)
    match = [r for r in state["items"] if r["id"] == story["id"]]
    if len(match) != 1 or match[0].get("status") != "reserved":
        raise RuntimeError("Post non riservato o già inviato: pubblicazione bloccata")
    page_url = base_url.rstrip("/") + "/"
    image_url = page_url + story["image"]
    check_public_image(image_url)
    channel = buffer.instagram_channel()
    print("Buffer autorizzato sul canale Instagram:", channel.get("name", ""))
    # Un solo tentativo, mai retry su scritture: in caso di timeout la prenotazione resta bloccata.
    post_id = buffer.share_now(text=caption(story, page_url), image_url=image_url, channel_id=channel["id"])
    match[0]["status"] = "sent_to_buffer"  # NON equivale a pubblicato con successo su Instagram
    match[0]["buffer_post_id"] = post_id
    match[0]["buffer_sent_at"] = datetime.now(timezone.utc).isoformat()
    save_state(state_path, state)
    create_index(site, state)
    print("Post accettato da Buffer. ID:", post_id)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Bot Instagram notizie — pubblicazione prudente")
    sub = p.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("prepare", help="Prepara demo o notizia, senza pubblicazione")
    s.add_argument("--kind", choices=["demo", "positive", "negative"], default="demo")
    s.add_argument("--reserve", action="store_true", help="Riserva la notizia prima dell'invio")
    s = sub.add_parser("publish", help="Invia a Buffer una notizia già riservata")
    s.add_argument("--base-url", required=True, help="URL pubblico GitHub Pages restituito dal deploy")
    sub.add_parser("check-buffer", help="Interroga il canale Instagram in sola lettura")
    for name in ("prepare", "publish"):
        parser = sub.choices[name]
        parser.add_argument("--site", type=Path, default=Path("site"))
        parser.add_argument("--state", type=Path, default=Path("data/state.json"))
        parser.add_argument("--payload", type=Path, default=Path("payload.json"))
    args = p.parse_args(argv)
    try:
        if args.cmd == "prepare":
            prepare(args.kind, args.site, args.state, args.payload, args.reserve)
        elif args.cmd == "publish":
            publish(args.site, args.state, args.payload, args.base_url)
        else:
            c = buffer.instagram_channel()
            print("Connessione Buffer OK. Canale Instagram:", c.get("name", ""), "(ID:", c["id"], ")")
        return 0
    except Exception as exc:
        print("OPERAZIONE BLOCCATA:", str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
