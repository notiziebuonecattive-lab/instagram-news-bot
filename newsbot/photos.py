"""Acquisizione foto illustrative Wikimedia Commons, con controllo licenza e credito.

Se una fotografia pertinente e riutilizzabile non è verificabile, il post viene bloccato.
Le fotografie non sono mai presentate come scatti documentali dell'evento.
"""
from __future__ import annotations

import io
import re
from pathlib import Path
from urllib.parse import quote, urlsplit

import requests
from bs4 import BeautifulSoup
from PIL import Image, ImageOps

COMMONS_API = "https://commons.wikimedia.org/w/api.php"
HEADERS = {"User-Agent": "NotizieBuoneCattive/3.0 (educational Instagram news bot; commons image search)"}
# CC BY-SA è volutamente esclusa: immagini adattate possono avere obblighi
# di condivisione con la stessa licenza che richiedono un flusso dedicato.
ALLOWED = re.compile(r"^(?:CC0(?:[ -]1\.0)?|CC BY(?:[ -](?:2\.0|2\.5|3\.0|4\.0))?|Public domain|PD(?:-|$))", re.I)


class PhotoError(RuntimeError):
    pass


def _field(metadata: dict, field: str) -> str:
    raw = metadata.get(field) or {}
    val = raw.get("value", "") if isinstance(raw, dict) else ""
    return BeautifulSoup(str(val), "html.parser").get_text(" ", strip=True)


def search_photo(keywords: str, *, session=None, limit: int = 18) -> dict:
    """Cerca una foto relativa all'argomento, senza fingere che rappresenti il fatto."""
    if not isinstance(keywords, str) or not 4 <= len(keywords.strip()) <= 90:
        raise PhotoError("Parole chiave fotografiche non valide")
    words = re.findall(r"[A-Za-zÀ-ÿ0-9-]+", keywords)
    if not 2 <= len(words) <= 8:
        raise PhotoError("Specificare 2-8 parole chiave per la fotografia")
    query = " ".join(words) + " filetype:bitmap"
    session = session or requests.Session()
    try:
        result = session.get(COMMONS_API, params={
            "action": "query", "format": "json", "formatversion": "2",
            "generator": "search", "gsrsearch": query, "gsrnamespace": 6,
            "gsrlimit": min(limit, 40), "prop": "imageinfo", "iiprop": "url|mime|size|extmetadata",
            "iiurlwidth": 1500,
        }, headers=HEADERS, timeout=25)
        result.raise_for_status()
        pages = result.json().get("query", {}).get("pages", [])
    except (requests.RequestException, ValueError, AttributeError) as exc:
        raise PhotoError("Ricerca immagini Wikimedia Commons non disponibile") from exc
    for page in sorted(pages, key=lambda x: x.get("index", 10_000)):
        info = (page.get("imageinfo") or [{}])[0]
        if info.get("mime") not in ("image/jpeg", "image/png", "image/webp"):
            continue
        if info.get("width", 0) < 800 or info.get("height", 0) < 550:
            continue
        meta = info.get("extmetadata") or {}
        license_name = _field(meta, "LicenseShortName")
        if not ALLOWED.match(license_name) or "SA" in license_name.upper():
            continue
        if _field(meta, "Restrictions"):
            continue
        image_url = info.get("thumburl") or info.get("url", "")
        if not image_url.startswith("https://upload.wikimedia.org/"):
            continue
        page_title = str(page.get("title", ""))
        if not page_title.startswith("File:"):
            continue
        # Preleva i crediti dalle informazioni pubblicate dal titolare.
        author = _field(meta, "Artist") or _field(meta, "Credit")
        if not author and "CC BY" in license_name.upper():
            continue
        attribution = {
            "source_page": "https://commons.wikimedia.org/wiki/" + quote(page_title.replace(" ", "_"), safe=":()_-"),
            "author": author or "Wikimedia Commons",
            "license": license_name,
            "license_url": _field(meta, "LicenseUrl"),
            "title": page_title.removeprefix("File:"),
            "illustrative": True,
        }
        return {"url": image_url, "attribution": attribution}
    raise PhotoError("Nessuna fotografia adatta con licenza compatibile: pubblicazione bloccata")


def download_photo(photo: dict, destination: Path, *, session=None) -> None:
    url = photo["url"]
    if urlsplit(url).hostname != "upload.wikimedia.org" or not url.startswith("https://"):
        raise PhotoError("Fonte immagine non autorizzata")
    session = session or requests.Session()
    try:
        response = session.get(url, timeout=28, headers=HEADERS, stream=True, allow_redirects=False)
        response.raise_for_status()
        if response.status_code != 200 or not response.headers.get("Content-Type", "").startswith("image/"):
            raise PhotoError("La risorsa fotografica non è un'immagine")
        raw = bytearray()
        for chunk in response.iter_content(chunk_size=65536):
            raw.extend(chunk)
            if len(raw) > 12_000_000:
                raise PhotoError("Fotografia troppo grande")
        with Image.open(io.BytesIO(raw)) as image:
            image = ImageOps.exif_transpose(image)
            if image.width < 800 or image.height < 550:
                raise PhotoError("Fotografia con risoluzione insufficiente")
            destination.parent.mkdir(parents=True, exist_ok=True)
            image.convert("RGB").save(destination, "JPEG", quality=88, optimize=True)
    except (requests.RequestException, OSError) as exc:
        raise PhotoError("Impossibile scaricare la fotografia") from exc
    finally:
        if "response" in locals():
            response.close()
