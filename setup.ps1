# setup.ps1 — First-time setup script for NL-to-SQL (Windows / PowerShell)
$ErrorActionPreference = "Stop"

Write-Host "==> Copying .env.example to .env" -ForegroundColor Cyan
if (-not (Test-Path ".env")) {
    Copy-Item ".env.example" ".env"
    Write-Host "    Created .env — edit MSSQL_SERVER, MSSQL_DATABASE and credentials before continuing."
    Write-Host "    Press Enter when done…" -ForegroundColor Yellow
    Read-Host
} else {
    Write-Host "    .env already exists, skipping."
}

Write-Host "`n==> Starting Ollama + Redis…" -ForegroundColor Cyan
docker compose up -d ollama redis

Write-Host "`n==> Waiting for Ollama…" -ForegroundColor Cyan
do {
    Start-Sleep -Seconds 3
    $ready = try { (Invoke-WebRequest -Uri "http://localhost:11434/api/tags" -UseBasicParsing -ErrorAction Stop).StatusCode -eq 200 } catch { $false }
} until ($ready)
Write-Host "    Ollama is ready."

Write-Host "`n==> Pulling LLM models (first run may take several minutes)…" -ForegroundColor Cyan
docker compose exec ollama ollama pull defog/sqlcoder-7b-2
docker compose exec ollama ollama pull nomic-embed-text

Write-Host "`n==> Starting all services…" -ForegroundColor Cyan
docker compose up -d

Write-Host "`n==> Waiting for backend…" -ForegroundColor Cyan
do {
    Start-Sleep -Seconds 5
    $ready = try { (Invoke-WebRequest -Uri "http://localhost:8000/health" -UseBasicParsing -ErrorAction Stop).StatusCode -eq 200 } catch { $false }
} until ($ready)
Write-Host "    Backend is ready."

Write-Host "`n==> Indexing schema into ChromaDB…" -ForegroundColor Cyan
$result = Invoke-RestMethod -Uri "http://localhost:8000/api/schema/index" -Method POST
$result | ConvertTo-Json

Write-Host "`n✓ Setup complete!" -ForegroundColor Green
Write-Host "  Frontend:  http://localhost"
Write-Host "  Backend:   http://localhost:8000/docs"
Write-Host "  Health:    http://localhost:8000/health"
