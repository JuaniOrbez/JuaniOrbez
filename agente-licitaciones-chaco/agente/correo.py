"""Armado y envío de pedidos de cotización por email."""
from __future__ import annotations

import re
import smtplib
import ssl
from email.message import EmailMessage
from email.utils import formatdate, make_msgid

from .config import SALIDA


def armar(empresa: dict, proveedor: str, destinatario: str, licitacion: dict,
          items: list[dict], cc: list[str] | None = None) -> EmailMessage:
    numero = licitacion.get("numero") or "proceso de compra"
    asunto = f"Pedido de cotización – {numero} – {empresa['razon_social']}"

    filas = []
    for it in items:
        cant = it.get("cantidad")
        cant_txt = f"{cant:g}" if isinstance(cant, (int, float)) else "a definir"
        linea = f"  • {it['descripcion']} — Cantidad: {cant_txt} {it.get('unidad') or ''}".rstrip()
        if it.get("especificaciones"):
            linea += f"\n    Especificaciones: {it['especificaciones']}"
        filas.append(linea)

    apertura = licitacion.get("fecha_apertura") or ""
    plazo = f" Necesitaríamos la cotización antes del {apertura[:10]}." if apertura else ""

    cuerpo = f"""Estimados {proveedor}:

Mi nombre es {empresa['contacto']}, de {empresa['razon_social']} (CUIT {empresa['cuit']}), \
con sede en {empresa['ciudad']}. Estamos preparando una oferta para un proceso de compra \
de la Provincia del Chaco y nos interesa cotizar con ustedes los siguientes productos:

{chr(10).join(filas)}

Les agradeceríamos que nos indiquen:
  - Precio unitario (aclarando si incluye IVA) y condición de pago.
  - Plazo de entrega y costo de envío a {empresa['ciudad']}.
  - Marca/modelo ofrecido y validez de la cotización.
{plazo}

Quedamos atentos. Muchas gracias.

{empresa['contacto']}
{empresa['razon_social']}
{empresa['telefono']} · {empresa['email']}

--
Les escribimos porque su empresa publica estos productos a la venta. \
Si no desean recibir más consultas, respondan este correo con la palabra BAJA.
"""
    msg = EmailMessage()
    msg["Subject"] = asunto
    msg["From"] = f"{empresa['contacto']} <{empresa['email']}>"
    msg["To"] = destinatario
    msg["Reply-To"] = empresa["email"]
    if cc:
        msg["Cc"] = ", ".join(cc)
    msg["Date"] = formatdate(localtime=True)
    msg["Message-ID"] = make_msgid(domain=empresa["email"].rsplit("@", 1)[-1])
    msg.set_content(cuerpo)
    return msg


def guardar_borrador(msg: EmailMessage) -> str:
    carpeta = SALIDA / "emails"
    carpeta.mkdir(parents=True, exist_ok=True)
    nombre = re.sub(r"[^\w.-]+", "_", f"{msg['To']}_{msg['Subject']}")[:150] + ".eml"
    ruta = carpeta / nombre
    ruta.write_bytes(bytes(msg))
    return str(ruta)


class Remitente:
    def __init__(self, smtp: dict):
        if not smtp.get("host") or not smtp.get("user"):
            raise ValueError("Faltan SMTP_HOST / SMTP_USER / SMTP_PASSWORD en .env")
        self.smtp = smtp
        self._con: smtplib.SMTP | None = None

    def __enter__(self):
        ctx = ssl.create_default_context()
        if self.smtp["ssl"]:
            self._con = smtplib.SMTP_SSL(self.smtp["host"], self.smtp["port"], context=ctx, timeout=60)
        else:
            self._con = smtplib.SMTP(self.smtp["host"], self.smtp["port"], timeout=60)
            self._con.starttls(context=ctx)
        self._con.login(self.smtp["user"], self.smtp["password"])
        return self

    def enviar(self, msg: EmailMessage) -> None:
        assert self._con is not None
        self._con.send_message(msg)

    def __exit__(self, *exc):
        if self._con:
            try:
                self._con.quit()
            except smtplib.SMTPException:
                pass
