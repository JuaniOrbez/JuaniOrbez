# Agente de licitaciones – Provincia del Chaco

Agente en Python que:

1. **Busca licitaciones** en el portal de compras de la provincia ([compras.chaco.gob.ar](https://compras.chaco.gob.ar)), las filtra por tus rubros y descarta las que ya cerraron.
2. **Extrae los renglones** (productos, cantidades, especificaciones) de la página y de los pliegos PDF, usando Claude para leer el texto.
3. **Busca proveedores argentinos** con el mejor precio publicado para cada producto (Claude con búsqueda web), junto con su email de contacto.
4. **Pide cotización por email**: arma un solo correo por proveedor y licitación con todos los productos que vende. Por defecto **sólo genera borradores** (`.eml`) para que los revises; el envío real se activa aparte.

```
compras.chaco.gob.ar ──► scraper ──► Claude (extrae renglones) ──► SQLite
                                                                     │
          emails (.eml / SMTP) ◄── agrupar por proveedor ◄── Claude + búsqueda web
```

## Instalación

Requiere **Python 3.10 o superior** (`python3 --version`). El Python que trae la Mac
con las Command Line Tools es 3.9: instalá uno nuevo desde [python.org](https://www.python.org/downloads/)
o con `brew install python@3.12`.

```bash
git clone -b claude/compassionate-volta-qo97ae https://github.com/JuaniOrbez/JuaniOrbez.git
cd JuaniOrbez/agente-licitaciones-chaco
python3.12 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env              # completá ANTHROPIC_API_KEY y los datos SMTP
cp config.example.yaml config.yaml  # tus datos de empresa, rubros y límites
```

Para Gmail usá `smtp.gmail.com`, puerto `465` y una [contraseña de aplicación](https://myaccount.google.com/apppasswords) (no tu contraseña normal).

## Uso

```bash
python -m agente.main buscar        # 1-2. licitaciones + renglones
python -m agente.main proveedores   # 3. proveedores y precios
python -m agente.main cotizar       # 4. borradores en salida/emails/*.eml
python -m agente.main respuestas    # marca quién contestó (lee tu Gmail)
python -m agente.main planilla      # actualiza la planilla de proveedores en Drive
python -m agente.main reporte       # salida/reporte.csv (se abre en Excel)

python -m agente.main todo          # todo lo anterior
python -m agente.main cotizar --enviar   # envío real por SMTP
python -m agente.main buscar --url https://compras.chaco.gob.ar/organismos/6/licitaciones/2026/120
```

Todo queda en `datos/agente.db`, así que podés correrlo todos los días (por ejemplo con `cron`): no vuelve a analizar licitaciones ya vistas ni reenvía pedidos ya enviados.

## Planilla de proveedores en Google Drive

`python -m agente.main planilla` crea o actualiza una planilla de Google Sheets con dos hojas:

- **Proveedores**: una fila por proveedor, con los productos que vende, teléfono, email, sitio web,
  licitaciones, si se le envió el pedido, si respondió y si pidió la baja. La lista crece en cada
  corrida y no se borran los proveedores anteriores. Las columnas **Notas** y **Estado comercial**
  son para que escribas a mano: el agente las respeta.
- **Productos**: cada producto ofrecido con su precio, link y licitación.

`python -m agente.main respuestas` revisa la bandeja de entrada (IMAP, con la misma cuenta y
contraseña de aplicación del SMTP) y marca quién contestó. Si en la respuesta aparece la palabra
BAJA, agrega el email a `datos/bajas.txt`. Para que Gmail permita esto, IMAP tiene que estar
activado (Gmail → Configuración → Reenvío y correo POP/IMAP).

Configuración (una sola vez):

1. En [console.cloud.google.com](https://console.cloud.google.com) creá un proyecto y activá la
   **Google Sheets API** (APIs y servicios → Biblioteca).
2. APIs y servicios → Credenciales → Crear credenciales → **Cuenta de servicio**. Dentro de la
   cuenta creada: Claves → Agregar clave → JSON. Guardá el archivo descargado en la carpeta del
   agente como `credenciales-google.json` (no se sube a GitHub).
3. Creá una planilla vacía en Google Drive y **compartila como Editor** con el email de la cuenta
   de servicio (termina en `iam.gserviceaccount.com`, figura dentro del JSON como `client_email`).
4. Copiá el ID de la planilla (lo que está entre `/d/` y `/edit` en su link) en `.env`:
   `GOOGLE_SHEET_ID=...`

`python -m agente.main todo` actualiza la planilla y las respuestas automáticamente al final.

## Configuración (`config.yaml`)

| Sección | Qué controla |
|---|---|
| `empresa` | Datos que aparecen en el email (razón social, CUIT, contacto). |
| `portal` | Páginas de inicio, organismos a recorrer, límites y pausa entre pedidos. |
| `filtros.rubros` | Lo que vendés. Si la licitación no menciona la palabra exacta, Claude decide si es del rubro (ej. "artículos de oficina" cuenta como librería). Con `filtro_inteligente: false` sólo se usa la palabra exacta. No se aplica cuando pasás el link de una licitación puntual. |
| `filtros.solo_abiertas` | Ignorar procesos cuya apertura de sobres ya pasó. |
| `proveedores` | Cuántos proveedores por producto, tope de productos por licitación, dominios a excluir. |
| `email` | `enviar`, máximo de correos por corrida y pausa entre envíos. |

Para que un proveedor no reciba más correos, agregá su email (uno por línea) a `datos/bajas.txt`.

## Costos y límites a tener en cuenta

- Cada licitación analizada usa una llamada a Claude; cada producto usa una investigación web (búsquedas + lectura de páginas), que es lo más caro. Ajustá `max_items_por_licitacion` y `max_por_item` para controlar el gasto.
- Los precios encontrados son **precios publicados en la web**, sirven como referencia para elegir a quién pedir cotización; el precio real llega con la respuesta del proveedor.
- El scraper no depende del diseño exacto del portal: busca los enlaces `/organismos/{id}/licitaciones/{año}/{número}` y deja que Claude interprete el contenido. Si el portal cambia la estructura de URLs, ajustá `PATRON_DETALLE` en `agente/scraper.py`.
- Los PDFs escaneados (imágenes) no tienen texto extraíble; en ese caso el renglón puede quedar incompleto.
- Para participar en licitaciones del Chaco necesitás estar inscripto en el Registro de Proveedores de la provincia; el agente lista los requisitos de cada pliego, pero no hace ese trámite.

## Tests

```bash
pip install pytest
python -m pytest -q tests
```

Los tests corren sin red: simulan el portal y las respuestas de Claude.
