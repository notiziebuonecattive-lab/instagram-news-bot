# Instagram News Bot V4 — solo pubblicazione, senza IA

Questo progetto pubblica **caroselli già scritti, verificati e impaginati**.
Non cerca notizie, non genera testi, non acquista crediti API e non modifica immagini.

**STATO INIZIALE: PUBBLICAZIONE BLOCCATA**. Il calendario automatico NON è installato: il workflow è solo manuale e richiede anche `ALLOW_PUBLISH=true` per inviare.

## Il lavoro quotidiano

1. Prepari qui in ChatGPT il carosello con le tue grafiche: **3 PNG 1080×1350**, la didascalia e almeno due URL diretti alle fonti.
2. Metti i cinque file in una cartella numerata, per esempio `posts/queue/001_buona_speranza/`:

   ```text
   01.png
   02.png
   03.png
   caption.txt
   sources.txt
   ```

3. Carichi la cartella su GitHub (la *cartella estratta*: un `.zip` caricato come singolo file non viene aperto automaticamente).
4. Dopo la futura attivazione del calendario, il bot sceglierà il numero più basso non ancora inviato e lo manderà a Buffer **il martedì e il venerdì alle 12:07, ora italiana**, una pubblicazione per giornata. Le tre categorie sono `buona`, `cattiva`, `curiosita` nel nome della cartella. È l'ordine numerico, **non** la categoria, a determinare la sequenza.

Nessun processo locale o computer acceso è necessario. Non occorre GitHub Pages: il programma condivide URL diretti dei PNG in questo repository pubblico.

### Regole per le cartelle

- Nome cartella: `NNN_categoria_descrizione` (tre cifre; esempio `002_cattiva_alluvione`, `003_curiosita_polpi`). Niente spazi o accenti nei nomi.
- `01.png`, `02.png`, `03.png`: PNG di **1080×1350 px**, ordine del carosello.
- `caption.txt`: testo italiano **già completo** di descrizione, eventuali crediti fotografici, hashtag e nomi delle fonti; massimo 2.200 caratteri.
- `sources.txt`: almeno due URL HTTPS, **uno per riga**, da domini differenti, relativi alle verifiche effettuate. Sono un archivio pubblico della documentazione, **non** un fact-check automatico.
- Non modificare né cancellare una cartella dopo che è stata inviata a Buffer: le immagini devono rimanere accessibili.
- Evitare di caricare in anticipo notizie molto sensibili alla data: il bot pubblica in ordine, non controlla se il contenuto è ancora attuale.

## Configurazione GitHub

Usa il **repository già esistente** `notiziebuonecattive-lab/instagram-news-bot`. **NON eliminarlo**: elimineresti anche i segreti già configurati.

### Secrets & Variables

Percorso `Settings → Secrets and variables → Actions`:

| Tipo | Nome | Uso |
| --- | --- | --- |
| Repository secret | `BUFFER_API_KEY` | Chiave Buffer esistente: **mantienila** |
| Repository variable | `ALLOW_PUBLISH` | Inizialmente `false`. Passerà a `true` soltanto dopo il test reale autorizzato |
| Repository variable facoltativa | `BUFFER_CHANNEL_ID` | Serve soltanto se Buffer ha più account Instagram collegati |

`DEEPSEEK_API_KEY` non è più utilizzato: puoi lasciarlo nei Secrets (non viene letto dai nuovi workflow) oppure eliminarlo successivamente se vuoi ridurre le credenziali conservate.

### Workflow

- `.github/workflows/check.yml`: valida tutti i contenuti su ogni push. Non possiede chiavi API e non pubblica.
- `.github/workflows/publish.yml`: inizialmente SOLO manuale. `preview` (predefinita) non invia nulla; `publish` necessita di `ALLOW_PUBLISH=true`. Il calendario è commentato e andrà attivato solo dopo il collaudo.

Non mantenere in `.github/workflows/` i vecchi `instagram.yml`, `ci.yml`, `check-buffer.yml`: sono progettati per la V3 e non devono coesistere con la V4.

### Per abilitare la pubblicazione reale

1. Importa la V4 e verifica che l'azione **Verifica caroselli** sia verde.
2. Carica **un solo carosello di prova reale e verificato**, poi avvia `Instagram - pubblica carosello` in modalità `preview`: nei log deve comparire il suo identificativo, senza alcun invio.
3. Verifica che i PNG siano accessibili in forma diretta da una finestra privata del browser (gli URL puntano a `raw.githubusercontent.com`).
4. Aggiungi la Repository Variable `ALLOW_PUBLISH=true` **solo quando vuoi autorizzare gli invii**.
5. Esegui un invio manuale con `mode=publish`, quindi controlla **Buffer e Instagram**. L'ID restituito da Buffer conferma la ricezione della richiesta, non garantisce la pubblicazione finale su Instagram.
6. **Solo quando sarai pronto**, aggiungi il trigger `schedule` commentato in `.github/workflows/publish.yml`; allora funzionerà il calendario con `ALLOW_PUBLISH=true`.

## Protezione contro i doppioni

Prima dell'invio il programma aggiorna `data/state.json` con stato `reserved` e lo **salva su GitHub con un commit**. Solo se il push riesce, prova a inviare il carosello a Buffer. Dopo una risposta positiva aggiorna lo stato a `sent_to_buffer` e registra l'ID ricevuto.

Se una mutazione Buffer ha un esito incerto (timeout o errore) il post resta `reserved` e **la coda si blocca**: è necessario controllare Buffer prima di modificarne lo stato. Non riprovare alla cieca. Non cancellare `data/state.json` e non rinumerare le cartelle pubblicate.

GitHub Actions può ritardare o saltare le esecuzioni pianificate; per questo non è garantita la pubblicazione all'ora esatta. La V4 non dispone di un recupero automatico fuori dai due giorni previsti; al successivo slot valido riprende il primo carosello non pubblicato.

## Limiti importanti

- Tutto ciò che carichi nel repository **pubblico** è pubblico, anche immagini, didascalie e fonti prima della data di pubblicazione. Per notizie ancora riservate o contenuti non destinati alla diffusione, serve un altro archivio.
- `sources.txt` con due domini diversi **non dimostra la veridicità dei fatti**: il fact-check va fatto prima di caricare.
- Per i servizi esterni può essere necessario adeguare il formato dei post o rinnovare la chiave API quando Buffer cambia le proprie condizioni.
- `raw.githubusercontent.com` deve poter servire i PNG a Buffer. Se il primo invio reale fallisce per i file media, il test va corretto prima di riprovare; si potrà usare GitHub Pages come alternativa.

## Sviluppo offline

Servono Python 3.12 e basta; nessuna dipendenza Python esterna.

```bash
python -m unittest discover -s tests -v
python -m bot.publisher validate
python -m bot.publisher plan
```

La programmazione usa la sintassi GitHub Actions con `timezone: Europe/Rome`.

Documentazione: https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows ; https://developers.buffer.com/guides/hosting-media.html ; https://developers.buffer.com/examples/create-image-post.html
