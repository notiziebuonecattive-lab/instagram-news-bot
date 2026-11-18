"""Controlli conservativi: link autentici, autori diversi, date recenti e duplicati."""
import hashlib
import ipaddress
import json
import re
from datetime import date, datetime, timedelta, timezone
from urllib.parse import urlsplit, urljoin, urlunsplit

import requests
from bs4 import BeautifulSoup


class ValidationError(ValueError):
    pass


def safe_https_url(url: str) -> str:
    if not isinstance(url, str) or len(url) > 1500:
        raise ValidationError("URL non valido")
    u = urlsplit(url)
    if u.scheme != "https" or u.username or u.password or not u.hostname or "." not in u.hostname:
        raise ValidationError("URL esterno HTTPS richiesto")
    host = u.hostname.lower()
    if host.endswith((".local", ".internal", ".test", ".example")):
        raise ValidationError("Dominio non pubblico")
    try:
        ipaddress.ip_address(host)
    except ValueError:
        pass
    else:
        raise ValidationError("Non sono accettati indirizzi IP nei link delle fonti")
    return urlunsplit((u.scheme, u.netloc, u.path or '/', u.query, ''))


def publisher_domain(url: str) -> str:
    host = (urlsplit(url).hostname or "").lower().removeprefix("www.")
    parts = host.split(".")
    suffixes = {"co.uk", "com.au", "co.nz", "com.br", "co.jp", "com.cn"}
    if len(parts) >= 3 and ".".join(parts[-2:]) in suffixes:
        return ".".join(parts[-3:])
    return ".".join(parts[-2:]) if len(parts) >= 2 else host


def _parse_date(value: object) -> date | None:
    if not isinstance(value, str):
        return None
    try:
        return date.fromisoformat(value[:10])
    except (ValueError, TypeError):
        return None


def _published(soup: BeautifulSoup) -> date | None:
    for key, name in [("property", "article:published_time"), ("name", "datePublished"),
                      ("itemprop", "datePublished"), ("name", "pubdate"),
                      ("property", "og:published_time"), ("name", "date")]:
        tag = soup.find("meta", attrs={key: name})
        if tag and _parse_date(tag.get("content")):
            return _parse_date(tag.get("content"))
    for tag in soup.find_all("script", attrs={"type": "application/ld+json"}, limit=15):
        try:
            root = json.loads(tag.string or tag.get_text())
        except (ValueError, TypeError):
            continue
        def explore(o):
            if isinstance(o, dict):
                if _parse_date(o.get("datePublished")):
                    return _parse_date(o["datePublished"])
                for v in o.values():
                    x = explore(v)
                    if x:
                        return x
            elif isinstance(o, list):
                for v in o:
                    x = explore(v)
                    if x:
                        return x
            return None
        found = explore(root)
        if found:
            return found
    for t in soup.select("time[datetime]")[:10]:
        if _parse_date(t.get("datetime")):
            return _parse_date(t["datetime"])
    return None


def fetch_article(url: str, *, today: date | None = None, session=None) -> dict:
    today = today or date.today()
    url = safe_https_url(url)
    session = session or requests.Session()
    # Evita che un redirect porti a endpoint locali.
    for _ in range(4):
        try:
            response = session.get(url, timeout=18, allow_redirects=False, headers={
                "User-Agent": "Mozilla/5.0 (compatible; InstagramNewsBot/1.0; research)"
            }, stream=True)
        except requests.RequestException as exc:
            raise ValidationError("Fonte non raggiungibile") from exc
        if response.status_code in (301, 302, 303, 307, 308):
            dest = response.headers.get("Location")
            response.close()
            if not dest:
                raise ValidationError("Redirect non valido")
            url = safe_https_url(urljoin(url, dest))
            continue
        break
    else:
        raise ValidationError("Troppi redirect")
    try:
        response.raise_for_status()
        ctype = response.headers.get("Content-Type", "")
        if "html" not in ctype.lower():
            raise ValidationError("La fonte non è un articolo HTML")
        raw = bytearray()
        for chunk in response.iter_content(chunk_size=16384):
            raw.extend(chunk)
            if len(raw) > 1_200_000:
                raise ValidationError("Pagina troppo grande")
        soup = BeautifulSoup(bytes(raw), "html.parser")
    except requests.RequestException as exc:
        raise ValidationError("Fonte non accessibile") from exc
    finally:
        response.close()
    published = _published(soup)
    if not published or not (today - timedelta(days=10) <= published <= today + timedelta(days=1)):
        raise ValidationError("Data di pubblicazione non verificabile o troppo vecchia")
    for element in soup(["script", "style", "nav", "footer", "header", "aside"]):
        element.decompose()
    text = " ".join(soup.stripped_strings)
    if len(text) < 450:
        raise ValidationError("Testo della fonte insufficiente o bloccato")
    return {"url": url, "published_at": published.isoformat(), "text": text[:7500]}


def normalized(text: str) -> set[str]:
    return {x for x in re.findall(r"[a-zà-ÿ0-9]+", text.lower()) if len(x) >= 4}


def ensure_not_duplicate(story: dict, state: dict) -> None:
    title = normalized(story["headline"])
    candidate_urls = {x['url'].split('?')[0].rstrip('/') for x in story["sources"]}
    for old in state.get("items", []):
        old_urls = {x.get("url", "").split('?')[0].rstrip('/') for x in old.get("sources", [])}
        if candidate_urls & old_urls:
            raise ValidationError("Una fonte della notizia è già stata utilizzata")
        words = normalized(old.get("headline", ""))
        if words and title and len(title & words) / len(title | words) >= .55:
            raise ValidationError("Notizia probabilmente già trattata")


def validate_structure(story: dict, kind: str, state: dict, *, today: date | None = None) -> dict:
    today = today or date.today()
    headline, summary = story.get("headline"), story.get("summary")
    if not isinstance(headline, str) or not 12 <= len(headline.strip()) <= 105:
        raise ValidationError("Titolo mancante o troppo lungo")
    if not isinstance(summary, str) or not 70 <= len(summary.split()) <= 185:
        raise ValidationError("Didascalia fuori limiti (70–185 parole)")
    edate = _parse_date(story.get("event_date"))
    if not edate or not (today - timedelta(days=14) <= edate <= today + timedelta(days=1)):
        raise ValidationError("Data della notizia non recente")
    sources = story.get("sources")
    if not isinstance(sources, list) or len(sources) < 2:
        raise ValidationError("Mancano due fonti")
    domains = set()
    clean_sources = []
    for source in sources[:3]:
        if not isinstance(source, dict):
            raise ValidationError("Fonte non valida")
        url = safe_https_url(source.get("url", ""))
        domain = publisher_domain(url)
        if domain in domains:
            raise ValidationError("Due fonti provengono dallo stesso editore/dominio")
        domains.add(domain)
        publisher = str(source.get("publisher", "")).strip()[:80]
        if len(publisher) < 3:
            raise ValidationError("Nome dell'editore mancante")
        supplied_date = _parse_date(source.get("published_at"))
        if not supplied_date or not (today - timedelta(days=10) <= supplied_date <= today + timedelta(days=1)):
            raise ValidationError("Data della fonte mancante o troppo vecchia")
        clean_sources.append({"url": url, "publisher": publisher, "published_at": supplied_date.isoformat()})
    tags = story.get("hashtags")
    if not isinstance(tags, list) or not 2 <= len(tags) <= 6 or not all(
            isinstance(x, str) and re.fullmatch(r"#[\wà-ÿ]+", x, flags=re.I) for x in tags):
        raise ValidationError("Hashtag non validi")
    result = {"headline": headline.strip(), "summary": summary.strip(),
              "event_date": edate.isoformat(), "sources": clean_sources,
              "hashtags": tags, "kind": kind}
    ensure_not_duplicate(result, state)
    digest = hashlib.sha256((kind + ":" + clean_sources[0]["url"].split('?')[0]).encode()).hexdigest()[:16]
    result["id"] = digest
    if any(x.get("id") == digest for x in state.get("items", [])):
        raise ValidationError("ID già presente nello storico")
    return result


def check_sources(story: dict, *, today: date | None = None) -> list[dict]:
    checked = []
    for s in story["sources"]:
        data = fetch_article(s["url"], today=today)
        claimed = _parse_date(s["published_at"])
        actual = _parse_date(data["published_at"])
        if abs((claimed - actual).days) > 2:
            raise ValidationError("Data dichiarata incoerente con quella dell'articolo")
        checked.append(data)
    return checked
