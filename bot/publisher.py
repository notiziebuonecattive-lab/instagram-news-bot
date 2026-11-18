"""Coda editoriale GitHub -> Buffer, senza generazione IA e senza dipendenze esterne.

La mutazione Buffer è intenzionalmente eseguita una sola volta. Prima della
richiesta, il post viene riservato con un commit dal workflow GitHub: se il
processo termina senza conoscere l'esito, la coda si blocca e richiede
riconciliazione manuale, invece di rischiare un duplicato.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import struct
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
QUEUE = ROOT / "posts" / "queue"
STATE_FILE = ROOT / "data" / "state.json"
BUFFER_ENDPOINT = "https://api.buffer.com"
ROME = ZoneInfo("Europe/Rome")
CATEGORIES = {"buona", "cattiva", "curiosita"}
NAME_RE = re.compile(r"^(\d{3})_(buona|cattiva|curiosita)_[a-z0-9][a-z0-9_-]*$")
PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
MAX_IMAGE_BYTES = 18 * 1024 * 1024


class PublisherError(RuntimeError):
    """Un contenuto incompleto o un'azione rischiosa blocca la pubblicazione."""


def local_now() -> datetime:
    return datetime.now(ROME)


def _image_size(path: Path) -> tuple[int, int]:
    if not path.is_file() or path.stat().st_size < 40 or path.stat().st_size > MAX_IMAGE_BYTES:
        raise PublisherError(f"Immagine mancante o di dimensioni non ammesse: {path}")
    with path.open("rb") as f:
        head = f.read(33)
    if head[:8] != PNG_SIGNATURE or head[12:16] != b"IHDR":
        raise PublisherError(f"PNG non valido: {path}")
    width, height = struct.unpack(">II", head[16:24])
    if (width, height) != (1080, 1350):
        raise PublisherError(f"Dimensioni errate per {path.name}: {width}x{height}; richiesto 1080x1350")
    return width, height


def _check_sources(path: Path) -> list[str]:
    if not path.is_file():
        raise PublisherError(f"Manca sources.txt in {path.parent.name}")
    urls = [line.strip() for line in path.read_text(encoding="utf-8-sig").splitlines()
            if line.strip() and not line.lstrip().startswith("#")]
    if len(urls) < 2:
        raise PublisherError(f"Servono almeno due link alle fonti in {path}")
    hosts: set[str] = set()
    for url in urls:
        parsed = urllib.parse.urlparse(url)
        host = (parsed.hostname or "").lower().removeprefix("www.")
        if parsed.scheme != "https" or not host or "." not in host or parsed.username or parsed.password:
            raise PublisherError(f"Fonte non HTTPS o non valida in {path}")
        hosts.add(host)
    if len(hosts) < 2:
        raise PublisherError(f"Indicare fonti di almeno due domini differenti: {path}")
    # Due domini diversi non garantiscono in sé indipendenza o accuratezza.
    return urls


def inspect_post(folder: Path) -> dict:
    match = NAME_RE.fullmatch(folder.name)
    if not match:
        raise PublisherError(f"Nome cartella non valido: {folder.name} (es. 001_buona_esempio)")
    images = [folder / f"0{i}.png" for i in (1, 2, 3)]
    for path in images:
        _image_size(path)
    caption_path = folder / "caption.txt"
    if not caption_path.is_file():
        raise PublisherError(f"Manca caption.txt in {folder.name}")
    caption = caption_path.read_text(encoding="utf-8-sig").strip()
    if not 30 <= len(caption) <= 2200:
        raise PublisherError(f"La didascalia di {folder.name} deve contenere 30–2200 caratteri")
    if "#" not in caption:
        raise PublisherError(f"La didascalia di {folder.name} non contiene hashtag")
    sources = _check_sources(folder / "sources.txt")
    return {"id": folder.name, "sequence": int(match.group(1)), "category": match.group(2),
            "images": images, "caption": caption, "sources": sources}


def scan_queue() -> list[dict]:
    if not QUEUE.exists():
        return []
    folders = sorted((p for p in QUEUE.iterdir() if p.is_dir()), key=lambda p: p.name)
    posts = [inspect_post(p) for p in folders]
    sequences = [p["sequence"] for p in posts]
    if len(sequences) != len(set(sequences)):
        raise PublisherError("Numeri di coda duplicati: ogni cartella deve avere un numero progressivo unico")
    return sorted(posts, key=lambda p: (p["sequence"], p["id"]))


def load_state() -> dict:
    if not STATE_FILE.exists():
        return {"posts": {}, "slots": {}}
    obj = json.loads(STATE_FILE.read_text(encoding="utf-8"))
    if not isinstance(obj, dict) or not isinstance(obj.get("posts"), dict) or not isinstance(obj.get("slots"), dict):
        raise PublisherError("data/state.json non valido")
    return obj


def save_state(state: dict) -> None:
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    temp = STATE_FILE.with_suffix(".json.tmp")
    temp.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temp.replace(STATE_FILE)


def pick_next(posts: list[dict], state: dict) -> dict | None:
    # NON passare ad altri post se un invio precedente ha un esito incerto.
    blocked = [name for name, entry in state["posts"].items() if entry.get("status") == "reserved"]
    if blocked:
        raise PublisherError("Invio precedente da controllare manualmente: " + ", ".join(blocked))
    return next((post for post in posts if post["id"] not in state["posts"]), None)


def print_plan() -> None:
    posts = scan_queue()
    state = load_state()
    complete = sum(1 for entry in state["posts"].values() if entry.get("status") == "sent_to_buffer")
    print(f"Caroselli in repository: {len(posts)} | Accettati da Buffer: {complete}")
    try:
        chosen = pick_next(posts, state)
    except PublisherError as exc:
        print(f"BLOCCATO: {exc}")
        return
    if chosen:
        print(f"Prossimo: {chosen['id']} | categoria: {chosen['category']} | 3 PNG | fonti: {len(chosen['sources'])}")
    else:
        print("Non ci sono nuovi caroselli pronti da pubblicare")


def _output(value: bool, post: str = "") -> None:
    path = os.getenv("GITHUB_OUTPUT", "")
    if path:
        with open(path, "a", encoding="utf-8") as f:
            f.write("selected=" + ("true" if value else "false") + "\n")
            if value:
                f.write("post_id=" + post + "\n")


def reserve(*, manual: bool = False) -> bool:
    if os.environ.get("ALLOW_PUBLISH", "false").lower() != "true":
        raise PublisherError("Blocco di sicurezza: Repository Variable ALLOW_PUBLISH non è true")
    now = local_now()
    if not manual and (now.weekday() not in (1, 4) or (now.hour, now.minute) < (12, 0)):
        # Difesa nel caso in cui un cron venisse eseguito fuori orario.
        print("Nessuna pubblicazione: non è martedì/venerdì dopo le 12:00 in Italia")
        _output(False)
        return False
    state = load_state()
    slot = now.date().isoformat()
    if slot in state["slots"]:
        print("Slot di oggi già utilizzato, nessun nuovo invio:", slot)
        _output(False)
        return False
    chosen = pick_next(scan_queue(), state)
    if chosen is None:
        print("Coda vuota; nessuna pubblicazione")
        _output(False)
        return False
    state["posts"][chosen["id"]] = {"status": "reserved", "reserved_at": now.isoformat(), "slot": slot}
    state["slots"][slot] = chosen["id"]
    save_state(state)
    _output(True, chosen["id"])
    print("Prenotato (nessun invio a Buffer):", chosen["id"])
    return True


def _graphql(query: str, token: str) -> dict:
    if not token:
        raise PublisherError("BUFFER_API_KEY assente nei GitHub Secrets")
    req = urllib.request.Request(
        BUFFER_ENDPOINT,
        data=json.dumps({"query": query}, ensure_ascii=False).encode("utf-8"),
        headers={"Authorization": "Bearer " + token, "Content-Type": "application/json"},
        method="POST")
    try:
        with urllib.request.urlopen(req, timeout=40) as res:
            payload = json.loads(res.read(1000000))
    except (urllib.error.URLError, TimeoutError, OSError, ValueError) as exc:
        # Non riprovare una mutazione con esito incerto: potrebbe essere stata accettata.
        raise PublisherError(f"Risposta Buffer non disponibile o incerta: {type(exc).__name__}") from exc
    if payload.get("errors"):
        raise PublisherError("Buffer GraphQL: " + str(payload["errors"][0].get("message", "errore"))[:200])
    return payload.get("data") or {}


def _channel(token: str) -> str:
    fixed = os.getenv("BUFFER_CHANNEL_ID", "").strip()
    if fixed:
        data = _graphql("query { channel(input: { id: " + json.dumps(fixed) + " }) { id name service } }", token)
        c = data.get("channel") or {}
        if str(c.get("service", "")).lower() != "instagram":
            raise PublisherError("BUFFER_CHANNEL_ID non corrisponde a un canale Instagram")
        return str(c["id"])
    data = _graphql("query { account { organizations { id name } } }", token)
    found: list[dict] = []
    for org in (data.get("account") or {}).get("organizations", []):
        query = "query { channels(input: { organizationId: " + json.dumps(org["id"]) + " }) { id name service } }"
        found.extend(c for c in (_graphql(query, token).get("channels") or [])
                     if str(c.get("service", "")).lower() == "instagram")
    if len(found) != 1:
        raise PublisherError(f"Trovati {len(found)} canali Instagram; specifica BUFFER_CHANNEL_ID se necessario")
    return str(found[0]["id"])


def build_mutation(*, caption: str, channel_id: str, urls: list[str]) -> str:
    if len(urls) != 3 or any(not u.startswith("https://") for u in urls):
        raise PublisherError("Il carosello richiede tre URL HTTPS")
    assets = ", ".join("{image: {url: " + json.dumps(u) + "}}" for u in urls)
    return ("mutation { createPost(input: {text: " + json.dumps(caption, ensure_ascii=False)
            + " channelId: " + json.dumps(channel_id) + " schedulingType: automatic mode: shareNow assets: ["
            + assets + "]}) { ... on PostActionSuccess { post { id } } ... on MutationError { message } } }")


def media_urls(post: dict, *, repo: str, commit: str) -> list[str]:
    if not re.fullmatch(r"[a-zA-Z0-9_.-]+/[a-zA-Z0-9_.-]+", repo):
        raise PublisherError("GITHUB_REPOSITORY non valido")
    if not re.fullmatch(r"[0-9a-f]{40}", commit):
        raise PublisherError("SHA commit non valido: usare il commit corrente dopo la prenotazione")
    root = f"https://raw.githubusercontent.com/{repo}/{commit}/posts/queue/"
    return [root + urllib.parse.quote(post["id"]) + "/" + file.name for file in post["images"]]


def check_public_png(url: str) -> None:
    req = urllib.request.Request(url, headers={"User-Agent": "InstagramNewsBot/4.0", "Range": "bytes=0-32"})
    try:
        with urllib.request.urlopen(req, timeout=30) as res:
            head = res.read(33)
            if res.status not in (200, 206) or not head.startswith(PNG_SIGNATURE):
                raise PublisherError("Immagine pubblica non valida: " + url)
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise PublisherError("Immagine pubblica non accessibile: " + url) from exc


def send(*, repo: str, commit: str, post_id: str) -> None:
    if os.environ.get("ALLOW_PUBLISH", "false").lower() != "true":
        raise PublisherError("Blocco di sicurezza ALLOW_PUBLISH")
    state = load_state()
    record = state["posts"].get(post_id) or {}
    if record.get("status") != "reserved":
        raise PublisherError("Post non riservato o già inviato: stop")
    # Il workflow esegue questa fase soltanto dopo aver registrato la prenotazione su main.
    selected = next((p for p in scan_queue() if p["id"] == post_id), None)
    if not selected:
        raise PublisherError("Cartella del post riservato non trovata")
    urls = media_urls(selected, repo=repo, commit=commit)
    for url in urls:
        check_public_png(url)
    token = os.environ.get("BUFFER_API_KEY", "").strip()
    channel = _channel(token)
    query = build_mutation(caption=selected["caption"], channel_id=channel, urls=urls)
    # Una mutazione senza retry: se l'esito è ignoto, lo status rimane reserved.
    response = _graphql(query, token)
    created = response.get("createPost") or {}
    if created.get("message"):
        raise PublisherError("Buffer ha rifiutato il carosello: " + str(created["message"])[:200])
    returned = (created.get("post") or {}).get("id")
    if not returned:
        raise PublisherError("Esito Buffer non confermato: verificare Buffer prima di procedere")
    record["status"] = "sent_to_buffer"
    record["buffer_post_id"] = str(returned)
    record["sent_at"] = local_now().isoformat()
    save_state(state)
    print("Carosello accettato da Buffer (non è una conferma di pubblicazione su Instagram):", post_id)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Pubblicazione caroselli verificati, senza IA")
    cmd = parser.add_subparsers(dest="command", required=True)
    cmd.add_parser("validate", help="Controlla ogni post e la sua struttura senza chiamate API")
    cmd.add_parser("plan", help="Mostra la prossima pubblicazione senza chiamate API")
    reserve_cmd = cmd.add_parser("reserve", help="Prenota un post prima di inviarlo a Buffer")
    reserve_cmd.add_argument("--manual", action="store_true")
    send_cmd = cmd.add_parser("send", help="Invia una sola volta il post già riservato")
    send_cmd.add_argument("--repo", required=True)
    send_cmd.add_argument("--commit", required=True)
    send_cmd.add_argument("--post", required=True)
    args = parser.parse_args(argv)
    try:
        if args.command == "validate":
            posts = scan_queue()
            print(f"Validazione completata: {len(posts)} caroselli integri. Nessuna pubblicazione.")
        elif args.command == "plan":
            print_plan()
        elif args.command == "reserve":
            reserve(manual=args.manual)
        elif args.command == "send":
            send(repo=args.repo, commit=args.commit, post_id=args.post)
        return 0
    except (PublisherError, ValueError, OSError, json.JSONDecodeError) as exc:
        print("OPERAZIONE BLOCCATA:", str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
