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
MIN_SLIDES, MAX_SLIDES = 2, 20
MAX_CAPTION = 2200
IMAGE_RE = re.compile(r"^(\d{2})\.png$")
HASHTAG_RE = re.compile(r"(?<!\w)#[\w]+", re.UNICODE)
SECTION_RE = re.compile(r"^(?:CAPTION INSTAGRAM|HASHTAGS?|FONTI CONSULTABILI|NOTA EDITORIALE(?:\s*\(.*\))?)$", re.IGNORECASE)
DEFAULT_HASHTAGS = {
    "buona": ("#NotiziePositive", "#BuoneNotizie", "#Notizie"),
    "cattiva": ("#Notizie", "#Attualita", "#Mondo"),
    "curiosita": ("#Misteri", "#Curiosita", "#Cultura"),
}


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


def _check_urls(urls: list[str], origin: str) -> list[str]:
    if len(urls) < 2:
        raise PublisherError(f"Servono almeno due link alle fonti in {origin}")
    hosts: set[str] = set()
    for url in urls:
        parsed = urllib.parse.urlparse(url)
        host = (parsed.hostname or "").lower().removeprefix("www.")
        if parsed.scheme != "https" or not host or "." not in host or parsed.username or parsed.password:
            raise PublisherError(f"Fonte non HTTPS o non valida in {origin}")
        hosts.add(host)
    if len(hosts) < 2:
        raise PublisherError(f"Indicare fonti di almeno due domini differenti: {origin}")
    # Questo controlla solo il formato, non l'accuratezza degli articoli.
    return urls


def _check_sources(path: Path) -> list[str]:
    if not path.is_file():
        raise PublisherError(f"Manca sources.txt in {path.parent.name}")
    urls = [line.strip() for line in path.read_text(encoding="utf-8-sig").splitlines()
            if line.strip() and not line.lstrip().startswith("#")]
    return _check_urls(urls, str(path))


def _slides(folder: Path) -> list[Path]:
    files = list(folder.glob("*.png"))
    unnumbered = [f.name for f in files if not IMAGE_RE.fullmatch(f.name)]
    if unnumbered:
        raise PublisherError(f"Nome immagine non valido in {folder.name}: {', '.join(sorted(unnumbered))}")
    count = len(files)
    if not MIN_SLIDES <= count <= MAX_SLIDES:
        raise PublisherError(f"{folder.name}: il carosello richiede da {MIN_SLIDES} a {MAX_SLIDES} immagini PNG")
    images = [folder / f"{i:02d}.png" for i in range(1, count + 1)]
    if set(files) != set(images):
        raise PublisherError(f"Numerazione delle immagini non consecutiva in {folder.name}: usare 01.png, 02.png, ...")
    for path in images:
        _image_size(path)
    return images


def _compose_caption(description: str, tags: list[str], category: str) -> str:
    description = description.strip()
    if not description:
        raise PublisherError("La descrizione Instagram e' vuota")
    # Il bot assembla soltanto testi verificati e hashtag espliciti; non inventa fatti.
    existing = {tag.casefold() for tag in HASHTAG_RE.findall(description)}
    extra = []
    for tag in tags:
        if not HASHTAG_RE.fullmatch(tag):
            raise PublisherError(f"Hashtag non valido: {tag!r}")
        if tag.casefold() not in existing:
            extra.append(tag)
            existing.add(tag.casefold())
    if not existing:
        extra = list(DEFAULT_HASHTAGS[category])
    result = description + ("\n\n" + " ".join(extra) if extra else "")
    if not 30 <= len(result) <= MAX_CAPTION:
        raise PublisherError(f"La didascalia deve contenere 30-{MAX_CAPTION} caratteri (attuali: {len(result)})")
    return result


def _section(lines: list[str], title: str) -> str:
    found = False
    collected: list[str] = []
    for line in lines:
        stripped = line.strip()
        if SECTION_RE.fullmatch(stripped):
            if found:
                break
            if stripped.casefold() == title.casefold():
                found = True
            continue
        if found and not re.fullmatch(r"=+", stripped):
            collected.append(line)
    if not found:
        raise PublisherError(f"Sezione {title} mancante nel testo editoriale")
    return "\n".join(collected).strip()


def parse_editorial(path: Path, category: str) -> tuple[str, list[str]]:
    text = path.read_text(encoding="utf-8-sig")
    lines = text.splitlines()
    description = _section(lines, "CAPTION INSTAGRAM")
    hashtag_lines = _section(lines, "HASHTAG")
    tags = HASHTAG_RE.findall(hashtag_lines)
    source_text = _section(lines, "FONTI CONSULTABILI")
    urls = [u.rstrip(".,;") for u in re.findall(r"https://[^\s<>]+", source_text)]
    caption = _compose_caption(description, tags, category)
    return caption, urls


def _from_editorial(path: Path, category: str) -> tuple[str, list[str]]:
    caption, urls = parse_editorial(path, category)
    return caption, _check_urls(urls, path.name)


def compose_editorial(path: Path, category: str, out: Path | None = None) -> None:
    if category not in CATEGORIES:
        raise PublisherError(f"Categoria non supportata: {category}")
    if not path.is_file():
        raise PublisherError(f"File editoriale non trovato: {path}")
    caption, urls = parse_editorial(path, category)
    print("=== DIDASCALIA INSTAGRAM ===")
    print(caption)
    print("\n=== FONTI INDICATE NEL FILE ===")
    for url in urls:
        print(url)
    try:
        _check_urls(urls, path.name)
        print("\nControllo formale dei riferimenti: OK (non e' un fact-check)")
    except PublisherError as exc:
        print(f"\nATTENZIONE: {exc}. Correggere le fonti prima della pubblicazione.")
    if out is not None:
        if out.exists() and any((out / name).exists() for name in ("caption.txt", "sources.txt")):
            raise PublisherError("File di destinazione gia' presenti: non sovrascrivo caption.txt o sources.txt")
        out.mkdir(parents=True, exist_ok=True)
        (out / "caption.txt").write_text(caption + "\n", encoding="utf-8")
        (out / "sources.txt").write_text("\n".join(urls) + "\n", encoding="utf-8")
        print("Caption e fonti esportate in:", out)


def _post_text(folder: Path, category: str) -> tuple[str, list[str]]:
    caption_path, sources_path = folder / "caption.txt", folder / "sources.txt"
    if caption_path.exists() or sources_path.exists():
        # Modalita' semplice: due file precompilati, piu' hashtags.txt facoltativo.
        if not caption_path.is_file() or not sources_path.is_file():
            raise PublisherError(f"{folder.name}: servono sia caption.txt sia sources.txt")
        tags_path = folder / "hashtags.txt"
        tags = HASHTAG_RE.findall(tags_path.read_text(encoding="utf-8-sig")) if tags_path.is_file() else []
        return _compose_caption(caption_path.read_text(encoding="utf-8-sig"), tags, category), _check_sources(sources_path)
    # Modalita' editoriale: riutilizza direttamente il TXT del Template.zip.
    # La nota editoriale e le spiegazioni delle slide non confluiscono nel post.
    files = sorted(folder.glob("*.txt"))
    if len(files) != 1:
        raise PublisherError(f"{folder.name}: inserire caption.txt + sources.txt oppure un solo TXT editoriale")
    return _from_editorial(files[0], category)


def inspect_post(folder: Path) -> dict:
    match = NAME_RE.fullmatch(folder.name)
    if not match:
        raise PublisherError(f"Nome cartella non valido: {folder.name} (es. 001_buona_esempio)")
    images = _slides(folder)
    caption, sources = _post_text(folder, match.group(2))
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
        print(f"Prossimo: {chosen['id']} | categoria: {chosen['category']} | {len(chosen['images'])} PNG | fonti: {len(chosen['sources'])}")
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
    if not MIN_SLIDES <= len(urls) <= MAX_SLIDES or any(not u.startswith("https://") for u in urls):
        raise PublisherError(f"Il carosello richiede da {MIN_SLIDES} a {MAX_SLIDES} URL HTTPS")
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
    caption_cmd = cmd.add_parser("caption", help="Mostra la didascalia completa generata per un carosello")
    caption_cmd.add_argument("--post", required=True, help="Nome completo della cartella in coda")
    compose_cmd = cmd.add_parser("compose", help="Assembla una caption con hashtag dal TXT editoriale, senza immagini o API")
    compose_cmd.add_argument("--file", required=True, type=Path)
    compose_cmd.add_argument("--category", required=True, choices=sorted(CATEGORIES))
    compose_cmd.add_argument("--out", type=Path, help="Esporta caption.txt e sources.txt nella cartella indicata")
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
        elif args.command == "caption":
            item = next((x for x in scan_queue() if x["id"] == args.post), None)
            if item is None:
                raise PublisherError(f"Carosello non presente: {args.post}")
            print(item["caption"])
            print("\n--- Fonti registrate (non aggiunte alla didascalia) ---")
            print("\n".join(item["sources"]))
        elif args.command == "compose":
            compose_editorial(args.file, args.category, args.out)
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
