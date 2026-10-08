import base64
import html
import json

from bs4 import BeautifulSoup

from agente import scraper

URL = "https://compras.chaco.gob.ar/organismos/6/licitaciones/2026/4796"
SNAPSHOT = json.dumps({"data": {"x": 1}, "memo": {"id": "abc", "name": "licitacion"}, "checksum": "z"})
HTML = f"""<html><head><meta name="csrf-token" content="TOKEN123"></head><body>
<header><h1>Compras Gobierno Chaco</h1></header>
<div wire:snapshot="{html.escape(SNAPSHOT)}" wire:id="abc">
<table><tr><td>Concurso de Precios                 N° 4796/2026</td></tr></table>
<p>Objeto del Llamado: ADQUISICION DE INSUMOS DE LABORATORIO</p>
<ul class="list-group">
 <li><span>OFERTA ECONOMICA</span>
  <button class="btn" wire:click="downloadFile(2026,6,4796,3,'OFERTA ECONOMICA')"></button></li>
</ul></div>
<script src="/vendor/livewire/livewire.js?id=1" data-csrf="TOKEN123" data-update-uri="/livewire/update"></script>
</body></html>"""


class Resp:
    def __init__(self, cuerpo):
        self._cuerpo = cuerpo

    def json(self):
        return self._cuerpo


def test_detecta_boton_livewire_y_titulo():
    lic = scraper.parsear_detalle(BeautifulSoup(HTML, "html.parser"), URL)
    assert lic.titulo == "Concurso de Precios N° 4796/2026"
    [adj] = lic.adjuntos
    assert adj.nombre == "OFERTA ECONOMICA"
    assert adj.livewire["metodo"] == "downloadFile"
    assert adj.livewire["params"] == [2026, 6, 4796, 3, "OFERTA ECONOMICA"]
    assert adj.livewire["version"] == 3 and adj.livewire["snapshot"] == SNAPSHOT
    assert adj.livewire["csrf"] == "TOKEN123"
    assert adj.livewire["endpoint"] == "/livewire/update"


def test_descarga_livewire_v3(monkeypatch):
    lic = scraper.parsear_detalle(BeautifulSoup(HTML, "html.parser"), URL)
    pedidos = []
    pdf = b"%PDF-1.4 contenido"

    def pedir(self, metodo, url, **kw):
        pedidos.append((metodo, url, json.loads(kw["data"]), kw["headers"]))
        return Resp({"components": [{"snapshot": "{}", "effects": {"download": {
            "name": "oferta.pdf", "content": base64.b64encode(pdf).decode()}}}]})

    monkeypatch.setattr(scraper.Portal, "_pedir", pedir)
    portal = scraper.Portal({"portal": {"base_url": "https://compras.chaco.gob.ar"}})
    assert portal.descargar(lic.adjuntos[0], URL) == pdf
    metodo, url, cuerpo, cab = pedidos[0]
    assert (metodo, url) == ("POST", "https://compras.chaco.gob.ar/livewire/update")
    assert cuerpo["_token"] == "TOKEN123" and cab["X-CSRF-TOKEN"] == "TOKEN123"
    assert cuerpo["components"][0]["snapshot"] == SNAPSHOT
    assert cuerpo["components"][0]["calls"] == [
        {"path": "", "method": "downloadFile", "params": [2026, 6, 4796, 3, "OFERTA ECONOMICA"]}]


def test_descarga_livewire_v2(monkeypatch):
    inicial = {"fingerprint": {"id": "x", "name": "licitacion-detalle"}, "serverMemo": {"data": {}}}
    html_v2 = (f'<div wire:id="x" wire:initial-data="{html.escape(json.dumps(inicial))}">'
               "<li>PLIEGO <button wire:click=\"downloadFile(2026,6,4796,2,'PLIEGO')\"></button></li></div>"
               "<script>window.livewire_token = 'TOK2';</script>")
    lic = scraper.parsear_detalle(BeautifulSoup(html_v2, "html.parser"), URL)
    pedidos = []

    def pedir(self, metodo, url, **kw):
        pedidos.append((url, json.loads(kw["data"])))
        return Resp({"effects": {"download": {"content": base64.b64encode(b"%PDF x").decode()}}})

    monkeypatch.setattr(scraper.Portal, "_pedir", pedir)
    portal = scraper.Portal({"portal": {"base_url": "https://compras.chaco.gob.ar"}})
    assert portal.descargar(lic.adjuntos[0], URL) == b"%PDF x"
    url, cuerpo = pedidos[0]
    assert url == "https://compras.chaco.gob.ar/livewire/message/licitacion-detalle"
    assert cuerpo["updates"][0]["payload"]["method"] == "downloadFile"
    assert lic.adjuntos[0].livewire["csrf"] == "TOK2"
