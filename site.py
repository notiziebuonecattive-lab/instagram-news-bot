"""Mini-sito pubblico delle fonti: collegabile dalla bio Instagram."""
from html import escape
from pathlib import Path


STYLE = """
:root{font-family:system-ui,-apple-system,Segoe UI,sans-serif;color:#273331;background:#f7f4ee}
*{box-sizing:border-box}body{margin:0}.wrap{max-width:940px;margin:auto;padding:30px 20px}
header{padding:48px 0 25px;border-bottom:2px solid #d8dfd9}h1{font-size:clamp(2rem,5vw,3.5rem);line-height:1.1;letter-spacing:-.04em;margin:0}
p{line-height:1.65}small,.muted{color:#526360}.intro{max-width:660px}h2{margin-top:48px}
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(270px,1fr));gap:24px;margin-top:24px}
article{background:white;border:1px solid #dce1da;border-radius:15px;overflow:hidden}
article img{width:100%;height:auto;display:block}article .content{padding:20px}
.tag{font-size:.77rem;font-weight:800;letter-spacing:.09em;color:#0d8272}
.tag.negative{color:#b94f42}article h3{font-size:1.4rem;line-height:1.22;margin:.7rem 0}
article a{color:#116659;overflow-wrap:anywhere}li{margin-bottom:8px}footer{border-top:1px solid #dce1da;padding:20px 0;margin-top:55px}
"""


def create_index(folder: Path, state: dict, preview: list[dict] | None = None) -> None:
    folder.mkdir(parents=True, exist_ok=True)
    items = (preview or []) + list(reversed(state.get("items", [])))
    cards = []
    for item in items[:80]:
        positive = item["kind"] == "positive"
        label = "BELLA NOTIZIA" if positive else "BRUTTA NOTIZIA"
        cls = "" if positive else " negative"
        image = escape(item.get("image", ""), quote=True)
        sources = item.get("sources", [])
        li = "".join(
            '<li><a href="' + escape(src["url"], quote=True) + '" rel="noopener noreferrer" target="_blank">'
            + escape(src["publisher"]) + "</a> · " + escape(src.get("published_at", "")) + "</li>"
            for src in sources
        )
        summary = escape(item.get("summary", ""))
        status = '<p class="muted"><strong>ANTEPRIMA — NON PUBBLICATA</strong></p>' if item.get("preview") else ""
        cards.append(f'<article><img src="{image}" loading="lazy" alt="{escape(label, quote=True)}">'
                     f'<div class="content"><span class="tag{cls}">{label}</span>'
                     f'<h3>{escape(item["headline"])}</h3>{status}<p>{summary}</p>'
                     f'<strong>Fonti consultate</strong><ul>{li}</ul></div></article>')
    content = "".join(cards) if cards else "<p>Le notizie verificate saranno raccolte qui.</p>"
    html = f'''<!doctype html><html lang="it"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="description" content="Due notizie a settimana. Una positiva e una negativa, con fonti consultabili.">
<title>Il mondo, in due notizie</title><style>{STYLE}</style></head>
<body><div class="wrap"><header><small>UN PROGETTO EDITORIALE MINIMAL</small>
<h1>Il mondo,<br>in due notizie.</h1>
<p class="intro">Ogni settimana una notizia positiva e una negativa. Informazioni contestualizzate e riferimenti agli articoli originali. I controlli automatici riducono gli errori, ma non sostituiscono una verifica giornalistica umana.</p>
</header><main><h2>Notizie e fonti</h2><div class="grid">{content}</div></main>
<footer><small>Le fonti sono riportate per permettere la consultazione; le immagini sono grafiche originali. Nessuna affiliazione con le testate citate.</small></footer></div></body></html>'''
    (folder / "index.html").write_text(html, encoding="utf-8")
    (folder / ".nojekyll").write_text("", encoding="utf-8")
