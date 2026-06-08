#!/usr/bin/env bash
# build.sh
# Gera o executavel standalone broker-monitor (ELF Linux) para distribuicao em
# servidores Protheus Linux sem acesso a internet ou com firewall restrito.
#
# Uso:
#   ./build.sh
#   ./build.sh /caminho/dist
#
# Requisitos: Python 3.11+ e pip na maquina de BUILD (nao no servidor destino).
#
# IMPORTANTE: o PyInstaller NAO faz cross-compilation. Rode este script em um
# Linux para gerar o binario Linux. Para gerar o .exe Windows, use build.ps1
# em uma maquina Windows.

set -euo pipefail

OUTPUT_DIR="${1:-dist}"

echo ""
echo "=== broker-monitor :: build portable (Linux) ==="
echo ""

# Instala PyInstaller se necessario
echo ">> Verificando PyInstaller..."
if ! python3 -m pip show pyinstaller > /dev/null 2>&1; then
    echo ">> Instalando PyInstaller..."
    python3 -m pip install pyinstaller
fi

# Gera o executavel
echo ">> Gerando executavel (isso pode levar alguns minutos)..."
python3 -m PyInstaller \
    --onefile \
    --name broker-monitor \
    --distpath "$OUTPUT_DIR" \
    --hidden-import bs4 \
    --hidden-import requests \
    --hidden-import rich \
    src/broker_monitor/__main__.py

EXE_PATH="${OUTPUT_DIR}/broker-monitor"
SIZE=$(du -h "$EXE_PATH" | cut -f1)

echo ""
echo ">> Executavel gerado com sucesso!"
echo "   Arquivo : ${EXE_PATH}"
echo "   Tamanho : ${SIZE}"
echo ""
echo "Para implantar no servidor:"
echo "  1. Copie o binario broker-monitor para o servidor"
echo "  2. Copie config.example.json, renomeie para config.json e preencha"
echo "  3. De permissao de execucao: chmod +x broker-monitor"
echo "  4. Execute: ./broker-monitor run --config config.json"
echo ""
