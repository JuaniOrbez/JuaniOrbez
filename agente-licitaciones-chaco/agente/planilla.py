"""Planilla de proveedores en Google Sheets (se actualiza en cada corrida).

Hoja "Proveedores": una fila por proveedor, con productos, contacto y estado del pedido.
Hoja "Productos": una fila por producto ofrecido (precio, link, licitación).
Las columnas "Notas" y "Estado comercial" se escriben a mano y se respetan.
"""
from __future__ import annotations

from collections import defaultdict

COLUMNAS_PROVEEDORES = [
    "Proveedor", "Email", "Teléfono", "Sitio web", "Provincia", "Productos que vende",
    "Licitaciones", "Email enviado", "Fecha envío", "Respondió", "Fecha respuesta",
    "Pidió baja", "Notas", "Estado comercial",
]
COLUMNAS_MANUALES = ["Notas", "Estado comercial"]
COLUMNAS_PRODUCTOS = [
    "Proveedor", "Email", "Producto ofrecido", "Para el renglón", "Precio", "Moneda",
    "Incluye IVA", "Link", "Licitación", "Apertura",
]


def _clave(email: str, proveedor: str) -> str:
    return (email or "").strip().lower() or (proveedor or "").strip().lower()


def filas_proveedores(con, existentes: list[dict]) -> list[list]:
    """Combina la base local con lo que ya hay en la planilla (preserva columnas manuales)."""
    manuales = {_clave(r.get("Email", ""), r.get("Proveedor", "")): r for r in existentes}

    prov: dict[str, dict] = {}
    productos: dict[str, set] = defaultdict(set)
    licitaciones: dict[str, set] = defaultdict(set)
    for r in con.execute(
            """SELECT o.*, i.descripcion AS item, l.numero
               FROM ofertas o JOIN items i ON i.id=o.item_id
               JOIN licitaciones l ON l.url=i.licitacion_url ORDER BY o.id"""):
        k = _clave(r["email"], r["proveedor"])
        actual = prov.setdefault(k, {})
        for campo in ("proveedor", "email", "telefono", "sitio_web", "provincia"):
            if r[campo] and not actual.get(campo):
                actual[campo] = r[campo]
        productos[k].add(r["item"])
        if r["numero"]:
            licitaciones[k].add(r["numero"])

    envios: dict[str, dict] = {}
    for e in con.execute("SELECT * FROM emails ORDER BY fecha"):
        k = e["email"].lower()
        d = envios.setdefault(k, {"enviado": False, "fecha": "", "resp": "", "baja": False})
        if e["estado"] == "enviado":
            d["enviado"] = True
            d["fecha"] = d["fecha"] or e["fecha"][:16]
        if e["respuesta_fecha"]:
            d["resp"] = d["resp"] or e["respuesta_fecha"]
        d["baja"] = d["baja"] or bool(e["baja"])

    claves = list(prov) + [k for k in manuales if k not in prov]
    filas = []
    for k in claves:
        p = prov.get(k, {})
        previo = manuales.get(k, {})
        env = envios.get(k, {})
        fila = {
            "Proveedor": p.get("proveedor") or previo.get("Proveedor", ""),
            "Email": p.get("email") or previo.get("Email", ""),
            "Teléfono": p.get("telefono") or previo.get("Teléfono", ""),
            "Sitio web": p.get("sitio_web") or previo.get("Sitio web", ""),
            "Provincia": p.get("provincia") or previo.get("Provincia", ""),
            "Productos que vende": "; ".join(sorted(productos[k])) or previo.get("Productos que vende", ""),
            "Licitaciones": ", ".join(sorted(licitaciones[k])) or previo.get("Licitaciones", ""),
            "Email enviado": "Sí" if env.get("enviado") else (previo.get("Email enviado") or "No"),
            "Fecha envío": env.get("fecha") or previo.get("Fecha envío", ""),
            "Respondió": "Sí" if env.get("resp") else (previo.get("Respondió") or "No"),
            "Fecha respuesta": env.get("resp") or previo.get("Fecha respuesta", ""),
            "Pidió baja": "Sí" if env.get("baja") else (previo.get("Pidió baja") or ""),
        }
        for col in COLUMNAS_MANUALES:
            fila[col] = previo.get(col, "")
        filas.append([fila[c] for c in COLUMNAS_PROVEEDORES])
    return filas


def filas_productos(con) -> list[list]:
    filas = []
    for r in con.execute(
            """SELECT o.proveedor, o.email, o.producto, i.descripcion, o.precio, o.moneda,
                      o.precio_incluye_iva, o.url_producto, l.numero, l.fecha_apertura
               FROM ofertas o JOIN items i ON i.id=o.item_id
               JOIN licitaciones l ON l.url=i.licitacion_url
               ORDER BY l.fecha_apertura DESC, i.id, o.precio IS NULL, o.precio"""):
        iva = {1: "Sí", 0: "No"}.get(r["precio_incluye_iva"], "")
        filas.append([r["proveedor"], r["email"], r["producto"], r["descripcion"],
                      r["precio"] if r["precio"] is not None else "", r["moneda"], iva,
                      r["url_producto"], r["numero"], (r["fecha_apertura"] or "")[:16]])
    return filas


def _hoja(libro, titulo: str, columnas: int):
    import gspread

    try:
        return libro.worksheet(titulo)
    except gspread.WorksheetNotFound:
        return libro.add_worksheet(title=titulo, rows=1000, cols=columnas)


def _escribir(hoja, encabezado: list[str], filas: list[list]) -> None:
    hoja.clear()
    hoja.update([encabezado] + filas, "A1")
    hoja.freeze(rows=1)
    hoja.format("1:1", {"textFormat": {"bold": True}})


def sincronizar(con, credenciales: str, sheet_id: str) -> str:
    import gspread

    cliente = gspread.service_account(filename=credenciales)
    libro = cliente.open_by_key(sheet_id)
    hoja_prov = _hoja(libro, "Proveedores", len(COLUMNAS_PROVEEDORES))
    existentes = hoja_prov.get_all_records() if hoja_prov.row_count and hoja_prov.acell("A1").value else []
    _escribir(hoja_prov, COLUMNAS_PROVEEDORES, filas_proveedores(con, existentes))
    _escribir(_hoja(libro, "Productos", len(COLUMNAS_PRODUCTOS)), COLUMNAS_PRODUCTOS,
              filas_productos(con))
    return libro.url
