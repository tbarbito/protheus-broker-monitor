# build.ps1
# Gera o executavel standalone broker-monitor.exe para distribuicao em ambientes
# sem acesso a internet ou com restricoes de firewall (ex: servidores Protheus corporativos).
#
# Uso:
#   .\build.ps1
#   .\build.ps1 -OutputDir "C:\MeusDist"
#
# Requisitos: Python 3.11+ e pip disponiveis na maquina de BUILD (nao no servidor destino).

param(
    [string]$OutputDir = "dist"
)

$ErrorActionPreference = "Stop"

Write-Host ""
Write-Host "=== broker-monitor :: build portable ===" -ForegroundColor Cyan
Write-Host ""

# Instala PyInstaller se necessario
Write-Host "Verificando PyInstaller..." -ForegroundColor Yellow
pip show pyinstaller > $null 2>&1
if ($LASTEXITCODE -ne 0) {
    Write-Host "Instalando PyInstaller..." -ForegroundColor Yellow
    pip install pyinstaller
}

# Gera o executavel
Write-Host "Gerando executavel (isso pode levar alguns minutos)..." -ForegroundColor Yellow
pyinstaller `
    --onefile `
    --name broker-monitor `
    --distpath $OutputDir `
    --hidden-import bs4 `
    --hidden-import requests `
    --hidden-import rich `
    src/broker_monitor/__main__.py

if ($LASTEXITCODE -ne 0) {
    Write-Host "Falha no build." -ForegroundColor Red
    exit 1
}

$exePath = Join-Path $OutputDir "broker-monitor.exe"
$size    = [math]::Round((Get-Item $exePath).Length / 1MB, 1)

Write-Host ""
Write-Host "Executavel gerado com sucesso!" -ForegroundColor Green
Write-Host "  Arquivo : $exePath" -ForegroundColor Green
Write-Host "  Tamanho : ${size} MB" -ForegroundColor Green
Write-Host ""
Write-Host "Para implantar no servidor:" -ForegroundColor Cyan
Write-Host "  1. Copie broker-monitor.exe para o servidor" -ForegroundColor White
Write-Host "  2. Copie config.example.json, renomeie para config.json e preencha" -ForegroundColor White
Write-Host "  3. Execute: broker-monitor.exe run --config config.json" -ForegroundColor White
Write-Host ""
