"""CLI del agente de licitaciones.

Uso:
    python -m agente.main buscar        # 1. busca licitaciones y extrae renglones
    python -m agente.main proveedores   # 2. busca proveedores con mejor precio
    python -m agente.main cotizar       # 3. genera (o envía) pedidos de cotización
    python -m agente.main reporte       # resumen en salida/reporte.csv
    python -m agente.main todo          # 1 + 2 + 3 + reporte
"""
from __future__ import annotations

import argparse
import csv
import json
import time
from collections import defaultdict
from pathlib import Path

import requests

from . import config, correo, db, extractor, llm, planilla, proveedores, respuestas, scraper


# --- 1. Licitaciones -------------------------------------------------------
def cmd_buscar(cfg: dict, args) -> None:
    portal = scraper.Portal(cfg)
    # Si se pasa una licitación puntual, ya la eligió el usuario: no se filtra por rubro.
    rubros = [] if args.url else (cfg["filtros"].get("rubros") or [])
    inteligente = cfg["filtros"].get("filtro_inteligente", True)
    print("Buscando licitaciones en", portal.base, "...")
    urls = [args.url] if args.url else portal.listar()
    print(f"  {len(urls)} licitaciones encontradas")

    with db.conexion() as con:
        for url in urls:
            # Las ya analizadas se saltean, salvo que se pida una licitación puntual.
            if not args.url and con.execute(
                    "SELECT 1 FROM licitaciones WHERE url=? AND analizada=1", (url,)).fetchone():
                continue
            try:
                lic = portal.detalle(url, leer_adjuntos=False)
            except requests.RequestException as e:
                print(f"  ! {url}: {e}")
                continue
            if not scraper.coincide_rubros(lic.texto + lic.titulo, rubros):
                # Puede que los renglones sólo estén en el pliego: miramos los PDFs.
                portal.cargar_adjuntos(lic)
                if not scraper.coincide_rubros(lic.texto_para_analisis(), rubros):
                    if not inteligente:
                        print(f"  - fuera de rubro: {lic.titulo[:80]}")
                        continue
                    # Sin coincidencia literal: Claude evalúa sinónimos y categorías afines.
                    try:
                        rel = extractor.es_relevante(lic, rubros)
                    except (llm.RechazoModelo, RuntimeError) as e:
                        print(f"    ! no se pudo evaluar el rubro: {e}")
                        continue
                    if not rel.relevante:
                        print(f"  - fuera de rubro: {lic.titulo[:80]} ({rel.motivo[:100]})")
                        continue
                    print(f"  + rubro afín: {rel.motivo[:120]}")
            else:
                portal.cargar_adjuntos(lic)

            print(f"  > analizando: {lic.titulo[:90]}")
            try:
                datos = extractor.analizar(lic)
            except (llm.RechazoModelo, RuntimeError) as e:
                print(f"    ! no se pudo analizar: {e}")
                continue
            abierta = extractor.esta_abierta(datos)
            con.execute(
                """INSERT OR REPLACE INTO licitaciones
                   (url, numero, organismo, objeto, tipo, fecha_apertura, lugar_apertura,
                    abierta, texto, adjuntos, analizada)
                   VALUES (?,?,?,?,?,?,?,?,?,?,1)""",
                (url, datos.numero, datos.organismo, datos.objeto, datos.tipo,
                 datos.fecha_apertura, datos.lugar_apertura, int(abierta),
                 lic.texto_para_analisis(), db.a_json([a.url for a in lic.adjuntos])),
            )
            for r in datos.renglones:
                con.execute(
                    """INSERT OR IGNORE INTO items
                       (licitacion_url, renglon, descripcion, cantidad, unidad,
                        especificaciones, busqueda) VALUES (?,?,?,?,?,?,?)""",
                    (url, r.renglon, r.descripcion, r.cantidad, r.unidad,
                     r.especificaciones, r.busqueda),
                )
            estado = "ABIERTA" if abierta else "cerrada"
            print(f"    {datos.numero} | apertura {datos.fecha_apertura} | {estado} | "
                  f"{len(datos.renglones)} renglones")
            for req in datos.requisitos_clave:
                print(f"      requisito: {req}")


# --- 2. Proveedores --------------------------------------------------------
def cmd_proveedores(cfg: dict, args) -> None:
    pcfg = cfg["proveedores"]
    filtro_abiertas = "AND l.abierta=1" if cfg["filtros"].get("solo_abiertas", True) else ""
    with db.conexion() as con:
        items = con.execute(
            f"""SELECT i.* FROM items i JOIN licitaciones l ON l.url=i.licitacion_url
                WHERE i.proveedores_buscados=0 {filtro_abiertas}
                ORDER BY l.fecha_apertura, i.id""").fetchall()
        por_lic: dict[str, int] = defaultdict(int)
        for it in items:
            if por_lic[it["licitacion_url"]] >= pcfg.get("max_items_por_licitacion", 15):
                continue
            por_lic[it["licitacion_url"]] += 1
            print(f"Buscando proveedores: {it['descripcion'][:80]}")
            try:
                ofertas = proveedores.buscar(
                    it["descripcion"], it["especificaciones"], it["cantidad"],
                    it["unidad"], it["busqueda"] or it["descripcion"],
                    pcfg.get("max_por_item", 5))
            except (llm.RechazoModelo, RuntimeError) as e:
                print(f"  ! error: {e}")
                continue
            for o in ofertas:
                con.execute(
                    """INSERT OR IGNORE INTO ofertas
                       (item_id, proveedor, email, telefono, sitio_web, url_producto,
                        producto, precio, moneda, precio_incluye_iva, provincia, notas)
                       VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (it["id"], o.proveedor, o.email.strip().lower(), o.telefono, o.sitio_web,
                     o.url_producto, o.producto, o.precio, o.moneda,
                     None if o.precio_incluye_iva is None else int(o.precio_incluye_iva),
                     o.provincia, o.notas))
                precio = f"{o.moneda} {o.precio:,.2f}" if o.precio else "s/precio"
                print(f"  · {o.proveedor[:40]:40} {precio:>18}  {o.email or '(sin email)'}")
            con.execute("UPDATE items SET proveedores_buscados=1 WHERE id=?", (it["id"],))
            con.commit()


# --- 3. Pedidos de cotización ---------------------------------------------
def _bajas() -> set[str]:
    ruta = config.DATOS / "bajas.txt"
    if not ruta.exists():
        return set()
    return {l.strip().lower() for l in ruta.read_text(encoding="utf-8").splitlines() if l.strip()}


def cmd_cotizar(cfg: dict, args) -> None:
    ecfg = cfg["email"]
    enviar = args.enviar or ecfg.get("enviar", False)
    excluir = cfg["proveedores"].get("excluir_dominios", [])
    bajas = _bajas()
    filtro_abiertas = "AND l.abierta=1" if cfg["filtros"].get("solo_abiertas", True) else ""

    with db.conexion() as con:
        filas = con.execute(
            f"""SELECT o.email, o.proveedor, i.*, l.numero, l.fecha_apertura, l.objeto
                FROM ofertas o JOIN items i ON i.id=o.item_id
                JOIN licitaciones l ON l.url=i.licitacion_url
                WHERE o.email != '' {filtro_abiertas}""").fetchall()

        # Un solo email por proveedor y licitación, con todos sus productos.
        grupos: dict[tuple[str, str], dict] = {}
        for f in filas:
            email = f["email"]
            if email in bajas or not proveedores.email_contactable(email, excluir):
                continue
            g = grupos.setdefault((f["licitacion_url"], email), {
                "proveedor": f["proveedor"], "items": {},
                "licitacion": {"numero": f["numero"], "fecha_apertura": f["fecha_apertura"]}})
            g["items"][f["id"]] = dict(f)

        pendientes = [(k, g) for k, g in grupos.items()
                      if not con.execute("SELECT 1 FROM emails WHERE licitacion_url=? AND email=?"
                                         " AND estado='enviado'", k).fetchone()]
        limite = ecfg.get("max_por_ejecucion", 20)
        print(f"{len(pendientes)} pedidos de cotización pendientes "
              f"({'ENVÍO REAL' if enviar else 'modo borrador'}; máx. {limite})")
        if not pendientes:
            return

        remitente = correo.Remitente(cfg["smtp"]) if enviar else None
        contexto = remitente if remitente else _Nulo()
        with contexto:
            for n, ((lic_url, email), g) in enumerate(pendientes[:limite]):
                msg = correo.armar(cfg["empresa"], g["proveedor"], email, g["licitacion"],
                                   list(g["items"].values()), ecfg.get("cc"))
                archivo = correo.guardar_borrador(msg)
                estado = "borrador"
                if remitente:
                    if n:
                        time.sleep(ecfg.get("pausa_segundos", 20))
                    try:
                        remitente.enviar(msg)
                        estado = "enviado"
                    except Exception as e:  # noqa: BLE001 - registrar y seguir
                        estado = f"error: {e}"
                con.execute(
                    """INSERT INTO emails (licitacion_url, email, proveedor, asunto, estado, archivo)
                       VALUES (?,?,?,?,?,?)
                       ON CONFLICT(licitacion_url, email) DO UPDATE SET
                       estado=excluded.estado, archivo=excluded.archivo,
                       fecha=CURRENT_TIMESTAMP""",
                    (lic_url, email, g["proveedor"], msg["Subject"], estado, archivo))
                con.commit()
                print(f"  [{estado}] {email} ({len(g['items'])} productos) -> {archivo}")


class _Nulo:
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


# --- Respuestas y planilla -------------------------------------------------
def cmd_respuestas(cfg: dict, args) -> None:
    """Marca qué proveedores contestaron, leyendo la bandeja de entrada por IMAP."""
    if not cfg["imap"]["user"]:
        print("Respuestas: falta configurar SMTP_USER / SMTP_PASSWORD en .env; se omite.")
        return
    with db.conexion() as con:
        pendientes = con.execute(
            """SELECT id, email, fecha FROM emails
               WHERE estado='enviado' AND respuesta_fecha IS NULL""").fetchall()
        print(f"Revisando respuestas de {len(pendientes)} proveedores...")
        if not pendientes:
            return
        nuevas_bajas = []
        with respuestas.Casilla(cfg["imap"]) as casilla:
            for p in pendientes:
                r = casilla.buscar_respuesta(p["email"], p["fecha"])
                if not r:
                    continue
                con.execute("UPDATE emails SET respuesta_fecha=?, respuesta_asunto=?, baja=? "
                            "WHERE id=?", (r["fecha"] or "sí", r["asunto"], int(r["baja"]), p["id"]))
                print(f"  ✓ {p['email']} respondió ({r['fecha']}): {r['asunto'][:60]}"
                      + ("  [pidió BAJA]" if r["baja"] else ""))
                if r["baja"]:
                    nuevas_bajas.append(p["email"])
        if nuevas_bajas:
            ruta = config.DATOS / "bajas.txt"
            with open(ruta, "a", encoding="utf-8") as f:
                f.write("".join(e + "\n" for e in nuevas_bajas))


def cmd_planilla(cfg: dict, args) -> None:
    """Actualiza la planilla de proveedores en Google Sheets."""
    g = cfg["google"]
    if not g["sheet_id"]:
        print("Planilla: falta GOOGLE_SHEET_ID en .env; se omite.")
        return
    if not Path(g["credenciales"]).exists():
        print(f"Planilla: no encuentro el archivo de credenciales {g['credenciales']}; se omite.")
        return
    with db.conexion() as con:
        url = planilla.sincronizar(con, g["credenciales"], g["sheet_id"])
    print("Planilla actualizada:", url)


# --- Diagnóstico -----------------------------------------------------------
def cmd_diagnostico(cfg: dict, args) -> None:
    """Muestra qué ve el agente en una página del portal, para ajustar el scraper."""
    from bs4 import BeautifulSoup
    from urllib.parse import urljoin

    portal = scraper.Portal(cfg)
    resp = portal._get(args.url)
    resp.encoding = resp.apparent_encoding or resp.encoding
    carpeta = config.SALIDA / "diagnostico"
    carpeta.mkdir(parents=True, exist_ok=True)
    archivo = carpeta / (args.url.rstrip("/").rsplit("/", 1)[-1] + ".html")
    archivo.write_text(resp.text, encoding="utf-8")

    sopa = BeautifulSoup(resp.text, "html.parser")
    print(f"HTML guardado en: {archivo} ({len(resp.text):,} caracteres)")
    print(f"Tablas: {len(sopa.find_all('table'))}")
    for i, t in enumerate(sopa.find_all("table"), 1):
        filas = t.find_all("tr")
        primera = filas[0].get_text(" | ", strip=True)[:150] if filas else ""
        print(f"  tabla {i}: {len(filas)} filas · {primera}")
    for tag in sopa.find_all("iframe", src=True):
        print(f"Iframe: {urljoin(args.url, tag['src'])}")
    for tag in sopa.find_all("script", src=True):
        print(f"Script: {urljoin(args.url, tag['src'])}")
    for f in sopa.find_all("form"):
        print(f"Formulario: action={f.get('action')} method={f.get('method')}")
    lic = scraper.parsear_detalle(BeautifulSoup(resp.text, "html.parser"), args.url)
    print(f"Adjuntos detectados: {len(lic.adjuntos)}")
    for a in lic.adjuntos:
        print(f"  - {a.nombre[:60]} -> {a.url}")
    print("Enlaces de la página:")
    vistos = set()
    for a in sopa.find_all("a", href=True):
        href = urljoin(args.url, a["href"])
        if href in vistos or href.startswith(("mailto:", "javascript:")):
            continue
        vistos.add(href)
        print(f"  [{a.get_text(' ', strip=True)[:50]}] {href}")
        if len(vistos) >= 80:
            print("  ...")
            break
    for adj in lic.adjuntos:
        datos = portal.descargar(adj, args.url)
        if datos is None:
            continue
        ruta = scraper.guardar_adjunto(args.url, adj.nombre, datos)
        texto_adj = scraper.texto_archivo(datos)
        print(f"\nDescargado '{adj.nombre}' ({len(datos):,} bytes) -> {ruta}")
        print(f"  primeros 800 caracteres:\n{texto_adj[:800]}")
    texto = lic.texto
    print(f"\nTexto visible ({len(texto):,} caracteres), primeros 1500:\n{texto[:1500]}")


# --- Reporte ---------------------------------------------------------------
def cmd_reporte(cfg: dict, args) -> None:
    ruta = config.SALIDA / "reporte.csv"
    with db.conexion() as con, open(ruta, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f, delimiter=";")
        w.writerow(["licitacion", "organismo", "apertura", "abierta", "renglon", "producto",
                    "cantidad", "unidad", "proveedor", "precio", "moneda", "incluye_iva",
                    "email", "telefono", "url_producto", "url_licitacion"])
        for r in con.execute(
                """SELECT l.numero, l.organismo, l.fecha_apertura, l.abierta, i.renglon,
                          i.descripcion, i.cantidad, i.unidad, o.proveedor, o.precio, o.moneda,
                          o.precio_incluye_iva, o.email, o.telefono, o.url_producto, l.url
                   FROM licitaciones l JOIN items i ON i.licitacion_url=l.url
                   LEFT JOIN ofertas o ON o.item_id=i.id
                   ORDER BY l.fecha_apertura, i.id, o.precio IS NULL, o.precio"""):
            w.writerow(list(r))
        resumen = {
            "licitaciones": con.execute("SELECT COUNT(*) FROM licitaciones").fetchone()[0],
            "abiertas": con.execute("SELECT COUNT(*) FROM licitaciones WHERE abierta=1").fetchone()[0],
            "renglones": con.execute("SELECT COUNT(*) FROM items").fetchone()[0],
            "ofertas": con.execute("SELECT COUNT(*) FROM ofertas").fetchone()[0],
            "emails": dict(con.execute(
                "SELECT estado, COUNT(*) FROM emails GROUP BY estado").fetchall()),
        }
    print(json.dumps(resumen, ensure_ascii=False, indent=2))
    print("Reporte:", ruta)


def main() -> None:
    p = argparse.ArgumentParser(description="Agente de licitaciones – Provincia del Chaco")
    p.add_argument("--config", help="ruta a config.yaml")
    sub = p.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("buscar", help="buscar licitaciones y extraer renglones")
    b.add_argument("url_posicional", nargs="?", metavar="URL", help="analizar sólo esta licitación")
    b.add_argument("--url", help="analizar sólo esta licitación")
    sub.add_parser("proveedores", help="buscar proveedores con mejor precio")
    c = sub.add_parser("cotizar", help="generar/enviar pedidos de cotización")
    c.add_argument("--enviar", action="store_true", help="enviar de verdad por SMTP")
    sub.add_parser("reporte", help="exportar salida/reporte.csv")
    sub.add_parser("respuestas", help="marcar qué proveedores contestaron (lee el correo)")
    sub.add_parser("planilla", help="actualizar la planilla de proveedores en Google Sheets")
    d = sub.add_parser("diagnostico", help="mostrar qué ve el agente en una página")
    d.add_argument("url")
    t = sub.add_parser("todo", help="buscar + proveedores + cotizar + reporte")
    t.add_argument("--url")
    t.add_argument("--enviar", action="store_true")
    args = p.parse_args()

    if getattr(args, "url_posicional", None) and not args.url:
        args.url = args.url_posicional
    cfg = config.cargar(args.config)
    pasos = {
        "buscar": [cmd_buscar], "proveedores": [cmd_proveedores],
        "cotizar": [cmd_cotizar], "reporte": [cmd_reporte],
        "diagnostico": [cmd_diagnostico],
        "respuestas": [cmd_respuestas], "planilla": [cmd_planilla],
        "todo": [cmd_buscar, cmd_proveedores, cmd_cotizar, cmd_respuestas,
                 cmd_planilla, cmd_reporte],
    }[args.cmd]
    for paso in pasos:
        paso(cfg, args)


if __name__ == "__main__":
    main()
