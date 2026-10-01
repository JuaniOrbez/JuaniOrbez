"""Carga de configuración (config.yaml + variables de entorno)."""
from __future__ import annotations

import os
from pathlib import Path

import yaml
from dotenv import load_dotenv

RAIZ = Path(__file__).resolve().parent.parent
DATOS = RAIZ / "datos"
SALIDA = RAIZ / "salida"


def cargar(ruta: str | Path | None = None) -> dict:
    load_dotenv(RAIZ / ".env")
    ruta = Path(ruta) if ruta else RAIZ / "config.yaml"
    if not ruta.exists():
        ruta = RAIZ / "config.example.yaml"
    with open(ruta, encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    DATOS.mkdir(exist_ok=True)
    SALIDA.mkdir(exist_ok=True)
    cfg["smtp"] = {
        "host": os.getenv("SMTP_HOST", ""),
        "port": int(os.getenv("SMTP_PORT", "465")),
        "ssl": os.getenv("SMTP_SSL", "true").lower() == "true",
        "user": os.getenv("SMTP_USER", ""),
        "password": os.getenv("SMTP_PASSWORD", ""),
    }
    return cfg
