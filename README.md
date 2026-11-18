# Instagram News Bot V3 — caroselli con template approvati

**NOVITÀ:** Usa i due template PNG dell'utente in 3 palette (verde, rosso, celeste). Ogni post crea 3 immagini 1080×1350: copertina, "Che cosa sappiamo", "Contesto e fonti". Le foto si inseriscono sotto ai template, il testo sopra. `Buffer` riceve un elenco ordinato di tre immagini nella stessa richiesta. Il calendario resta **DISATTIVATO** e `ALLOW_PUBLISH=false` resta il valore di sicurezza.

### Prima di pubblicare
1. Carica il contenuto dello ZIP **nella root del repository**, sovrascrivendo la vecchia versione.
2. Da Actions esegui prima `Controlli automatici` e poi `Instagram - esecuzione MANUALE` con `kind=demo` e `publish=false`.
3. Controlla la grafica del carosello (9 PNG: 3 caroselli di esempio). I crediti delle demo sono sintetici.
4. Solo dopo controlla un caso live con `publish=false`, che consuma credito DeepSeek.
5. Solo con approvazione esplicita imposta la variabile `ALLOW_PUBLISH=true` per un test reale di pubblicazione.

**I file dei template sono disponibili in** `assets/templates/`. Nel repository non devono essere incluse chiavi API.

---

# Instagram News Bot — versione 2 (tre categorie con fotografie)

Bot Instagram minimalista in italiano: **Notizie Buone** (verde pastello), **Notizie Cattive** (rosso pastello), **Curiosità** (celeste). Ogni post ha una **fotografia**, un **riquadro scuro** con titolo e sottotitolo e una descrizione con link alle fonti.

**CONSEGNA IN SICUREZZA:** inizialmente funziona SOLO in modalità demo. Non c'è un calendario attivo, né è possibile pubblicare senza abilitare volontariamente due controlli. 

## Architettura

- **Python + Pillow:** grafica 1080 × 1350, generata senza servizi esterni a pagamento.
- **DeepSeek Flash:** ricerca le notizie e produce testi italiani con citazioni (richiede saldo API); viene interrogato una seconda volta sul contenuto degli articoli. Non garantisce una verifica giornalistica umana.
- **Wikimedia Commons:** cerca una fotografia *illustrativa* pertinente, analizza licenza/crediti e scarica solo foto con una licenza accettata (`CC0`, dominio pubblico, oppure `CC BY`; `CC BY-SA` esclusa per evitare obblighi sui derivati). Se non trova una foto idonea, **non crea il post**. I metadati e le autorizzazioni restano da controllare sui casi reali: l'automazione non esclude dichiarazioni erronee degli uploader o diritti della personalità.
- **GitHub Pages:** ospita le immagini e il sito archivio con fonti e attribuzione della foto, collegabile alla bio.
- **Buffer GraphQL:** invia a Instagram un'immagine pubblicamente raggiungibile; le API e le autorizzazioni devono essere verificate con un test reale.
- **GitHub Actions:** prepara le demo e, soltanto dopo l'attivazione esplicita, consente di creare e inviare post reali.

## Calendario predisposto (ancora disattivato)

Rimangono **due post alla settimana**, martedì e venerdì alle **12:00 Europe/Rome**. Le tre categorie ruotano fra gli slot consecutivi (buone → cattive → curiosità → buone...). Non viene pubblicata una notizia di ogni categoria ogni settimana; per quello servirebbero tre slot.

Lo scheduler è **commentato** in `.github/workflows/instagram.yml` e viene ignorato finché non viene attivato volutamente.

## Importazione nel repository GitHub già creato

1. Scaricare ed estrarre lo ZIP completo.
2. Fare doppio clic su **`IMPORTA_SU_GITHUB.bat`** dalla cartella estratta (richiede **Git for Windows**). Inserire l'URL `https://github.com/TUO_UTENTE/instagram-news-bot`. Se i file sono già presenti, lo script aggiornerà il repository.
3. I due GitHub Secrets predisposti (`DEEPSEEK_API_KEY`, `BUFFER_API_KEY`) **restano su GitHub**. Non sono contenuti nello ZIP e non devono essere incollati nei file.
4. In `Settings → Pages → Build and deployment → Source` verificare `GitHub Actions`.
5. **Non** aggiungere o attivare la variabile `ALLOW_PUBLISH`; il suo valore predefinito è `false`.
6. Aprire `Actions`, controllare `Controlli automatici (nessuna pubblicazione)` e scaricare l'artifact `preview-instagram` per vedere tutte e tre le anteprime.
7. Avviare con `Run workflow` **Verifica Buffer (solo lettura)**. Il bot recupera il canale ma non crea alcun post.
8. Avviare manualmente **Instagram - esecuzione MANUALE**, `kind=demo`, `publish=false`: aggiorna GitHub Pages con tre anteprime; non chiama DeepSeek e non invia a Buffer.
9. Solo dopo il controllo delle immagini e del collegamento Buffer, provare una ricerca reale con `kind=positive`, `publish=false`. Può consumare il credito DeepSeek e accedere a Wikimedia Commons; con €0,08 disponibili valutare attentamente se farla.
10. **Non attivare il calendario o ALLOW_PUBLISH prima che i test reali, con immagini e fonti, siano stati controllati.**

> Se il repository non è accessibile da questa chat, lo ZIP è il metodo più sicuro per importare il progetto senza condividere chiavi. Il file `.bat` e lo script `.ps1` possono essere aperti con Blocco note prima dell'utilizzo.

## Cosa viene verificato

Per le notizie reali: due editori su domini differenti, link HTTPS, testi raggiungibili, date di pubblicazione dichiarate e trovate sulla pagina, assenza di titoli/sorgenti già usati, controllo LLM della corrispondenza del testo alle due fonti. Per notizie positive e negative vengono richiesti articoli recenti (fino a 10 giorni); per le curiosità è consentita una finestra fino a **90 giorni** per includere divulgazione scientifica non immediata.

**Limiti importanti:** due domini differenti non garantiscono la reale indipendenza degli articoli; alcuni siti bloccano l'accesso automatizzato e le notizie potrebbero non essere rilevate; Wikimedia può fornire foto genericamente pertinenti ma non riferite all'evento. La foto viene indicata come *illustrativa*, sia su Instagram sia sul sito. Se una verifica fallisce, il post è saltato.

## Controlli sulla pubblicazione

- Demo e anteprime non possono essere pubblicate.
- Una pubblicazione reale richiede **sia** `publish=true` nel lancio manuale **sia** la GitHub Actions Variable `ALLOW_PUBLISH=true`.
- Il bot salva la notizia come `reserved` nel repository **prima** di effettuare una richiesta `createPost` a Buffer, controlla che la PNG sia online via GitHub Pages, poi invia **una sola richiesta** a Buffer.
- Uno stato `sent_to_buffer` **non significa** che Instagram abbia effettivamente pubblicato. Per gli errori/tentativi incerti verificare manualmente Buffer prima di riprovare.
- Lo storico dei post è conservato in `data/state.json`. GitHub Actions usa un lock `concurrency` per evitare esecuzioni simultanee.

## Esecuzione locale senza credenziali

```bash
python -m pip install -r requirements-dev.txt
python -m pytest -q
python -m newsbot.cli prepare --kind demo
```

Le tre fotografie **demo** provengono dalle immagini sintetiche progettate durante questa conversazione. Sono soltanto elementi illustrativi e sono chiaramente marcate `SOLO DEMO`. In nessun caso la demo le invia a Instagram.

## Struttura del codice

- `newsbot/cli.py`: flusso completo; demo, preparazione, registrazione, invio, scelta slot.
- `newsbot/deepseek.py`: ricerca web e verifica via DeepSeek.
- `newsbot/verify.py`: validazione strutturale/fonti/date/duplicati.
- `newsbot/photos.py`: selezione foto Wikimedia Commons con attribuzione e controllo licenza.
- `newsbot/render.py`: tre template Pillow fedeli alla struttura grafica approvata.
- `newsbot/site.py`: archivio pubblico con fonti e crediti fotografici.
- `newsbot/buffer.py`: GraphQL Buffer.
- `.github/workflows/ci.yml`: test e artifact con 3 anteprime.
- `.github/workflows/check-buffer.yml`: sola lettura.
- `.github/workflows/instagram.yml`: pubblicazione manuale bloccata di default; schedule commentato.

## Documentazione ufficiale

- DeepSeek web tools: https://api-docs.deepseek.com/guides/web_tools/
- Buffer image post: https://developers.buffer.com/examples/create-image-post.html
- GitHub Actions schedule e timezone: https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax
- Wikimedia Commons metadati/licenze: https://commons.wikimedia.org/wiki/Commons:Machine-readable_data
