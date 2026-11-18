# Instagram News Bot V4.1 — caroselli flessibili e didascalie automatiche

Il bot **pubblica soltanto contenuti già preparati**. Non cerca notizie, non inventa testi o fatti, non usa DeepSeek e non disegna immagini.
Le grafiche si preparano a parte, qui in ChatGPT, usando i tuoi template. Il bot riconosce la sequenza delle immagini e assembla la didascalia per Buffer a partire dai file di testo.

**Stato di sicurezza:** la pubblicazione programmata resta **disattivata**. Il workflow di pubblicazione resta manuale e richiede `ALLOW_PUBLISH=true` **più** la scelta esplicita `publish` per inviare un post.

## 1. Cartella di ogni carosello

Nella cartella `posts/queue/` inserisci un post già pronto. Esempio con **quattro slide**:

```text
posts/queue/
  001_buona_scoperta/
    01.png
    02.png
    03.png
    04.png
    01_una_terapia_genetica_per_un_solo_bambino.txt
```

Sono accettati caroselli da **2 a 20 slide** (in genere useremo 3 o 4): immagini `01.png`, `02.png`, e così via, **senza buchi nella numerazione**, tutte **1080 × 1350 px**. L'ordine dei file determina l'ordine delle immagini su Instagram. Buffer documenta un limite massimo di 20 immagini per carosello Instagram.

Ogni post deve usare una di queste due modalità per la didascalia.

### A) Modalità automatica — consigliata per il tuo Template.zip

Metti **un solo TXT editoriale originale** nella cartella, conservando anche il nome originale (ad esempio `31_manoscritto_voynich.txt`). Il bot riconosce le sezioni:

- `CAPTION INSTAGRAM`: descrizione testuale;
- `HASHTAG`: hashtag da aggiungere, senza ripeterli;
- `FONTI CONSULTABILI`: URL delle fonti;
- `NOTA EDITORIALE (NON PUBBLICARE)`: esclusa automaticamente dal post.

Il titolo e i testi delle `SLIDE` non vengono pubblicati due volte: sono destinati alle immagini già impaginate. Non è necessaria nessuna API di intelligenza artificiale.

Puoi visualizzare la didascalia che verrà inviata con:

```bash
python -m bot.publisher caption --post 001_buona_scoperta
```

### B) Modalità manuale — alternativa

Se le descrizioni sono già pronte in file separati, usa:

```text
posts/queue/002_cattiva_esempio/
  01.png
  02.png
  03.png
  caption.txt
  sources.txt
  hashtags.txt    (facoltativo)
```

- `caption.txt`: testo principale, eventualmente già completo di hashtag.
- `hashtags.txt`: tag supplementari, ad esempio `#Notizie #Ambiente #Scienza`. Il bot li aggiunge senza duplicazioni. Se **non ci sono hashtag** da nessuna parte, inserisce tre tag generici basati sulla categoria.
- `sources.txt`: un URL HTTPS per riga.

**Se sono presenti `caption.txt` e `sources.txt`, il bot usa questi** (anche se c'è un altro TXT editoriale per archivio). Se non ci sono, richiede esattamente un TXT editoriale nel formato descritto sopra. Non tronca le didascalie superiori a **2.200 caratteri**, ma segnala l'errore.

Le categorie ammesse nel nome della cartella sono `buona`, `cattiva` e `curiosita`: per i TXT del gruppo *Misteri* usa `curiosita` come categoria tecnica, mantenendo nell'immagine e negli hashtag l'etichetta *Misteri* se desideri.

## 2. Preparare una didascalia anche senza immagini

Puoi assemblare un TXT originale prima ancora di completare le grafiche:

```bash
python -m bot.publisher compose --file "percorso/31_manoscritto_voynich.txt" --category curiosita
```

Per esportare **`caption.txt`** e **`sources.txt`** (senza sovrascrivere file esistenti):

```bash
python -m bot.publisher compose --file "percorso/31_manoscritto_voynich.txt" --category curiosita --out "cartella/output"
```

Questo comando non fa ricerche web, non interroga Buffer e non pubblica. Se le fonti sono insufficienti, mostra un avviso: puoi comunque esportare il testo, **ma non inviarlo automaticamente** finché non sono presenti i riferimenti richiesti.

## 3. Controllo delle fonti

Per poter passare il controllo di pubblicazione il post deve contenere **almeno due URL HTTPS di domini differenti**. È un requisito prudenziale del progetto, non un fact-check automatico: due siti diversi non provano da soli che una notizia sia vera.

Alcuni dei TXT del tuo archivio contengono una sola fonte o fonti dello stesso dominio; in questi casi la V4.1 prepara il testo ma **blocca il post** finché non saranno completati i riferimenti. Non modifica mai automaticamente le fonti.

## 4. Comandi di verifica

```bash
python -m unittest discover -s tests -v
python -m bot.publisher validate
python -m bot.publisher plan
python -m bot.publisher caption --post 001_buona_scoperta
```

- `validate` controlla ogni post nella coda e il formato delle immagini, didascalie e fonti. La coda può essere vuota.
- `plan` mostra il prossimo post da pubblicare, il numero reale di slide e le fonti.
- `caption` mostra la descrizione **esatta** costruita per il post selezionato.

Ogni push su `main` esegue il workflow **Verifica caroselli (nessuna pubblicazione)**.

## 5. Pubblicazione: invariata e ancora disattivata

Il repository resta `notiziebuonecattive-lab/instagram-news-bot`. La chiave Buffer `BUFFER_API_KEY` e la variabile `BUFFER_CHANNEL_ID` già presenti su GitHub **non devono essere modificate**. `DEEPSEEK_API_KEY` non è usata.

Il workflow `publish.yml` è manuale, con modalità `preview` o `publish`. Quest'ultima richiede `ALLOW_PUBLISH=true`; non è attivato alcun `schedule`. Non impostare `ALLOW_PUBLISH=true` finché non avremo collaudato un carosello reale.

Il programma prenota il post con un commit prima della chiamata a Buffer per evitare doppioni. Le immagini vengono servite tramite URL HTTPS pubblici del repository. Gli URL devono restare raggiungibili fino alla pubblicazione. La conferma di Buffer non garantisce che Instagram abbia poi pubblicato effettivamente le immagini.

Due pubblicazioni settimanali (martedì e venerdì alle 12:07, ora italiana) potranno essere abilitate **solo più avanti**. Github Actions può ritardare le esecuzioni programmate. L'ordine dei post è quello dei numeri progressivi delle cartelle, non quello delle categorie.

**Attenzione:** il repository è pubblico; ciò che carichi nella coda è visibile anche prima della pubblicazione Instagram. Per post riservati serve un archivio privato.

## 6. Aggiornamento della V4 alla V4.1

Non pulire né ricreare il repository. Estrai il pacchetto `AGGIORNA_BOT_V4_1.zip` e avvia `AGGIORNA_BOT_V4_1.bat` su Windows, con Git for Windows installato.

Lo script verifica la versione corrente dei file, crea un backup Git locale e aggiorna **soltanto** `bot/publisher.py`, `tests/test_publisher.py` e `README.md`. Non tocca `data/state.json`, `posts/queue/`, le chiavi, le variabili GitHub o i workflow.

Il codice è stato testato offline con `unittest` e con i 45 file `.txt` del Template.zip. Non è ancora stato eseguito un invio reale di carosello a Buffer.

## Documentazione

- Buffer, immagini e limiti Instagram: https://support.buffer.com/articles/attaching-images-videos-and-other-media-to-your-posts-eudySt0TnS
- Buffer, elenco ordinato di immagini API: https://developers.buffer.com/examples/create-image-post.html
- Buffer, media pubblici raggiungibili: https://developers.buffer.com/guides/hosting-media.html
- GitHub, workflow pianificati: https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax
