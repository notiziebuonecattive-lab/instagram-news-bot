# Instagram News Bot

**AGGIORNAMENTO 18/11/2026**

Questo pacchetto include i 3 template definitivi approvati dall'utente in `assets/templates/`:
- `template_buone.png`
- `template_cattive.png`
- `template_curiosita.png`

Include anche una anteprima 1:1 del risultato desiderato: `assets/templates/anteprima_1a1.png`.

**DOVE CARICARLO:** estrai lo ZIP e carica **tutto il contenuto della cartella** nella **root** del repository GitHub `instagram-news-bot`.

Una bella e una brutta notizia a settimana: grafica originale, fonti consultabili, pubblicazione via Buffer. Tutto in italiano, senza n8n e senza server permanente.

**STATO INIZIALE: SOLO TEST. NON C'È ALCUNA PUBBLICAZIONE AUTOMATICA.**

## Cosa viene fatto e cosa no

- `demo`: crea due PNG 1080×1350 e il sito delle fonti, senza chiamare DeepSeek o Buffer.
- `positive` / `negative`: DeepSeek cerca una notizia sul web (costo API), il programma verifica due articoli di editori diversi, le date, la disponibilità dei testi e chiede una seconda conferma al modello. Se manca un elemento, **non pubblica**.
- Solo con `publish=true` **e** Repository Variable `ALLOW_PUBLISH=true`: registra la notizia come `reserved`, pubblica l'immagine su GitHub Pages, controlla che sia online e chiama **una volta sola** l'API Buffer `shareNow`. La conferma di Buffer non certifica che Instagram abbia effettivamente mostrato il post: controllare Buffer/Instagram.
- Non esegue automaticamente il calendario finché non viene aggiunto il trigger `schedule`.

### Limiti della verifica delle notizie

Due editori/domini diversi e due URL funzionanti **non garantiscono** indipendenza editoriale o veridicità. La seconda lettura automatica è un filtro utile, non un fact-checker infallibile. Siti paywall o bloccati e notizie senza data verificabile vengono scartati; quindi il sistema può saltare una settimana. Evitare la pubblicazione completamente autonoma finché non si è verificata la qualità su vari casi reali.

## Configurazione, dopo l'importazione su GitHub

1. Repository pubblico `instagram-news-bot`, GitHub Pages Source **GitHub Actions**.
2. In `Settings → Secrets and variables → Actions → Secrets`: già creati `DEEPSEEK_API_KEY` e `BUFFER_API_KEY`. Non copiarli mai nei file.
3. In `Settings → Secrets and variables → Actions → Variables`: **non creare per ora** `ALLOW_PUBLISH`, oppure lasciarla `false` (valore predefinito). Se Buffer ha più canali Instagram, creare `BUFFER_CHANNEL_ID` con l'ID esatto restituito dalla API.
4. Aprire scheda `Actions`. Lanciare prima **Controlli automatici**, poi **Verifica Buffer (solo lettura)** tramite `Run workflow`.
5. Lanciare **Instagram - esecuzione MANUALE**, `kind=demo`, `publish=false`. Si ottiene un URL GitHub Pages con due immagini chiaramente marcate DEMO, senza usare il credito DeepSeek.
6. Solo quando la demo è confermata, fare **una** ricerca `kind=positive`, `publish=false` (può spendere una parte degli 0,08 € disponibili). Se i controlli bloccano il processo, leggere il motivo nei log, senza forzarlo.
7. Per attivare un post reale, impostare **volontariamente** Repository Variable `ALLOW_PUBLISH=true` e scegliere `publish=true` su un'esecuzione live. Se non vuoi ancora pubblicare, NON attivarla.
8. Dopo la verifica manuale di diverse notizie, si potrà valutare l'aggiunta del calendario automatico (vedi sotto).

**NOTA:** le immagini di anteprima generate in esecuzioni non pubblicate sono visibili sul sito Pages di quella esecuzione, ma non vengono salvate nel repository. Gli articoli riservati per la pubblicazione vengono invece registrati nei file `data/state.json` e `site/posts/` tramite commit automatico.

## Esito incerto e doppioni

Il bot usa `concurrency` GitHub Actions, tiene lo storico nel repository ed esegue un commit di prenotazione **prima** della scrittura su Buffer. Non ritenta le mutazioni Buffer dopo timeout: se l'invio ha esito incerto, lo stato resta `reserved` e il controllo deve essere manuale. Non cancellare a caso le riserve: prima vedere se il post esiste su Buffer e Instagram.

Se GitHub Pages non fornisce una URL pubblica raggiungibile, il bot **non** invia il post a Buffer. GitHub Actions può saltare/ritardare eventi pianificati; non è un servizio di pubblicazione con SLA garantiti.

## Attivare il calendario (solo in futuro)

Dopo aver stabilizzato il sistema, aggiungere all'evento `on` del file `.github/workflows/instagram.yml`:

```yaml
  schedule:
    - cron: '0 12 * * 2,5'
      timezone: 'Europe/Rome'
```

Il workflow riconosce automaticamente i giorni: martedì = notizia positiva, venerdì = notizia negativa. Per far funzionare la pianificazione serve **anche** impostare `ALLOW_PUBLISH=true` dopo i test (ed essere consapevoli che questo autorizzerà la pubblicazione). GitHub Actions potrebbe ritardare o saltare una corsa programmata. Prima di attivare la schedule, usare almeno una pubblicazione controllata e verificare i post nell'app Instagram.

## Sviluppo locale

```bash
python -m pip install -r requirements-dev.txt
python -m pytest -q
python -m newsbot.cli prepare --kind demo
```

L'anteprima statica viene generata nella cartella `site/`. Non è necessario configurare segreti per le demo. `payload.json` non viene versionato.

## Architettura

- `newsbot/deepseek.py`: richiesta DeepSeek web + controllo del testo rispetto alle due fonti.
- `newsbot/verify.py`: controlli di forma, fonti, date e deduplicazione.
- `newsbot/render.py`: due template Pillow originali, nessuna fotografia esterna.
- `newsbot/buffer.py`: lettura canali e singolo invio GraphQL `shareNow`.
- `newsbot/site.py`: pagina pubblica con fonti e archivio consultabili, da linkare nella bio.
- `data/state.json`: registro persistente su GitHub.
- `.github/workflows/ci.yml`: test e anteprima, nessuna credenziale.
- `.github/workflows/check-buffer.yml`: sola lettura Buffer, nessuna pubblicazione.
- `.github/workflows/instagram.yml`: esecuzione manuale, blocco doppio per pubblicazione.

## Documentazione ufficiale

- DeepSeek web tools: https://api-docs.deepseek.com/guides/web_tools/
- Buffer GraphQL image post: https://developers.buffer.com/examples/create-image-post.html
- Buffer channel retrieval: https://developers.buffer.com/guides/data-model
- GitHub Pages con Actions: https://docs.github.com/en/pages/getting-started-with-github-pages/using-custom-workflows-with-github-pages

## Importare da Windows senza usare terminali complessi

Dopo aver estratto lo ZIP, apri la cartella e fai doppio clic su **`IMPORTA_SU_GITHUB.bat`**. Incolla l'URL completo del tuo repository e segui la finestra di autenticazione GitHub, se appare. Serve **Git for Windows** installato; lo script non legge le chiavi API. Puoi aprire i due file `.bat` e `.ps1` in Blocco note per controllare cosa fanno. Alternativa: caricare manualmente i file estratti (compresa la cartella `.github`) con GitHub → Add file → Upload files.
