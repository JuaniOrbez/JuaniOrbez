"""Convierte el texto de una licitación (página + pliegos) en datos estructurados."""
from __future__ import annotations

from datetime import date

from pydantic import BaseModel, Field

from . import llm
from .scraper import Licitacion


class Renglon(BaseModel):
    renglon: str = Field(description="Número de renglón/ítem tal como figura, o '' si no hay")
    descripcion: str = Field(description="Descripción del producto o servicio")
    cantidad: float | None = Field(description="Cantidad solicitada, null si no figura")
    unidad: str = Field(description="Unidad de medida (unidad, caja, resma, litro, etc.)")
    especificaciones: str = Field(description="Especificaciones técnicas, marca sugerida, normas")
    busqueda: str = Field(
        description="Consulta corta (3-8 palabras) para buscar este producto en comercios "
                    "argentinos, sin cantidades ni números de renglón")


class DatosLicitacion(BaseModel):
    numero: str = Field(description="Ej: 'Licitación Pública N° 123/2026'")
    tipo: str = Field(description="Licitación pública, privada, concurso de precios, contratación directa, etc.")
    organismo: str
    objeto: str = Field(description="Objeto de la contratación en una frase")
    fecha_apertura: str | None = Field(description="Fecha y hora de apertura en formato ISO 'AAAA-MM-DDTHH:MM', null si no figura")
    lugar_apertura: str
    requisitos_clave: list[str] = Field(description="Requisitos para participar: inscripción en registro de proveedores, garantías, valor del pliego, etc.")
    es_de_bienes: bool = Field(description="true si compra bienes/productos (no obra pública ni servicios puros)")
    renglones: list[Renglon]


INSTRUCCIONES = """Sos un analista de compras públicas de la Provincia del Chaco (Argentina).
Recibís el texto de una página del portal de compras y de sus pliegos adjuntos.
Extraé los datos del proceso y TODOS los renglones (ítems) que se piden cotizar,
sin inventar nada: si un dato no aparece, dejalo vacío o null. No repitas renglones.
Si el texto del pliego está incompleto, extraé lo que esté disponible."""


def analizar(lic: Licitacion) -> DatosLicitacion:
    return llm.extraer(DatosLicitacion, INSTRUCCIONES, lic.texto_para_analisis())


def esta_abierta(datos: DatosLicitacion, hoy: date | None = None) -> bool:
    """True si la apertura es hoy o posterior (o si no se pudo determinar)."""
    if not datos.fecha_apertura:
        return True
    try:
        apertura = date.fromisoformat(datos.fecha_apertura[:10])
    except ValueError:
        return True
    return apertura >= (hoy or date.today())
