import email.message
import sys
import types

from agente import db, planilla, respuestas


def _base(tmp_path):
    ctx = db.conexion(tmp_path / "t.db")
    con = ctx.__enter__()
    con.execute("INSERT INTO licitaciones (url, numero, fecha_apertura, abierta, analizada) "
                "VALUES ('u1', 'LP 1/2026', '2026-12-01T10:00', 1, 1)")
    con.execute("INSERT INTO items (licitacion_url, renglon, descripcion) VALUES ('u1','1','Resma A4')")
    con.execute("INSERT INTO items (licitacion_url, renglon, descripcion) VALUES ('u1','2','Bolígrafo')")
    for item, precio in ((1, 100.0), (2, 50.0)):
        con.execute("""INSERT INTO ofertas (item_id, proveedor, email, telefono, sitio_web,
                       url_producto, producto, precio, moneda, precio_incluye_iva, provincia, notas)
                       VALUES (?, 'Mayorista NEA', 'ventas@nea.com.ar', '362-1', 'nea.com.ar',
                       ?, 'x', ?, 'ARS', 1, 'Chaco', '')""", (item, f"http://p/{item}", precio))
    con.execute("""INSERT INTO ofertas (item_id, proveedor, email, producto, precio, moneda, url_producto)
                   VALUES (1, 'Sin Mail SA', '', 'y', NULL, 'ARS', 'http://q')""")
    con.execute("""INSERT INTO emails (licitacion_url, email, proveedor, asunto, estado, fecha,
                   respuesta_fecha) VALUES ('u1','ventas@nea.com.ar','Mayorista NEA','a','enviado',
                   '2026-10-08 10:00:00','2026-10-09 08:30')""")
    return ctx, con


def test_filas_proveedores_agrupa_y_preserva_notas(tmp_path):
    ctx, con = _base(tmp_path)
    existentes = [
        {"Proveedor": "Mayorista NEA", "Email": "ventas@nea.com.ar", "Notas": "buen precio",
         "Estado comercial": "cliente"},
        {"Proveedor": "Viejo SRL", "Email": "viejo@x.com", "Productos que vende": "toner",
         "Email enviado": "Sí", "Notas": "cargado a mano"},
    ]
    filas = planilla.filas_proveedores(con, existentes)
    ctx.__exit__(None, None, None)
    por_email = {f[1]: dict(zip(planilla.COLUMNAS_PROVEEDORES, f)) for f in filas}
    nea = por_email["ventas@nea.com.ar"]
    assert nea["Productos que vende"] == "Bolígrafo; Resma A4"
    assert nea["Email enviado"] == "Sí" and nea["Respondió"] == "Sí"
    assert nea["Fecha respuesta"] == "2026-10-09 08:30"
    assert nea["Notas"] == "buen precio" and nea["Estado comercial"] == "cliente"
    assert por_email[""]["Proveedor"] == "Sin Mail SA"
    assert por_email[""]["Email enviado"] == "No"
    # Los proveedores que ya estaban en la planilla no se pierden (la lista crece).
    assert por_email["viejo@x.com"]["Notas"] == "cargado a mano"
    assert por_email["viejo@x.com"]["Email enviado"] == "Sí"


def test_filas_productos_ordenadas_por_precio(tmp_path):
    ctx, con = _base(tmp_path)
    filas = planilla.filas_productos(con)
    ctx.__exit__(None, None, None)
    assert [f[3] for f in filas] == ["Resma A4", "Resma A4", "Bolígrafo"]
    assert filas[0][4] == 100.0 and filas[1][4] == ""


def test_sincronizar_con_gspread_simulado(tmp_path, monkeypatch):
    ctx, con = _base(tmp_path)
    hojas = {}

    class Hoja:
        def __init__(self, titulo, datos=None):
            self.titulo, self.datos, self.row_count = titulo, datos or [], 1000

        def acell(self, ref):
            return types.SimpleNamespace(value=self.datos[0][0] if self.datos else None)

        def get_all_records(self):
            enc = self.datos[0]
            return [dict(zip(enc, f)) for f in self.datos[1:]]

        def clear(self):
            self.datos = []

        def update(self, valores, rango):
            self.datos = valores

        def freeze(self, rows):
            pass

        def format(self, rango, fmt):
            pass

    hojas["Proveedores"] = Hoja("Proveedores", [planilla.COLUMNAS_PROVEEDORES,
                                                ["Viejo", "v@x.com"] + [""] * 10 + ["nota", ""]])

    class Libro:
        url = "https://docs.google.com/spreadsheets/d/abc"

        def worksheet(self, t):
            if t not in hojas:
                raise NoEncontrada()
            return hojas[t]

        def add_worksheet(self, title, rows, cols):
            hojas[title] = Hoja(title)
            return hojas[title]

    class NoEncontrada(Exception):
        pass

    falso = types.SimpleNamespace(
        WorksheetNotFound=NoEncontrada,
        service_account=lambda filename: types.SimpleNamespace(open_by_key=lambda k: Libro()))
    monkeypatch.setitem(sys.modules, "gspread", falso)

    url = planilla.sincronizar(con, "cred.json", "abc")
    ctx.__exit__(None, None, None)
    assert url.endswith("/abc")
    emails = [f[1] for f in hojas["Proveedores"].datos[1:]]
    assert "v@x.com" in emails and "ventas@nea.com.ar" in emails
    assert len(hojas["Productos"].datos) == 4  # encabezado + 3 ofertas


def test_pide_baja():
    assert respuestas.pide_baja("BAJA")
    assert respuestas.pide_baja("Hola, por favor denme de baja. Gracias")
    assert not respuestas.pide_baja("Les paso la cotización adjunta.\n> responda BAJA si no desea")


def test_casilla_busca_respuesta(monkeypatch):
    msg = email.message.EmailMessage()
    msg["Subject"] = "Re: Pedido de cotización"
    msg["Date"] = "Fri, 09 Oct 2026 08:30:00 -0300"
    msg.set_content("Adjuntamos cotización.")
    buscados = []

    class ImapFalso:
        def search(self, charset, *criterios):
            buscados.append(criterios)
            return "OK", [b"7"]

        def fetch(self, num, partes):
            return "OK", [(b"7", bytes(msg))]

    c = respuestas.Casilla({"user": "a", "password": "b", "host": "h"})
    c.con = ImapFalso()
    r = c.buscar_respuesta("ventas@nea.com.ar", "2026-10-08 10:00:00")
    assert buscados == [("FROM", '"ventas@nea.com.ar"', "SINCE", "08-Oct-2026")]
    assert r == {"fecha": "2026-10-09 08:30", "asunto": "Re: Pedido de cotización", "baja": False}
