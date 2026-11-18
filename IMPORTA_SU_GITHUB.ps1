# Importazione assistita del progetto da Windows. Non legge alcuna chiave API.
param([string]$RepoUrl)
$ErrorActionPreference = 'Stop'
if (-not $RepoUrl) {
    $RepoUrl = Read-Host 'Incolla URL del repository (es. https://github.com/UTENTE/instagram-news-bot)'
}
if ($RepoUrl -notmatch '^https://github\.com/[A-Za-z0-9_.-]+/instagram-news-bot(?:\.git)?/?$') {
    throw 'URL non valido: usa il repository instagram-news-bot su github.com.'
}
if (-not (Get-Command git -ErrorAction SilentlyContinue)) {
    throw 'Git non è installato. Puoi installare Git for Windows oppure caricare i file estratti dal sito GitHub.'
}
$working = Join-Path $env:TEMP ('instagram-news-bot-import-' + [guid]::NewGuid().ToString('N'))
try {
    & git clone $RepoUrl $working
    if ($LASTEXITCODE -ne 0) { throw 'Clone non riuscito. Controlla Git e accesso al repository.' }
    Get-ChildItem -LiteralPath $PSScriptRoot -Force | Where-Object { $_.Name -ne 'IMPORTA_SU_GITHUB.ps1' } | ForEach-Object {
        Copy-Item -LiteralPath $_.FullName -Destination $working -Recurse -Force
    }
    Push-Location $working
    try {
        & git add -A
        if ($LASTEXITCODE -ne 0) { throw 'Impossibile aggiungere i file.' }
        & git -c 'user.name=Instagram News Bot Setup' -c 'user.email=setup@users.noreply.github.com' commit -m 'Install Instagram News Bot (safe demo default)'
        if ($LASTEXITCODE -ne 0) { throw 'Nessuna modifica da importare oppure commit non riuscito.' }
        & git push origin HEAD
        if ($LASTEXITCODE -ne 0) { throw 'Push non riuscito. Verifica accesso a GitHub.' }
        Write-Host 'Importazione completata. Apri il repository su GitHub e vai nella scheda Actions.' -ForegroundColor Green
    }
    finally { Pop-Location }
}
finally {
    if (Test-Path $working) { Remove-Item -LiteralPath $working -Recurse -Force }
}
