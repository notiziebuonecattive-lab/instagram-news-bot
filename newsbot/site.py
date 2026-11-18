"""Archivio pubblico con riferimenti alle notizie e attribuzioni fotografiche."""
from html import escape
from pathlib import Path

STYLE = """
:root{font-family:system-ui,-apple-system,Segoe UI,sans-serif;background:#f7f8f7;color:#1d2b30}
*{box-sizing:border-box}body{margin:0}.wrap{max-width:1040px;margin:auto;padding:28px 18px}
header{border-bottom:1px solid #ced9dc;padding:22px 0 35px}h1{font-size:clamp(2rem,5vw,3.4rem);margin:.2em 0;letter-spacing:-.05em}
p{line-height:1.65}.muted,small{color:#57666d}.intro{max-width:710px}h2{margin:35px 0 20px}
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(260px,1fr));gap:20px}
article{background:#fff;border:1px solid #dde3e5;border-radius:20px;overflow:hidden;box-shadow:0 2px 12px #0001}
article img{display:block;width:100%;height:auto}.content{padding:19px}article h3{font-size:1.3rem;line-height:1.25}
.tag{font-size:.8rem;font-weight:800;letter-spacing:.06em;color:#236946}
.tag.negative{color:#99363c}.tag.curiosity{color:#18749e}
li{margin:7px 0}a{color:#195974;overflow-wrap:anywhere}footer{border-top:1px solid #dde3e5;margin-top:55px;padding:24px 0}
"""
LABELS = {"positive": "NOTIZIE BUONE", "negative": "NOTIZIE CATTIVE", "curiosity": "CURIOSITÀ"}


def create_index(folder: Path, state: dict, preview: list[dict] | None = None) -> None:
    folder.mkdir(parents=True, exist_ok=True)
    items = (preview or []) + list(reversed(state.get("items", [])))
    cards = []
    for item in items[:80]:
        kind = item["kind"]
        label = LABELS.get(kind, kind)
        cls = f" {kind}" if kind != "positive" else ""
        image = escape(item.get("image", ""), quote=True)
        images = item.get("images") or [item.get("image", "")]
        links = " ".join(f'<a href="{escape(path, quote=True)}" target="_blank" rel="noopener">Slide {i}</a>'
                         for i, path in enumerate(images, 1) if path)
        carousel = f'<p class="muted">Carosello: {links}</p>' if len(images) > 1 else ""
        sources = item.get("sources") or []
        references = "".join(
            '<li><a href="' + escape(src["url"], quote=True) + '" rel="noopener noreferrer" target="_blank">'
            + escape(src["publisher"]) + "</a> · " + escape(src.get("published_at", "")) + "</li>"
            for src in sources
        )
        photo = item.get("photo") or {}
        photo_url = escape(photo.get("source_page", ""), quote=True)
        license_url = escape(photo.get("license_url", ""), quote=True)
        license_text = escape(photo.get("license", ""))
        license_display = (f'<a href="{license_url}" target="_blank" rel="noopener noreferrer">{license_text}</a>'
                           if license_url.startswith("https://") else license_text)
        credit = (f'<p class="muted">Foto illustrativa: <a href="{photo_url}" target="_blank" rel="noopener noreferrer">'
                  f'{escape(photo.get("title", "Fotografia"))}</a> · '
                  f'{escape(photo.get("author", ""))} · {license_display}. '
                  'Foto ritagliata e adattata al modello grafico del post.</p>') if photo else ""
        if item.get("preview") and not photo:
            credit = '<p class="muted">Fotografia sintetica, utilizzata esclusivamente come simulazione grafica.</p>'
        status = '<p class="muted"><strong>ANTEPRIMA — NON PUBBLICATA</strong></p>' if item.get("preview") else ""
        cards.append(
            f'<article><img src="{image}" loading="lazy" alt="{escape(label, quote=True)}">'
            f'<div class="content"><span class="tag{cls}">{escape(label)}</span>'
            f'<h3>{escape(item["headline"])}</h3>{status}{carousel}<p>{escape(item.get("summary", ""))}</p>'
            f'<strong>Fonti consultate</strong><ul>{references or "<li>Simulazione, nessuna fonte</li>"}</ul>{credit}</div></article>'
        )
    cards_html = "".join(cards) if cards else "<p>Le notizie verificate saranno raccolte qui.</p>"
    html = f'''<!doctype html><html lang="it"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="description" content="Notizie buone, notizie cattive e curiosità: fonti e fotografie attribuite.">
<title>Notizie Buone e Cattive · Notizie e fonti</title><style>{STYLE}</style></head>
<body><div class="wrap"><header><small>INFORMAZIONE SEMPLICE · FONTI PUBBLICHE</small>
<h1>Notizie Buone e Cattive</h1><p class="intro">Notizie buone, notizie cattive e curiosità, in italiano. Due post settimanali con categorie a rotazione. Le fonti sono consultabili. La selezione e verifica automatica riduce alcuni errori, ma non equivale al controllo umano di un giornalista.</p>
</header><main><h2>Archivio e fonti</h2><div class="grid">{cards_html}</div></main>
<footer><small>Le fotografie selezionate da Wikimedia Commons sono illustrative e vengono accreditate singolarmente. Le immagini demo sono sintetiche e non documentano eventi realmente accaduti. Questo progetto non è affiliato alle testate citate.</small></footer></div></body></html>'''
    (folder / "index.html").write_text(html, encoding="utf-8")
    (folder / ".nojekyll").write_text("", encoding="utf-8")
