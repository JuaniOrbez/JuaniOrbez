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
    if not isinstance(cfg.get("filtros"), dict):
        if cfg.get("filtros") is not None:
            print(f"Aviso: la sección 'filtros:' de {ruta.name} está mal escrita; "
                  "se analiza sin filtro de rubros.")
        cfg["filtros"] = {}
    for seccion in ("empresa", "portal", "proveedores", "email"):
        if not isinstance(cfg.get(seccion), dict):
            raise SystemExit(
                f"Error en {ruta.name}: la sección '{seccion}:' está mal escrita "
                f"(se leyó {cfg.get(seccion)!r}). Revisá que las líneas de abajo de "
                f"'{seccion}:' empiecen con 2 espacios, igual que en config.example.yaml.")
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
