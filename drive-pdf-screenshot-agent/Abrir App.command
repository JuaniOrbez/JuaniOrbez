#!/bin/bash
cd "$(dirname "$0")"

if [ ! -d "venv" ]; then
  echo "No se encontró el entorno virtual 'venv'."
  echo "Corré primero la instalación desde la terminal (ver README.md)."
  read -p "Presioná Enter para cerrar esta ventana."
  exit 1
fi

source venv/bin/activate
python app.py

echo ""
read -p "Presioná Enter para cerrar esta ventana."
