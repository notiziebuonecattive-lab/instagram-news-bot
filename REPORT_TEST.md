# Test Instagram News Bot V3

Verifica locale eseguita il 18 novembre 2026.

- `python -m pytest -q` → **26 test superati**.
- `python -m newsbot.cli prepare --kind demo` → tre caroselli, nove PNG 1080×1350 generati correttamente.
- Ogni categoria usa il proprio template originale di copertina e pagine interne in tre palette, con trasparenze preservate.
- Buffer carousel: una sola mutazione `createPost`, con 3 URL immagine in ordine, verificata con mock.
- Blocco pubblicazione: `ALLOW_PUBLISH=true` e `publish=true` necessari; niente schedule automatico.
- Verifiche con chiavi reali DeepSeek e Buffer non eseguite; nessuna chiamata a pagamento o pubblicazione reale.
- La verifica dei fatti basata su fonti e modello riduce gli errori, ma non sostituisce il controllo umano.
- **Da testare su GitHub Actions:** accesso effettivo DeepSeek, caricamento foto Wikimedia e pubblicazione dei caroselli su Buffer/Instagram, prima dell'automazione.

Documentazione API Buffer: https://developers.buffer.com/examples/create-image-post.html
