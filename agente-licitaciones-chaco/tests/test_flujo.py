"""Prueba de punta a punta con el portal y Claude simulados (sin red)."""
import argparse
from pathlib import Path

from agente import config, db, extractor, llm, main, proveedores, scraper

FIX = Path(__file__).parent / "fixtures"
URL = "https://compras.chaco.gob.ar/organismos/6/licitaciones/2026/120"


class RespFalsa:
    def __init__(self, texto):
        self.text = texto
        self.encoding = self.apparent_encoding = "utf-8"

    def raise_for_status(self):
        pass


def test_flujo_completo(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DATOS", tmp_path)
    monkeypatch.setattr(config, "SALIDA", tmp_path)
    monkeypatch.setattr(db, "DATOS", tmp_path)
    monkeypatch.setattr(main.correo, "SALIDA", tmp_path)

    paginas = {"https://compras.chaco.gob.ar/": "listado.html", URL: "detalle.html"}

    def get_falso(self, url, **kw):
        nombre = paginas.get(url)
        return RespFalsa((FIX / nombre).read_text("utf-8") if nombre else "<html></html>")

    monkeypatch.setattr(scraper.Portal, "_get", get_falso)
    monkeypatch.setattr(scraper.Portal, "_texto_adjunto", lambda self, url: "Pliego: resmas y biromes")

    def analizar_falso(lic):
        return extractor.DatosLicitacion(
            numero="LP 120/2026", tipo="Licitación Pública", organismo="Educación",
            objeto="Librería", fecha_apertura="2999-10-15T10:00", lugar_apertura="Las Heras 95",
            requisitos_clave=[], es_de_bienes=True,
            renglones=[extractor.Renglon(renglon="1", descripcion="Resma A4 75 g", cantidad=500,
                                         unidad="resma", especificaciones="", busqueda="resma a4"),
                       extractor.Renglon(renglon="2", descripcion="Bolígrafo azul", cantidad=2000,
                                         unidad="unidad", especificaciones="", busqueda="birome azul")])
    monkeypatch.setattr(extractor, "analizar", analizar_falso)

    def buscar_falso(desc, *a, **k):
        base = dict(telefono="", sitio_web="", url_producto="", moneda="ARS",
                    precio_incluye_iva=True, provincia="Chaco", notas="")
        return [proveedores.Oferta(proveedor="Mayorista NEA", email="Ventas@MayoristaNEA.com.ar",
                                   producto=desc, precio=100.0, **base),
                proveedores.Oferta(proveedor="Estatal", email="compras@chaco.gob.ar",
                                   producto=desc, precio=1.0, **base)]
    monkeypatch.setattr(proveedores, "buscar", buscar_falso)

    cfg = config.cargar(config.RAIZ / "config.example.yaml")
    args = argparse.Namespace(url=None, enviar=False)
    main.cmd_buscar(cfg, args)
    main.cmd_proveedores(cfg, args)
    main.cmd_cotizar(cfg, args)
    main.cmd_reporte(cfg, args)

    with db.conexion() as con:
        assert con.execute("SELECT COUNT(*) FROM items").fetchone()[0] == 2
        emails = con.execute("SELECT email, estado FROM emails").fetchall()
    # Un solo email al mayorista (con ambos productos); el dominio gob.ar se excluye.
    assert [tuple(e) for e in emails] == [("ventas@mayoristanea.com.ar", "borrador")]
    eml = next((tmp_path / "emails").glob("*.eml")).read_text("utf-8")
    assert "Resma A4 75 g" in eml and "Bol" in eml
    assert (tmp_path / "reporte.csv").exists()
