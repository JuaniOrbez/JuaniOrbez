"""Revisa la casilla (IMAP) para saber qué proveedores contestaron los pedidos."""
from __future__ import annotations

import email
import imaplib
import re
from datetime import datetime
from email.header import decode_header, make_header
from email.utils import parsedate_to_datetime

MESES = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


def _fecha_imap(fecha: str) -> str:
    d = datetime.fromisoformat(fecha[:19].replace(" ", "T"))
    return f"{d.day:02d}-{MESES[d.month - 1]}-{d.year}"


def _texto(msg: email.message.Message) -> str:
    partes = msg.walk() if msg.is_multipart() else [msg]
    for parte in partes:
        if parte.get_content_type() == "text/plain":
            datos = parte.get_payload(decode=True) or b""
            return datos.decode(parte.get_content_charset() or "utf-8", "replace")
    return ""


def pide_baja(texto: str) -> bool:
    """True si la respuesta (sin la parte citada) pide no recibir más correos."""
    propio = "\n".join(l for l in texto.splitlines() if not l.lstrip().startswith(">"))
    return re.search(r"\bbaja\b", propio[:400], re.IGNORECASE) is not None


class Casilla:
    def __init__(self, cfg_imap: dict):
        if not cfg_imap.get("user") or not cfg_imap.get("password"):
            raise ValueError("Faltan SMTP_USER / SMTP_PASSWORD en .env para leer el correo")
        self.cfg = cfg_imap
        self.con: imaplib.IMAP4_SSL | None = None

    def __enter__(self):
        self.con = imaplib.IMAP4_SSL(self.cfg["host"], self.cfg.get("port", 993))
        self.con.login(self.cfg["user"], self.cfg["password"])
        self.con.select("INBOX", readonly=True)
        return self

    def __exit__(self, *exc):
        if self.con:
            try:
                self.con.logout()
            except imaplib.IMAP4.error:
                pass

    def buscar_respuesta(self, remitente: str, desde: str) -> dict | None:
        """Primer correo de `remitente` recibido desde la fecha de envío."""
        assert self.con is not None
        estado, datos = self.con.search(None, "FROM", f'"{remitente}"', "SINCE", _fecha_imap(desde))
        if estado != "OK" or not datos or not datos[0]:
            return None
        primero = datos[0].split()[0]
        estado, partes = self.con.fetch(primero, "(BODY.PEEK[])")
        if estado != "OK":
            return None
        msg = email.message_from_bytes(partes[0][1])
        try:
            fecha = parsedate_to_datetime(msg["Date"]).strftime("%Y-%m-%d %H:%M")
        except (TypeError, ValueError):
            fecha = ""
        return {
            "fecha": fecha,
            "asunto": str(make_header(decode_header(msg.get("Subject", "")))),
            "baja": pide_baja(_texto(msg)),
        }
