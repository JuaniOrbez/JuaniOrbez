"""Recolección de licitaciones del portal de compras de la Provincia del Chaco.

El portal (https://compras.chaco.gob.ar) publica cada proceso en URLs del tipo
    /organismos/{id_organismo}/licitaciones/{año}/{número}
El scraper no depende de clases CSS concretas: busca enlaces con ese patrón,
descarga cada detalle, conserva el texto y las tablas, y baja los pliegos PDF.
La interpretación (renglones, fechas, etc.) la hace luego `extractor.py`.
"""
from __future__ import annotations

import io
import re
import time
import unicodedata
from dataclasses import dataclass, field
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

PATRON_DETALLE = re.compile(r"/organismos/(\d+)/licitaciones/(\d{4})/(\d+)/?$")
PATRON_PAGINACION = re.compile(r"[?&](page|pagina)=\d+")
EXT_ADJUNTOS = (".pdf", ".doc", ".docx", ".xls", ".xlsx", ".odt", ".ods")
MAX_BYTES_ADJUNTO = 15 * 1024 * 1024
MAX_CHARS_TEXTO = 120_000

UA = ("Mozilla/5.0 (X11; Linux x86_64) AgenteLicitacionesChaco/1.0 "
      "(+consulta de licitaciones publicas)")


@dataclass
class Adjunto:
    url: str
    nombre: str
    texto: str = ""


@dataclass
class Licitacion:
    url: str
    titulo: str
    texto: str
    tablas: list[list[list[str]]] = field(default_factory=list)
    adjuntos: list[Adjunto] = field(default_factory=list)

    def texto_para_analisis(self) -> str:
        partes = [f"URL: {self.url}", f"TÍTULO: {self.titulo}", "", self.texto]
        for i, tabla in enumerate(self.tablas, 1):
            partes.append(f"\n--- TABLA {i} ---")
            partes.extend(" | ".join(fila) for fila in tabla)
        for adj in self.adjuntos:
            if adj.texto:
                partes.append(f"\n--- ADJUNTO: {adj.nombre} ---\n{adj.texto}")
        return "\n".join(partes)[:MAX_CHARS_TEXTO]


def normalizar(texto: str) -> str:
    sin_acentos = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode()
    return re.sub(r"\s+", " ", sin_acentos).lower()


class Portal:
    def __init__(self, cfg: dict):
        self.cfg = cfg["portal"]
        self.base = self.cfg["base_url"].rstrip("/")
        self.host = urlparse(self.base).netloc
        self.sesion = requests.Session()
        self.sesion.headers["User-Agent"] = UA
        self._ultimo = 0.0

    # --- HTTP -------------------------------------------------------------
    def _get(self, url: str, **kw) -> requests.Response:
        espera = self.cfg.get("pausa_segundos", 1.5) - (time.monotonic() - self._ultimo)
        if espera > 0:
            time.sleep(espera)
        try:
            resp = self.sesion.get(url, timeout=40, **kw)
        finally:
            self._ultimo = time.monotonic()
        resp.raise_for_status()
        return resp

    def _sopa(self, url: str) -> BeautifulSoup:
        resp = self._get(url)
        resp.encoding = resp.apparent_encoding or resp.encoding
        return BeautifulSoup(resp.text, "html.parser")

    # --- Listados ---------------------------------------------------------
    def paginas_inicio(self) -> list[str]:
        paginas = list(self.cfg.get("paginas_inicio") or [self.base + "/"])
        anio = time.localtime().tm_year
        for org in self.cfg.get("organismos") or []:
            paginas.append(f"{self.base}/organismos/{org}/licitaciones")
            paginas.append(f"{self.base}/organismos/{org}/licitaciones/{anio}")
        return paginas

    def listar(self) -> list[str]:
        """Devuelve URLs de detalle de licitaciones, las más nuevas primero."""
        pendientes = self.paginas_inicio()
        visitadas: set[str] = set()
        detalles: dict[str, tuple[int, int]] = {}
        limite = self.cfg.get("max_paginas_listado", 10)
        while pendientes and len(visitadas) < limite:
            url = pendientes.pop(0)
            if url in visitadas:
                continue
            visitadas.add(url)
            try:
                sopa = self._sopa(url)
            except requests.RequestException as e:
                print(f"  ! no se pudo leer {url}: {e}")
                continue
            nuevos_detalles, siguientes = extraer_enlaces(sopa, url, self.host)
            detalles.update(nuevos_detalles)
            pendientes.extend(u for u in siguientes if u not in visitadas)
        ordenadas = sorted(detalles, key=lambda u: detalles[u], reverse=True)
        return ordenadas[: self.cfg.get("max_licitaciones", 40)]

    # --- Detalle ----------------------------------------------------------
    def detalle(self, url: str, leer_adjuntos: bool = True) -> Licitacion:
        sopa = self._sopa(url)
        lic = parsear_detalle(sopa, url)
        if leer_adjuntos:
            self.cargar_adjuntos(lic)
        return lic

    def cargar_adjuntos(self, lic: Licitacion) -> Licitacion:
        for adj in lic.adjuntos:
            if not adj.texto:
                adj.texto = self._texto_adjunto(adj.url)
        return lic

    def _texto_adjunto(self, url: str) -> str:
        if not urlparse(url).path.lower().endswith(".pdf"):
            return ""
        try:
            resp = self._get(url, stream=True)
            datos = resp.raw.read(MAX_BYTES_ADJUNTO + 1, decode_content=True)
        except requests.RequestException as e:
            print(f"  ! no se pudo descargar {url}: {e}")
            return ""
        if len(datos) > MAX_BYTES_ADJUNTO:
            print(f"  ! adjunto demasiado grande, se omite: {url}")
            return ""
        return texto_pdf(datos)


def extraer_enlaces(sopa: BeautifulSoup, url_base: str, host: str
                    ) -> tuple[dict[str, tuple[int, int]], list[str]]:
    """Separa enlaces a detalles de licitación y enlaces de paginación."""
    detalles: dict[str, tuple[int, int]] = {}
    siguientes: list[str] = []
    for a in sopa.find_all("a", href=True):
        abs_url = urljoin(url_base, a["href"]).split("#")[0]
        partes = urlparse(abs_url)
        if partes.netloc != host:
            continue
        m = PATRON_DETALLE.search(partes.path)
        if m:
            detalles[abs_url.rstrip("/")] = (int(m.group(2)), int(m.group(3)))
        elif PATRON_PAGINACION.search(abs_url) or "/licitaciones" in partes.path:
            siguientes.append(abs_url)
    return detalles, siguientes


def parsear_detalle(sopa: BeautifulSoup, url: str) -> Licitacion:
    for basura in sopa(["script", "style", "noscript", "nav", "footer", "header"]):
        basura.decompose()
    titulo = ""
    for selector in ("h1", "h2", "title"):
        nodo = sopa.find(selector)
        if nodo and nodo.get_text(strip=True):
            titulo = nodo.get_text(" ", strip=True)
            break

    tablas = []
    for tabla in sopa.find_all("table"):
        filas = []
        for tr in tabla.find_all("tr"):
            celdas = [c.get_text(" ", strip=True) for c in tr.find_all(["th", "td"])]
            if any(celdas):
                filas.append(celdas)
        if filas:
            tablas.append(filas)

    adjuntos, vistos = [], set()
    for a in sopa.find_all("a", href=True):
        abs_url = urljoin(url, a["href"])
        ruta = urlparse(abs_url).path.lower()
        etiqueta = a.get_text(" ", strip=True)
        if (ruta.endswith(EXT_ADJUNTOS) or "descargar" in ruta or "/uploads/" in ruta) \
                and abs_url not in vistos:
            vistos.add(abs_url)
            adjuntos.append(Adjunto(url=abs_url, nombre=etiqueta or ruta.rsplit("/", 1)[-1]))

    principal = sopa.find("main") or sopa.body or sopa
    texto = re.sub(r"\n\s*\n+", "\n\n", principal.get_text("\n", strip=True))
    return Licitacion(url=url, titulo=titulo, texto=texto, tablas=tablas, adjuntos=adjuntos)


def texto_pdf(datos: bytes, max_paginas: int = 40) -> str:
    import pdfplumber

    partes = []
    try:
        with pdfplumber.open(io.BytesIO(datos)) as pdf:
            for pagina in pdf.pages[:max_paginas]:
                partes.append(pagina.extract_text() or "")
    except Exception as e:  # PDFs escaneados o dañados
        return f"[no se pudo leer el PDF: {e}]"
    texto = "\n".join(partes).strip()
    return texto or "[PDF sin texto extraíble: probablemente escaneado]"


def coincide_rubros(texto: str, rubros: list[str]) -> bool:
    if not rubros:
        return True
    t = normalizar(texto)
    return any(normalizar(r) in t for r in rubros)
