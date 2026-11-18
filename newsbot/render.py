"""Grafica fissa generata senza IA e senza immagini esterne."""
from pathlib import Path
import textwrap

from PIL import Image, ImageDraw, ImageFont

W, H = 1080, 1350
FONTS = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/truetype/liberation2/LiberationSans-Regular.ttf",
    "/Library/Fonts/Arial.ttf",
    "C:/Windows/Fonts/arial.ttf",
]
BOLD_FONTS = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/liberation2/LiberationSans-Bold.ttf",
    "C:/Windows/Fonts/arialbd.ttf",
]


def font(size: int, bold=False):
    for path in (BOLD_FONTS if bold else FONTS):
        if Path(path).exists():
            return ImageFont.truetype(path, size)
    return ImageFont.load_default()


def _lines(draw, content: str, face, width: int) -> list[str]:
    words = content.split()
    lines, line = [], ""
    for word in words:
        candidate = f"{line} {word}".strip()
        if draw.textbbox((0, 0), candidate, font=face)[2] <= width:
            line = candidate
        else:
            if line:
                lines.append(line)
            line = word
    if line:
        lines.append(line)
    return lines


def render(story: dict, target: Path, *, demo: bool = False) -> None:
    positive = story["kind"] == "positive"
    bg = "#F6F3EB"
    ink = "#202829"
    accent = "#0D8272" if positive else "#B94F42"
    label = "BUONA NOTIZIA" if positive else "BRUTTA NOTIZIA"
    im = Image.new("RGB", (W, H), bg)
    draw = ImageDraw.Draw(im)
    draw.rectangle((0, 0, W, 20), fill=accent)
    draw.ellipse((750, 70, 1350, 650), fill="#E7E9DF" if positive else "#EFE3DC")
    draw.ellipse((860, 180, 1190, 510), outline=accent, width=17)
    draw.line((78, 125, 1002, 125), fill="#BBC0BC", width=2)
    draw.text((78, 75), "IL MONDO, IN DUE NOTIZIE", font=font(29, True), fill=ink)
    draw.rounded_rectangle((78, 235, 440, 308), radius=17, fill=accent)
    draw.text((106, 251), label, font=font(35, True), fill="white")

    headline = story["headline"].strip()
    if len(headline) > 105:
        raise ValueError("Titolo oltre 105 caratteri")
    selected = None
    for size in range(83, 47, -2):
        face = font(size, bold=True)
        lines = _lines(draw, headline, face, 918)
        height = len(lines) * int(size * 1.24)
        if height <= 565 and len(lines) <= 6:
            selected = (face, lines, int(size * 1.24))
            break
    if not selected:
        raise ValueError("Titolo non adattabile alla grafica")
    face, lines, spacing = selected
    y = 385
    for line in lines:
        draw.text((78, y), line, font=face, fill=ink)
        y += spacing
    draw.line((78, 1090, 1002, 1090), fill=accent, width=5)
    draw.text((78, 1130), "UNA NOTIZIA. DUE FONTI. NIENTE RUMORE.", font=font(28, True), fill=ink)
    draw.text((78, 1220), "CONTESTO E FONTI NELLA DESCRIZIONE", font=font(23), fill="#5D6462")
    if demo:
        draw.rounded_rectangle((746, 45, 1002, 104), radius=10, fill="#202829")
        draw.text((760, 60), "ESEMPIO / DEMO", font=font(22, True), fill="#FFFFFF")
    target.parent.mkdir(parents=True, exist_ok=True)
    im.save(target, format="PNG", optimize=True)
