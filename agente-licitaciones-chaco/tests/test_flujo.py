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
    monkeypatch.setattr(scraper.Portal, "descargar", lambda self, adj, pagina: b"Pliego: resmas y biromes")

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
    evaluadas = []

    def relevancia_falsa(lic, rubros):
        evaluadas.append(lic.url)
        return extractor.Relevancia(relevante=False, motivo="no coincide")
    monkeypatch.setattr(extractor, "es_relevante", relevancia_falsa)

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

    # La licitación sin la palabra exacta se consultó a Claude y se descartó.
    assert evaluadas == ["https://compras.chaco.gob.ar/organismos/35/licitaciones/2025/4"]
    with db.conexion() as con:
        assert con.execute("SELECT COUNT(*) FROM licitaciones").fetchone()[0] == 1
        assert con.execute("SELECT COUNT(*) FROM items").fetchone()[0] == 2
        emails = con.execute("SELECT email, estado FROM emails").fetchall()
    # Un solo email al mayorista (con ambos productos); el dominio gob.ar se excluye.
    assert [tuple(e) for e in emails] == [("ventas@mayoristanea.com.ar", "borrador")]
    eml = next((tmp_path / "emails").glob("*.eml")).read_text("utf-8")
    assert "Resma A4 75 g" in eml and "Bol" in eml
    assert (tmp_path / "reporte.csv").exists()


def test_sinonimo_aceptado_por_claude(tmp_path, monkeypatch):
    """'Artículos de oficina' no contiene 'librería', pero Claude lo acepta."""
    monkeypatch.setattr(db, "DATOS", tmp_path)
    url = "https://compras.chaco.gob.ar/organismos/6/licitaciones/2026/200"
    html = "<html><body><main><h1>LP 200/2026</h1><p>Adquisición de artículos de oficina</p></main></body></html>"
    monkeypatch.setattr(scraper.Portal, "listar", lambda self: [url])
    monkeypatch.setattr(scraper.Portal, "_get", lambda self, u, **kw: RespFalsa(html))
    monkeypatch.setattr(extractor, "es_relevante",
                        lambda lic, rubros: extractor.Relevancia(relevante=True, motivo="oficina = librería"))
    analizadas = []

    def analizar_falso(lic):
        analizadas.append(lic.url)
        return extractor.DatosLicitacion(
            numero="LP 200/2026", tipo="", organismo="", objeto="", fecha_apertura=None,
            lugar_apertura="", requisitos_clave=[], es_de_bienes=True, renglones=[])
    monkeypatch.setattr(extractor, "analizar", analizar_falso)

    cfg = config.cargar(config.RAIZ / "config.example.yaml")
    main.cmd_buscar(cfg, argparse.Namespace(url=None))
    assert analizadas == [url]
