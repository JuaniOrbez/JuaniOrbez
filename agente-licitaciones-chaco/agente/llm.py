"""Acceso a Claude: extracción estructurada e investigación con búsqueda web."""
from __future__ import annotations

import os
from typing import TypeVar

import anthropic
from pydantic import BaseModel

MODELO = os.getenv("CLAUDE_MODEL", "claude-opus-5-5")
# Si el clasificador de seguridad rechaza un pedido, la API reintenta
# automáticamente con el modelo de respaldo recomendado.
BETAS = ["server-side-fallback-2026-07-01"]

T = TypeVar("T", bound=BaseModel)

_cliente: anthropic.Anthropic | None = None


def cliente() -> anthropic.Anthropic:
    global _cliente
    if _cliente is None:
        _cliente = anthropic.Anthropic(max_retries=4)
    return _cliente


class RechazoModelo(RuntimeError):
    pass


def extraer(esquema: type[T], instrucciones: str, contenido: list | str,
            effort: str = "low") -> T:
    """Devuelve una instancia validada de `esquema` a partir del contenido."""
    resp = cliente().beta.messages.parse(
        model=MODELO,
        max_tokens=16000,
        betas=BETAS,
        fallbacks="default",
        output_config={"effort": effort},
        system=instrucciones,
        messages=[{"role": "user", "content": contenido}],
        output_format=esquema,
    )
    if resp.stop_reason == "refusal":
        raise RechazoModelo(str(resp.stop_details))
    if resp.parsed_output is None:
        raise RuntimeError(f"Respuesta sin datos estructurados (stop_reason={resp.stop_reason})")
    return resp.parsed_output


def investigar(instrucciones: str, pedido: str, max_busquedas: int = 8,
               effort: str = "medium", max_reanudaciones: int = 4) -> str:
    """Investiga en la web (búsqueda + lectura de páginas) y devuelve un informe en texto."""
    herramientas = [
        {
            "type": "web_search_20260209",
            "name": "web_search",
            "max_uses": max_busquedas,
            "user_location": {"type": "approximate", "country": "AR",
                              "region": "Chaco", "city": "Resistencia"},
        },
        {"type": "web_fetch_20260209", "name": "web_fetch", "max_uses": max_busquedas * 2},
    ]
    acumulado: list = []  # contenido del turno del asistente a través de pausas
    for _ in range(max_reanudaciones + 1):
        mensajes = [{"role": "user", "content": pedido}]
        if acumulado:
            mensajes.append({"role": "assistant", "content": acumulado})
        with cliente().beta.messages.stream(
            model=MODELO,
            max_tokens=32000,
            betas=BETAS,
            fallbacks="default",
            output_config={"effort": effort},
            system=instrucciones,
            tools=herramientas,
            messages=mensajes,
        ) as stream:
            resp = stream.get_final_message()
        if resp.stop_reason == "refusal":
            raise RechazoModelo(str(resp.stop_details))
        acumulado = acumulado + list(resp.content)
        if resp.stop_reason != "pause_turn":
            return "\n".join(b.text for b in acumulado if b.type == "text")
        # El servidor pausó un turno largo de búsquedas: se reenvía para continuar.
    raise RuntimeError("La investigación no terminó tras varias reanudaciones")
