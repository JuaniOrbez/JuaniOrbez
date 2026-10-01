"""Búsqueda de proveedores argentinos con mejor precio para cada renglón."""
from __future__ import annotations

import re

from pydantic import BaseModel, Field

from . import llm

EMAIL_VALIDO = re.compile(r"^[\w.+-]+@[\w-]+(\.[\w-]+)+$")


class Oferta(BaseModel):
    proveedor: str = Field(description="Nombre comercial o razón social")
    email: str = Field(description="Email de ventas/contacto publicado por el proveedor; '' si no se encontró")
    telefono: str
    sitio_web: str
    url_producto: str = Field(description="URL donde se vio el producto/precio")
    producto: str = Field(description="Producto concreto ofrecido (marca/modelo)")
    precio: float | None = Field(description="Precio unitario publicado, null si no figura")
    moneda: str = Field(description="ARS o USD")
    precio_incluye_iva: bool | None
    provincia: str = Field(description="Provincia donde opera o despacha")
    notas: str = Field(description="Ej: precio mayorista, mínimo de compra, envía al Chaco")


class ResultadoBusqueda(BaseModel):
    ofertas: list[Oferta]


INSTRUCCIONES_INVESTIGACION = """Sos un comprador profesional que abastece licitaciones públicas
en la Provincia del Chaco, Argentina. Para el producto indicado, buscá en la web proveedores
ARGENTINOS (distribuidores, mayoristas, fabricantes o comercios) que lo vendan, priorizando:
1. Precio unitario más bajo publicado (en ARS).
2. Que vendan a empresas / por mayor y hagan envíos al NEA (Chaco, Corrientes) o estén cerca.
3. Que publiquen un email de contacto o ventas.
Para cada proveedor intentá abrir su página de contacto para obtener el email real.
Nunca inventes emails, precios ni URLs: reportá sólo lo que viste en las páginas.
No incluyas organismos públicos. Los marketplaces sirven como referencia de precio,
pero preferí al vendedor/distribuidor que tenga contacto directo.
Terminá con un listado claro: proveedor, email, teléfono, sitio, URL del producto,
producto, precio, moneda, si incluye IVA, provincia y notas."""

INSTRUCCIONES_ESTRUCTURA = """Convertí el informe de investigación en datos estructurados.
Copiá sólo datos presentes en el informe; si falta un dato dejalo vacío o null.
Ordená las ofertas de menor a mayor precio unitario (las sin precio al final)."""


def buscar(descripcion: str, especificaciones: str, cantidad: float | None,
           unidad: str, consulta: str, max_proveedores: int = 5) -> list[Oferta]:
    pedido = (
        f"Producto: {descripcion}\n"
        f"Especificaciones: {especificaciones or '-'}\n"
        f"Cantidad requerida: {cantidad or '-'} {unidad}\n"
        f"Sugerencia de búsqueda: {consulta}\n\n"
        f"Encontrá hasta {max_proveedores} proveedores argentinos con el mejor precio."
    )
    informe = llm.investigar(INSTRUCCIONES_INVESTIGACION, pedido)
    if not informe.strip():
        return []
    resultado = llm.extraer(ResultadoBusqueda, INSTRUCCIONES_ESTRUCTURA, informe)
    return resultado.ofertas[:max_proveedores]


def email_contactable(email: str, excluir_dominios: list[str]) -> bool:
    email = (email or "").strip().lower()
    if not EMAIL_VALIDO.match(email):
        return False
    dominio = email.rsplit("@", 1)[1]
    return not any(dominio == d or dominio.endswith("." + d) for d in excluir_dominios)
