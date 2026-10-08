"""Persistencia en SQLite: licitaciones, renglones, proveedores y emails enviados."""
from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager

from .config import DATOS

ESQUEMA = """
CREATE TABLE IF NOT EXISTS licitaciones (
    url TEXT PRIMARY KEY,
    numero TEXT, organismo TEXT, objeto TEXT, tipo TEXT,
    fecha_apertura TEXT, lugar_apertura TEXT, abierta INTEGER,
    texto TEXT, adjuntos TEXT,
    analizada INTEGER DEFAULT 0,
    creada TEXT DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    licitacion_url TEXT REFERENCES licitaciones(url),
    renglon TEXT, descripcion TEXT, cantidad REAL, unidad TEXT, especificaciones TEXT,
    busqueda TEXT,
    proveedores_buscados INTEGER DEFAULT 0,
    UNIQUE(licitacion_url, renglon, descripcion)
);
CREATE TABLE IF NOT EXISTS ofertas (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    item_id INTEGER REFERENCES items(id),
    proveedor TEXT, email TEXT, telefono TEXT, sitio_web TEXT, url_producto TEXT,
    producto TEXT, precio REAL, moneda TEXT, precio_incluye_iva INTEGER,
    provincia TEXT, notas TEXT,
    UNIQUE(item_id, proveedor, url_producto)
);
CREATE TABLE IF NOT EXISTS emails (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    licitacion_url TEXT, email TEXT, proveedor TEXT, asunto TEXT,
    estado TEXT, archivo TEXT,
    fecha TEXT DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(licitacion_url, email)
);
"""


@contextmanager
def conexion(ruta=None):
    con = sqlite3.connect(ruta or DATOS / "agente.db")
    con.row_factory = sqlite3.Row
    con.executescript(ESQUEMA)
    _migrar(con)
    try:
        yield con
        con.commit()
    finally:
        con.close()


COLUMNAS_NUEVAS = {
    "emails": {"respuesta_fecha": "TEXT", "respuesta_asunto": "TEXT", "baja": "INTEGER DEFAULT 0"},
}


def _migrar(con: sqlite3.Connection) -> None:
    """Agrega columnas nuevas a bases creadas con versiones anteriores."""
    for tabla, columnas in COLUMNAS_NUEVAS.items():
        existentes = {r[1] for r in con.execute(f"PRAGMA table_info({tabla})")}
        for nombre, tipo in columnas.items():
            if nombre not in existentes:
                con.execute(f"ALTER TABLE {tabla} ADD COLUMN {nombre} {tipo}")


def a_json(valor) -> str:
    return json.dumps(valor, ensure_ascii=False)
