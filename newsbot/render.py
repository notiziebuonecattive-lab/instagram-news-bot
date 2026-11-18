"""Rendering caroselli tramite i due template PNG RGBA forniti dal progetto.

Foto sotto al PNG, testo sopra, quindi export Instagram 1080×1350.
Le immagini demo non rappresentano notizie reali.
"""
from __future__ import annotations

from pathlib import Path
import re
from PIL import Image, ImageDraw, ImageFont, ImageOps

W, H = 1122, 1402
EXPORT = (1080, 1350)
ASSETS = Path(__file__).resolve().parent.parent / 'assets' / 'templates'
THEMES = {
    'positive': {'name':'verde', 'label':'NOTIZIE BUONE', 'light':'#7BEEBC', 'dark':'#073629'},
    'negative': {'name':'rosso', 'label':'NOTIZIE CATTIVE', 'light':'#FFB4AF', 'dark':'#3B181D'},
    'curiosity': {'name':'celeste', 'label':'CURIOSITÀ', 'light':'#61E5F4', 'dark':'#06263E'},
}
FONTS = ['/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf',
         '/usr/share/fonts/truetype/liberation2/LiberationSans-Regular.ttf',
         'C:/Windows/Fonts/arial.ttf']
BOLDS = ['/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf',
         '/usr/share/fonts/truetype/liberation2/LiberationSans-Bold.ttf',
         'C:/Windows/Fonts/arialbd.ttf']


def font(size: int, bold: bool = False):
    for filename in (BOLDS if bold else FONTS):
        if Path(filename).exists():
            return ImageFont.truetype(filename, size)
    return ImageFont.load_default()


def wrap(d: ImageDraw.ImageDraw, text: str, face, max_width: int) -> list[str]:
    result = []
    line = ''
    for word in text.split():
        part = (line+' '+word).strip()
        if d.textbbox((0,0),part,font=face)[2] <= max_width:
            line=part
        else:
            if not line:
                raise ValueError('Una parola non rientra nello spazio del template')
            result.append(line)
            line=word
            if d.textbbox((0,0),line,font=face)[2] > max_width:
                raise ValueError('Una parola non rientra nello spazio del template')
    if line: result.append(line)
    return result


def fit_text(d, text, width, height, size_max, size_min, max_lines, bold=False):
    for sz in range(size_max,size_min-1,-2):
        face=font(sz,bold)
        try: lines=wrap(d,text,face,width)
        except ValueError: continue
        lead=round(sz*1.29)
        if len(lines)<=max_lines and len(lines)*lead<=height:
            return face,lines,lead
    raise ValueError('Testo troppo lungo per la grafica: interrompo anziché sovrapporre')


def _base(kind:str, photo:Path, which:str) -> Image.Image:
    if kind not in THEMES: raise ValueError('Categoria grafica non supportata')
    if which not in ('copertina','interna'): raise ValueError('Template non valido')
    f=ASSETS/f'{which}_{THEMES[kind]["name"]}.png'
    if not f.exists(): raise ValueError('Template PNG mancante: '+str(f))
    photo=Path(photo)
    if not photo.is_file(): raise ValueError('Fotografia obbligatoria non trovata')
    with Image.open(photo) as source:
        source=ImageOps.exif_transpose(source).convert('RGB')
        if source.width<600 or source.height<420:
            raise ValueError('Fotografia di risoluzione insufficiente')
        picture=ImageOps.fit(source,(W,845),Image.Resampling.LANCZOS,centering=(.5,.45))
    bg=Image.new('RGBA',(W,H),'#FFFFFF')
    bg.alpha_composite(picture.convert('RGBA'),(0,0))
    with Image.open(f) as layer:
        if layer.size!=(W,H):raise ValueError('Dimensioni template diverse da 1122×1402')
        bg.alpha_composite(layer.convert('RGBA'))
    return bg.convert('RGB')


def _brand(d,kind:str):
    accent=THEMES[kind]['light']
    d.rounded_rectangle((95,1256,474,1319),radius=30,outline=accent,width=3)
    f=font(26,True)
    d.text((118,1271),'@notiziebuonecattive',font=f,fill='white')


def _save(im:Image.Image, target:Path, demo:bool):
    d=ImageDraw.Draw(im)
    if demo:
        d.rounded_rectangle((785,30,1082,98),radius=20,fill='#101C2C')
        d.text((814,48),'SOLO DEMO',font=font(25,True),fill='#FFFFFF')
    target=Path(target)
    target.parent.mkdir(parents=True,exist_ok=True)
    im.resize(EXPORT,Image.Resampling.LANCZOS).save(target,'PNG',compress_level=2)


def render(story:dict, target:Path, *, demo:bool=False, photo:Path|None=None):
    """Copertina; API compatibile con il vecchio renderer per i test."""
    kind=story['kind']
    picture=Path(photo or story.get('photo_path',''))
    im=_base(kind,picture,'copertina')
    d=ImageDraw.Draw(im)
    theme=THEMES[kind]
    badgeface=font(30,True)
    label=theme['label']
    badgew=d.textbbox((0,0),label,font=badgeface)[2]
    # La pillola del template originale occupa x90–488.
    d.text((round(90+(398-badgew)/2),748),label,font=badgeface,fill=theme['dark'])
    headline=str(story['headline']).strip()
    if not headline:raise ValueError('Titolo vuoto')
    face,lines,leading=fit_text(d,headline,925,285,82,46,4,bold=True)
    y=850
    for idx,line in enumerate(lines):
        # Evidenzia la parte finale del titolo, senza cambiare il testo.
        if idx==len(lines)-1 and len(line.split())>1:
            words=line.split()
            last=words[-1]
            prefix=' '.join(words[:-1])+' '
            d.text((103,y),prefix,font=face,fill='white')
            off=d.textbbox((0,0),prefix,font=face)[2]
            d.text((103+off,y),last,font=face,fill=theme['light'])
        else:
            d.text((103,y),line,font=face,fill='white')
        y+=leading
    teaser=str(story.get('teaser') or 'Approfondimento e fonti nella descrizione').strip()
    face,lines,step=fit_text(d,teaser,864,150,33,23,4)
    y=max(1055,y+17)
    if y+len(lines)*step>1212:
        raise ValueError('Titolo e sottotitolo troppo lunghi per la copertina')
    d.rounded_rectangle((108,y+9,115,y+len(lines)*step-1),radius=3,fill=theme['light'])
    for line in lines:
        d.text((155,y),line,font=face,fill='#F1F8F8')
        y+=step
    _brand(d,kind)
    _save(im,target,demo)


def _inner(story:dict,photo:Path,target:Path,heading:str,body:str,*,demo:bool=False,sources:bool=False):
    kind=story['kind']
    im=_base(kind,photo,'interna')
    d=ImageDraw.Draw(im)
    theme=THEMES[kind]
    headface,headlines,lead=fit_text(d,heading,920,120,66,38,2,bold=True)
    y=843
    for line in headlines:
        d.text((103,y),line,font=headface,fill='white')
        y+=lead
    # Il blocco grafico originale contiene una riga verticale in corrispondenza x110.
    # Testo a destra del tratto, senza sovrapposizione.
    y=max(y+20,953)
    reserve_bottom=1224 if not sources else 1173
    # Il testo completo resta nella caption: nella slide compare un estratto leggibile.
    words=body.split()
    for count in range(len(words), 0, -1):
        excerpt=' '.join(words[:count]) + ('…' if count<len(words) else '')
        try:
            face,lines,step=fit_text(d,excerpt,855,reserve_bottom-y,34,24,8)
            break
        except ValueError:
            continue
    else:
        raise ValueError('Impossibile inserire il testo nella slide')
    for line in lines:
        d.text((155,y),line,font=face,fill='#F5FAF9')
        y+=step
    if sources:
        refs=', '.join(str(s.get('publisher','')) for s in story.get('sources',[])[:2])
        if refs:
            d.text((154,1188),'FONTI: '+refs[:58],font=font(23,True),fill=theme['light'])
    _brand(d,kind)
    _save(im,target,demo)


def _split_summary(summary:str) -> tuple[str,str]:
    """Usa parole già verificate, senza generare nuove affermazioni.

    Il testo completo rimane nella didascalia; le due slide contengono estratti.
    """
    sentences=[x.strip() for x in re.split(r'(?<=[.!?])\s+',str(summary).strip()) if x.strip()]
    first=[];second=[]
    for sentence in sentences:
        words=len(sentence.split())
        if not second and len(' '.join(first).split())+words<=46:
            first.append(sentence)
        elif len(' '.join(second).split())+words<=46:
            second.append(sentence)
        else:
            # Il corpo integrale resta nella caption. Non forzare contenuti lunghi.
            break
    if not first:
        first=[' '.join(summary.split()[:40]).rstrip('.,;')+'…']
    if not second:
        remaining=summary.split()[len(' '.join(first).split()):]
        second=[' '.join(remaining[:40]).rstrip('.,;')+'…' if remaining else 'Approfondimento completo e fonti nella descrizione.']
    return ' '.join(first),' '.join(second)


def render_carousel(story:dict,folder:Path,*,demo:bool=False,photo:Path|None=None) -> list[Path]:
    """Tre PNG 4:5: copertina + due slide informative. Nessuna pubblicazione."""
    picture=Path(photo or story.get('photo_path',''))
    dest=Path(folder)
    name=str(story['id'])
    paths=[dest/f'{name}-01.png',dest/f'{name}-02.png',dest/f'{name}-03.png']
    render(story,paths[0],photo=picture,demo=demo)
    body1,body2=_split_summary(story['summary'])
    heading='Che cosa sappiamo?' if story['kind']=='curiosity' else 'Che cosa è successo?'
    _inner(story,picture,paths[1],heading,body1,demo=demo)
    _inner(story,picture,paths[2],'Contesto e fonti',body2,demo=demo,sources=True)
    return paths
