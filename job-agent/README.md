# Agente de búsqueda laboral (LinkedIn + CV adaptado)

Busca ofertas en LinkedIn, mide qué tan compatible sos con cada una y, para las que valen la pena,
genera **un CV adaptado a esa oferta** (en .docx, apto para sistemas ATS), una carta de presentación,
un mensaje para el recruiter y respuestas sugeridas a las preguntas de screening. Usa Claude
(API de Anthropic) para el análisis y la redacción.

## Cómo funciona

```
config.yaml ──► 1. Busca en LinkedIn (páginas públicas, sin login)
                2. Lee la descripción de cada oferta nueva
cv_master.yaml ► 3. Claude puntúa la compatibilidad (0-100) y detecta keywords y brechas
                4. Para las mejores: CV adaptado + carta + respuestas
                5. Valida que nada sea inventado
                6. Guarda todo en output/<id>-<empresa>/ y lo registra en output/tracker.json
Vos ──────────► 7. Revisás y te postulás desde LinkedIn (1-2 minutos por oferta)
```

### Por qué no se postula solo

El último clic lo hacés vos, y no es por falta de ganas de automatizarlo:

- **Tu cuenta.** Los términos de LinkedIn prohíben usar bots en una cuenta logueada. Postularse
  automáticamente con Easy Apply es una de las formas más rápidas de que te restrinjan el perfil.
- **Más respuestas.** Mandar 10 postulaciones revisadas y bien dirigidas consigue más entrevistas
  que mandar 200 genéricas.
- **Honestidad.** Firmás vos lo que se envía. Por eso cada postulación trae una checklist.

### Cómo se evita que el CV adaptado mienta

Vos escribís un **CV maestro** con todo lo que hiciste, y cada viñeta tiene un `id`. Claude puede
reordenar, recortar y reformular usando el vocabulario de la oferta, pero cada viñeta del CV
adaptado tiene que citar los `id` del maestro que la respaldan. Lo que no tiene respaldo se descarta
antes de generar el archivo. Si aparece una skill que no está en tu maestro, el agente te avisa
para que la revises.

## Instalación

Necesitás Python 3.10 o superior y una API key de Anthropic (https://console.anthropic.com).

```bash
cd job-agent
python -m venv .venv && source .venv/bin/activate   # en Windows: .venv\Scripts\activate
pip install -r requirements.txt
export ANTHROPIC_API_KEY="sk-ant-..."              # en Windows: set ANTHROPIC_API_KEY=...

cp config.example.yaml config.yaml
cp data/cv_master.example.yaml data/cv_master.yaml
```

Completá `data/cv_master.yaml` con tu información real. Conviene poner de más: cada proyecto,
cada logro y cada tecnología, con números cuando los tengas. El agente elige qué mostrar en
cada caso. Después ajustá en `config.yaml` qué puestos buscar, dónde, y el puntaje mínimo.

`config.yaml`, `data/cv_master.yaml` y `output/` están en `.gitignore`, así que tus datos
personales no se suben a GitHub.

## Uso

```bash
python -m job_agent run                 # busca, evalúa y prepara las mejores postulaciones
python -m job_agent search              # solo busca y registra ofertas nuevas
python -m job_agent tailor https://www.linkedin.com/jobs/view/4012345678/   # una oferta puntual
python -m job_agent tailor --file oferta.txt --company "Acme" --title "Dev PHP"  # oferta pegada a mano
python -m job_agent list                # registro ordenado por compatibilidad
python -m job_agent list --state adaptada
python -m job_agent applied 4012345678  # marcar como postulada
python -m job_agent status 4012345678 entrevista
```

Cada postulación preparada queda en `output/<id>-<empresa>/`:

| Archivo | Para qué sirve |
|---|---|
| `CV_<nombre>_<empresa>.docx` | El CV para subir en LinkedIn. Una columna, sin tablas: apto para ATS |
| `CV_<nombre>_<empresa>.md` | Lo mismo en texto, para revisarlo rápido |
| `postulacion.md` | Puntaje, brechas, cambios hechos, carta, mensaje al recruiter, respuestas y checklist |

`tailor --file` sirve para ofertas que no son de LinkedIn o cuando la búsqueda pública no
encuentra la descripción: copiás el texto de la oferta en un archivo y listo.

### Rutina sugerida

1. Corré `python -m job_agent run` una o dos veces por semana.
2. Abrí cada `postulacion.md`, revisá el CV y completá los `[COMPLETAR]`.
3. Postulate desde el link, subiendo el `.docx`. Si hay un recruiter visible, mandale el mensaje.
4. Marcala con `applied`, y después actualizá el estado con `status`.
5. Si una brecha aparece una y otra vez, probablemente valga la pena aprender esa tecnología o hacer un
   proyecto que la use, y agregarlo al CV maestro.

## Costo y límites

- Cada oferta evaluada es una llamada corta a Claude. Cada postulación preparada suma dos llamadas
  más largas. `max_tailored_per_run` limita el gasto por corrida.
- La búsqueda usa la vista pública de LinkedIn, con pausas entre solicitudes. Si LinkedIn cambia su
  HTML o te limita el ritmo (error 429), la búsqueda puede volver vacía. En ese caso usá
  `tailor <url>` o `tailor --file`.
- Modelo por defecto: `claude-opus-5-5`. Se cambia en `config.yaml`.

## Estructura

```
job_agent/
  cli.py       comandos y orquestación
  linkedin.py  búsqueda y lectura de ofertas públicas
  llm.py       prompts y llamadas a Claude (salidas estructuradas)
  models.py    CV maestro, ofertas y esquemas de respuesta
  render.py    validación anti-invención y exportación a .docx / .md
  tracker.py   registro de ofertas y estados
```
