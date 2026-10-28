# Agente de búsqueda laboral (LinkedIn + CV de Canva)

Un agente de [Claude Code](https://code.claude.com) que hace esto por cada oferta:

1. Lee la oferta de LinkedIn y mide qué tan compatible sos.
2. Entra a tu carpeta de **Canva**, copia tu **CV base** y adapta la copia a esa oferta (resumen,
   orden de viñetas, palabras clave, habilidades) sin tocar el diseño.
3. Exporta la copia a PDF y la **baja a la carpeta `cvs/`** de tu máquina.
4. Abre la oferta en un navegador, hace clic en **Solicitud sencilla (Easy Apply)**, **sube ese PDF**
   y **completa todas las preguntas adicionales**: años de experiencia, sí/no, desplegables,
   textos libres, pretensión salarial, etc.
5. Te muestra un resumen y, cuando le decís que sí, envía la solicitud y la registra.

```
Vos: /postular https://www.linkedin.com/jobs/view/4012345678/

Canva ── carpeta "CVs" ── "CV Base" ──copia──► "CV - Acme - Dev PHP - 2026-10-28" (adaptado)
                                                        │ exportar PDF
                                                        ▼
                                  job-agent/cvs/CV_Juan_Orbez_Acme_2026-10-28.pdf
                                                        │ subir
                                                        ▼
LinkedIn ── Easy Apply ── contacto ── CV ── preguntas ── revisión ──(tu "sí")──► Enviada
```

## Qué necesitás

- **Claude Code** instalado y una cuenta de Claude (https://code.claude.com).
- **Node.js 18+**, que usa el navegador automatizado (Playwright).
- **Python 3.10+**, para la búsqueda y el registro de postulaciones.
- Una cuenta de **Canva** con una carpeta de CVs y un diseño base. Alcanza con el plan gratuito o
  Pro: el agente usa el conector oficial de Canva para Claude, no la API de Autofill, que es solo
  para Enterprise.

## Instalación (una sola vez)

```bash
git clone https://github.com/JuaniOrbez/JuaniOrbez.git
cd JuaniOrbez/job-agent
pip install -r requirements.txt

cp config.example.yaml config.yaml                     # nombre de tu carpeta y CV base de Canva
cp perfil/respuestas.example.yaml perfil/respuestas.yaml   # teléfono, preaviso, pretensión, etc.
cp data/cv_master.example.yaml data/cv_master.yaml     # opcional, ver abajo

claude                                                 # abre Claude Code en esta carpeta
```

Dentro de Claude Code:

1. Aceptá los servidores MCP del proyecto (`canva` y `playwright`) cuando te lo pregunte.
2. Escribí `/mcp`, elegí **canva** y autorizá tu cuenta de Canva en el navegador.
3. Pedile "abrí linkedin.com". Se abre una ventana de Chrome: iniciá sesión en LinkedIn **vos**.
   La sesión queda guardada en `.browser-profile/` para las próximas veces.

### Cómo preparar Canva

- Creá una carpeta (por ejemplo **CVs**) y poné ahí tu CV base, con el nombre que pusiste en
  `config.yaml` (`canva.cv_base`, por ejemplo **CV Base**).
- Conviene que cada sección (perfil, cada experiencia, habilidades) sea un cuadro de texto
  separado, con un poco de aire: el agente reescribe los textos manteniendo una longitud
  parecida para que nada se desborde.
- Si tenés versión en inglés, creá también **CV Base EN**: el agente usa la del idioma de la
  oferta.
- El agente **nunca modifica el CV base**: cada postulación genera una copia nueva en la misma
  carpeta.

### `data/cv_master.yaml` (opcional pero recomendado)

Tu CV de Canva entra en una página, así que seguro dejaste cosas afuera. Si las ponés en el CV
maestro (proyectos, logros, tecnologías), el agente puede elegir, para cada oferta, lo más
relevante. Nunca agrega nada que no esté en Canva o en este archivo.

### `perfil/respuestas.yaml`

Son las respuestas para las preguntas de las postulaciones: preaviso, si necesitás visa,
modalidad, pretensión salarial, años de experiencia por tecnología, nivel de inglés, preguntas
demográficas. Cuando aparece una pregunta nueva, el agente **te la hace a vos y la guarda acá**,
así que este archivo se completa solo con el uso.

## Uso

En Claude Code, dentro de `job-agent/`:

| Qué querés | Qué escribís |
|---|---|
| Postularte a una oferta | `/postular https://www.linkedin.com/jobs/view/...` |
| Buscar ofertas nuevas y elegir | `/buscar-ofertas` |
| Ver tu registro | `python -m job_agent list` (o pedile "mostrame mis postulaciones") |
| Actualizar un estado | "me llamaron de Acme", o `python -m job_agent status <id> entrevista` |

Lo que queda guardado de cada postulación:

- `cvs/CV_<nombre>_<empresa>_<fecha>.pdf`: el CV exacto que se envió.
- La copia adaptada en tu carpeta de Canva.
- `postulaciones/<fecha>-<empresa>.md`: puntaje, cambios en el CV y **todas las preguntas con la
  respuesta enviada**, para preparar la entrevista.
- `output/tracker.json`: el estado de cada oferta.

## Reglas del agente

Están en `CLAUDE.md` y el agente las sigue siempre:

- **No inventa.** Solo reformula lo que está en tu CV de Canva, en `cv_master.yaml` o en
  `respuestas.yaml`. Si una pregunta de LinkedIn no tiene respaldo (por ejemplo "¿tenés
  experiencia con Kubernetes?"), la respuesta honesta es "no", o te pregunta.
- **Te pide confirmación antes de enviar** (`postulacion.envio_automatico: false`). Si lo pasás a
  `true`, envía solo cuando todas las respuestas salieron de tus archivos; si tuvo que deducir
  algo, frena igual.
- **No resuelve CAPTCHAs ni verificaciones**, no crea cuentas en sitios de empresas y no escribe
  tu contraseña. En esos casos te pide que lo hagas vos en la ventana del navegador.
- **Ritmo humano:** como máximo `max_postulaciones_por_dia` (15 por defecto).

### Sobre el riesgo en LinkedIn

Los términos de LinkedIn no permiten automatizar acciones con una cuenta. Por eso el agente usa
un navegador real con tu sesión, va de a una postulación, te pide el "sí" final y respeta un
límite diario. Así el riesgo baja mucho, pero no es cero: usarlo es tu decisión. Si LinkedIn te
muestra una advertencia, frená unos días.

## Modo línea de comandos (sin Claude Code)

La carpeta `job_agent/` también funciona sola, con la API de Anthropic (`ANTHROPIC_API_KEY`):

```bash
python -m job_agent search             # busca ofertas públicas según config.yaml
python -m job_agent show <url|id>      # muestra la descripción completa
python -m job_agent run                # busca, puntúa y genera CVs .docx a partir de data/cv_master.yaml
python -m job_agent tailor <url|id>    # CV .docx adaptado para una oferta puntual
python -m job_agent tailor --file oferta.txt --company "Acme"
python -m job_agent list [--state postulada]
python -m job_agent log <url|id> --state postulada --cv-file cvs/x.pdf
python -m job_agent status <id> entrevista
```

Este modo genera el CV en Word a partir de `data/cv_master.yaml`. No usa Canva y no se postula.

## Problemas comunes

| Problema | Solución |
|---|---|
| "canva" aparece desconectado | `/mcp` → canva → volver a autenticar |
| El texto se desborda en Canva | Dejá más espacio en los cuadros del CV base o acortá el original |
| No aparece el botón Easy Apply | La oferta es externa; el agente sigue en el sitio de la empresa, pero frena si pide crear una cuenta |
| La búsqueda vuelve vacía | LinkedIn limitó el ritmo; esperá o pasale links a `/postular` |
| LinkedIn pide verificación | Resolvela vos en la ventana del navegador y decile "listo" |

## Estructura

```
CLAUDE.md                        reglas del agente
.mcp.json                        conectores: Canva (oficial) y navegador Playwright
.claude/skills/postular/         flujo completo de una postulación
.claude/skills/buscar-ofertas/   búsqueda y selección de ofertas
config.example.yaml              búsqueda, Canva y postulación
perfil/respuestas.example.yaml   respuestas a preguntas frecuentes
data/cv_master.example.yaml      CV maestro (opcional)
job_agent/                       CLI de Python: búsqueda, registro y modo sin Claude Code
```
