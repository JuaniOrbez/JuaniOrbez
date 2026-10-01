from datetime import date

from bs4 import BeautifulSoup

from agente import correo, extractor, proveedores, scraper
from pathlib import Path

FIX = Path(__file__).parent / "fixtures"


def sopa(nombre):
    return BeautifulSoup((FIX / nombre).read_text(encoding="utf-8"), "html.parser")


def test_extraer_enlaces_detecta_detalles_y_paginacion():
    detalles, siguientes = scraper.extraer_enlaces(
        sopa("listado.html"), "https://compras.chaco.gob.ar/", "compras.chaco.gob.ar")
    assert set(detalles) == {
        "https://compras.chaco.gob.ar/organismos/6/licitaciones/2026/120",
        "https://compras.chaco.gob.ar/organismos/35/licitaciones/2025/4",
    }
    assert detalles["https://compras.chaco.gob.ar/organismos/6/licitaciones/2026/120"] == (2026, 120)
    assert "https://compras.chaco.gob.ar/?page=2" in siguientes


def test_parsear_detalle():
    url = "https://compras.chaco.gob.ar/organismos/6/licitaciones/2026/120"
    lic = scraper.parsear_detalle(sopa("detalle.html"), url)
    assert lic.titulo.startswith("Licitación Pública N° 120/2026")
    assert lic.tablas[0][1] == ["1", "Resma papel A4 75 g", "500", "Resma"]
    assert [a.url for a in lic.adjuntos] == [
        "https://compras.chaco.gob.ar/uploads/pdfs/pliego-lp-120-2026.pdf"]
    assert "menu" not in lic.texto and "var x" not in lic.texto
    assert "Resma papel A4 75 g | 500" in lic.texto_para_analisis()


def test_coincide_rubros_sin_acentos():
    assert scraper.coincide_rubros("Adquisición de ARTICULOS DE LIBRERIA", ["librería"])
    assert not scraper.coincide_rubros("Obra de pavimento", ["librería"])
    assert scraper.coincide_rubros("cualquier cosa", [])


def _datos(fecha):
    return extractor.DatosLicitacion(
        numero="LP 1", tipo="pública", organismo="x", objeto="y", fecha_apertura=fecha,
        lugar_apertura="", requisitos_clave=[], es_de_bienes=True, renglones=[])


def test_esta_abierta():
    hoy = date(2026, 10, 1)
    assert extractor.esta_abierta(_datos("2026-10-15T10:00"), hoy)
    assert not extractor.esta_abierta(_datos("2026-09-01T10:00"), hoy)
    assert extractor.esta_abierta(_datos(None), hoy)
    assert extractor.esta_abierta(_datos("a confirmar"), hoy)


def test_email_contactable():
    excl = ["gob.ar"]
    assert proveedores.email_contactable("ventas@libreria.com.ar", excl)
    assert not proveedores.email_contactable("compras@chaco.gob.ar", excl)
    assert not proveedores.email_contactable("sin-arroba", excl)
    assert not proveedores.email_contactable("", excl)


def test_armar_email():
    empresa = {"razon_social": "Mi Empresa SRL", "cuit": "30-1", "contacto": "Juan",
               "email": "juan@empresa.com", "telefono": "123", "ciudad": "Resistencia"}
    msg = correo.armar(empresa, "Librería X", "ventas@x.com.ar",
                       {"numero": "LP 120/2026", "fecha_apertura": "2026-10-15T10:00"},
                       [{"descripcion": "Resma A4", "cantidad": 500.0, "unidad": "resma",
                         "especificaciones": "75 g"}])
    cuerpo = msg.get_content()
    assert msg["To"] == "ventas@x.com.ar"
    assert "LP 120/2026" in msg["Subject"]
    assert "Resma A4 — Cantidad: 500 resma" in cuerpo
    assert "antes del 2026-10-15" in cuerpo
    assert "BAJA" in cuerpo
