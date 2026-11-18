# Rapporto tecnico - 18 novembre 2026

## Verifiche eseguite in locale

- 17 test Pytest: **superati**.
- Generazione di 2 immagini dimostrative PNG 1080 × 1350: **superata**.
- Generazione della pagina web delle fonti: **superata**.
- Parsing dei tre workflow GitHub Actions YAML: **superato**.
- Gestione del blocco di pubblicazione, prenotazione e prevenzione doppio invio: **verificata con API simulate**.
- Verifica della struttura delle notizie, fonti distinte, duplicati e date: **verificata con dati simulati**.
- URL HTML e metadati dell'articolo: **testati con risposte simulate**.

## Non ancora verificato

- Nessuna API DeepSeek reale è stata chiamata: il credito di 0,08 € è invariato.
- Nessuna API Buffer reale è stata chiamata: la disponibilità dei permessi va controllata con il workflow di sola lettura.
- Nessun test è stato eseguito direttamente sull'account Instagram.
- Nessuna immagine è stata distribuita effettivamente sul GitHub Pages dell'utente.
- La verifica di due siti diversi e del loro contenuto non è equivalente a una verifica giornalistica infallibile.
- Il repository GitHub nuovo non era accessibile attraverso l'account GitHub connesso a questa chat: il progetto è consegnato come ZIP con importazione assistita.

## Protezioni

- Nessun calendario attivo nel workflow.
- Nessuna mutazione Buffer nelle demo o nel workflow di controllo.
- Scrittura Buffer solo con `ALLOW_PUBLISH=true` e richiesta esplicita.
- Blocco di duplicati con stato di prenotazione salvato nel repository prima dell'invio.
- Nessun ritentativo automatico dell'invio a Buffer quando l'esito potrebbe essere ambiguo.
