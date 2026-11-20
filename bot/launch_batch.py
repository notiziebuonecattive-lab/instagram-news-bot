"""Invio una tantum di 5 caroselli con 10 minuti tra le accettazioni Buffer.

NON modifica posts/queue, data/state.json o la pubblicazione settimanale.
La conferma Buffer NON prova da sola la pubblicazione effettiva su Instagram.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
import urllib.parse
from datetime import datetime, timezone
from pathlib import Path

from bot import publisher as p

ROOT = Path(__file__).resolve().parents[1]
LAUNCH = ROOT / "posts" / "launch"
STATE_PATH = ROOT / "data" / "launch_state.json"
CAMPAIGN = "lancio_cinque_2026_11"
INTERVAL_SECONDS = 600
POSTS = (
    "001_buona_lancio_coralli",
    "002_cattiva_lancio_fauna_73",
    "003_curiosita_lancio_marte",
    "004_buona_lancio_allerta_meteo",
    "005_curiosita_lancio_catena_romana",
)


def _ensure_authorized() -> None:
    if os.environ.get("ALLOW_PUBLISH", "false").lower() != "true":
        raise p.PublisherError("ALLOW_PUBLISH non e' true: stop senza invii")


def _state() -> dict:
    if not STATE_PATH.is_file():
        raise p.PublisherError("Manca data/launch_state.json")
    try:
        obj = json.loads(STATE_PATH.read_text(encoding="utf-8"))
    except (ValueError, OSError) as exc:
        raise p.PublisherError("Stato della campagna non valido") from exc
    if not isinstance(obj, dict) or obj.get("campaign") != CAMPAIGN or not isinstance(obj.get("posts"), dict):
        raise p.PublisherError("Campagna o struttura dati non corrispondente")
    if any(key not in POSTS for key in obj["posts"]):
        raise p.PublisherError("Trovato un identificativo sconosciuto nello stato")
    if any(not isinstance(v, dict) or v.get("status") not in ("reserved", "sent_to_buffer") for v in obj["posts"].values()):
        raise p.PublisherError("Trovato uno stato non valido: stop")
    return obj


def _save_state(obj: dict) -> None:
    temp = STATE_PATH.with_name(STATE_PATH.name + ".tmp")
    temp.write_text(json.dumps(obj, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temp.replace(STATE_PATH)


def _idx(index: int) -> str:
    if not 1 <= index <= len(POSTS):
        raise p.PublisherError("Indice consentito: da 1 a 5")
    return POSTS[index - 1]


def _inspect(name: str) -> dict:
    folder = LAUNCH / name
    if not folder.is_dir():
        raise p.PublisherError("Carosello del lancio mancante: " + name)
    post = p.inspect_post(folder)
    if len(post["images"]) != 4:
        raise p.PublisherError("Nel lancio servono esattamente 4 PNG per " + name)
    return post


def validate() -> None:
    if not LAUNCH.is_dir():
        raise p.PublisherError("Manca posts/launch")
    found = {folder.name for folder in LAUNCH.iterdir() if folder.is_dir()}
    if found != set(POSTS):
        raise p.PublisherError("Cartelle di lancio mancanti o estranee: " + repr(sorted(found.symmetric_difference(set(POSTS)))))
    for name in POSTS:
        post = _inspect(name)
        print(f"OK {name} | {post['category']} | {len(post['images'])} PNG | {len(post['sources'])} fonti")
    state = _state()
    for key, entry in state["posts"].items():
        print(f"STATO {key}: {entry['status']}")
    print("VALIDO: 5 caroselli indipendenti dalla coda settimanale. Nessun invio effettuato.")


def wait(index: int) -> None:
    """Assicura minimo 10 minuti dopo la precedente accettazione Buffer.

    In caso di ripresa il tempo gia' trascorso viene scalato.
    """
    name = _idx(index)
    obj = _state()
    if obj["posts"].get(name, {}).get("status") == "sent_to_buffer":
        print(name + " gia' inviato: nessuna attesa")
        return
    if index == 1:
        return
    previous = POSTS[index - 2]
    entry = obj["posts"].get(previous, {})
    if entry.get("status") != "sent_to_buffer" or not entry.get("sent_at"):
        raise p.PublisherError("Il post precedente non e' stato accettato da Buffer: " + previous)
    sent_at = datetime.fromisoformat(entry["sent_at"])
    if sent_at.tzinfo is None:
        raise p.PublisherError("Timestamp senza fuso orario nello stato")
    elapsed = (datetime.now(timezone.utc) - sent_at.astimezone(timezone.utc)).total_seconds()
    seconds = max(0, INTERVAL_SECONDS - elapsed)
    if seconds:
        print(f"Attesa di {int(seconds + 0.999)} secondi prima di {name}...", flush=True)
        time.sleep(seconds)


def reserve(index: int) -> None:
    """Prima salva lo stato riservato; il workflow lo committa prima della API Buffer."""
    _ensure_authorized()
    name = _idx(index)
    _inspect(name)
    obj = _state()
    record = obj["posts"].get(name)
    if record and record["status"] == "sent_to_buffer":
        print("GIA' INVIATO (nessun nuovo invio): " + name)
        return
    if record:
        raise p.PublisherError("INVIO SOSPESO, verificare Buffer prima di riprovare: " + name)
    if any(v["status"] == "reserved" for v in obj["posts"].values()):
        raise p.PublisherError("Esiste un invio precedente con esito incerto: blocco campagna")
    for previous in POSTS[:index - 1]:
        if obj["posts"].get(previous, {}).get("status") != "sent_to_buffer":
            raise p.PublisherError("Ordine violato: prima deve essere inviato " + previous)
    obj["posts"][name] = {
        "status": "reserved",
        "reserved_at": p.local_now().isoformat(),
    }
    _save_state(obj)
    print("RISERVATO su file (non ancora inviato a Buffer): " + name)


def send(index: int, repo: str, commit: str) -> None:
    _ensure_authorized()
    name = _idx(index)
    if not re.fullmatch(r"[a-zA-Z0-9_.-]+/[a-zA-Z0-9_.-]+", repo):
        raise p.PublisherError("Nome repository GitHub non valido")
    if not re.fullmatch(r"[0-9a-f]{40}", commit):
        raise p.PublisherError("SHA commit GitHub non valido")
    obj = _state()
    record = obj["posts"].get(name) or {}
    if record.get("status") != "reserved":
        raise p.PublisherError("Invio non riservato o gia' inviato: " + name)
    post = _inspect(name)
    prefix = f"https://raw.githubusercontent.com/{repo}/{commit}/posts/launch/{urllib.parse.quote(name)}/"
    urls = [prefix + image.name for image in post["images"]]
    # Se le immagini sono indisponibili, NON inviare alcuna chiamata mutativa.
    for url in urls:
        p.check_public_png(url)
    token = os.environ.get("BUFFER_API_KEY", "").strip()
    channel_id = p._channel(token)
    mutation = p.build_mutation(caption=post["caption"], channel_id=channel_id, urls=urls)
    # UNA chiamata a Buffer, senza retry dopo esito incerto.
    result = p._graphql(mutation, token)
    created = result.get("createPost") or {}
    if created.get("message"):
        raise p.PublisherError("Buffer ha rifiutato: " + str(created["message"])[:200])
    post_id = (created.get("post") or {}).get("id")
    if not post_id:
        raise p.PublisherError("Esito Buffer non confermato. Verificare Buffer prima di ripetere")
    record["status"] = "sent_to_buffer"
    record["buffer_post_id"] = str(post_id)
    record["sent_at"] = p.local_now().isoformat()
    _save_state(obj)
    print("CAROSELLO ACCETTATO DA BUFFER: " + name)
    print("Nota: verificare l'effettiva pubblicazione su Instagram.")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Lancio una tantum di 5 caroselli, ogni 10 minuti")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("validate")
    for operation in ("wait", "reserve", "send"):
        cmd = sub.add_parser(operation)
        cmd.add_argument("--index", required=True, type=int)
        if operation == "send":
            cmd.add_argument("--repo", required=True)
            cmd.add_argument("--commit", required=True)
    args = parser.parse_args(argv)
    try:
        if args.command == "validate":
            validate()
        elif args.command == "wait":
            wait(args.index)
        elif args.command == "reserve":
            reserve(args.index)
        else:
            send(args.index, args.repo, args.commit)
        return 0
    except (p.PublisherError, ValueError, OSError) as exc:
        print("BLOCCATO: " + str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
