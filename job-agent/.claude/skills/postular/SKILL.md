---
name: postular
description: Postularse a una oferta de LinkedIn. Copia el CV base de Canva, lo adapta a la oferta, baja el PDF a cvs/ y completa la solicitud en LinkedIn (Easy Apply o sitio externo) con todas las preguntas adicionales. Usar cuando pase un link de una oferta o diga "postulame a ...".
argument-hint: <url de la oferta en LinkedIn>
---

# Postular a una oferta

Antes de empezar, leé `config.yaml`, `perfil/respuestas.yaml` y, si existe, `data/cv_master.yaml`.
Las reglas de `CLAUDE.md` valen en todos los pasos. La principal es que no se inventa nada.

## 1. Entender la oferta

1. Corré `python -m job_agent show <url>` para obtener la descripción. Si vuelve vacía, abrí la
   URL en el navegador (`playwright`) y leé la descripción de la página.
2. `show` también muestra el estado de la oferta y cuántas postulaciones lleva hoy. Si ya está
   `postulada`, avisale y no sigas. Si ya llegó a `postulacion.max_postulaciones_por_dia`,
   avisale y frená.
3. Sacá en limpio:
   - puesto, empresa e idioma de la oferta;
   - requisitos excluyentes y deseables;
   - las keywords que va a buscar un ATS.
4. Compará con su CV y dale un puntaje de compatibilidad (0-100) con una línea de explicación,
   las keywords cubiertas y las brechas. Si el puntaje es menor que
   `matching.min_fit_score`, preguntale si igual quiere seguir.

## 2. CV adaptado en Canva

1. Buscá en Canva la carpeta `canva.carpeta` y, adentro, el diseño `canva.cv_base`. Si hay
   varios parecidos (por ejemplo "CV Base ES" y "CV Base EN"), usá el del idioma de la oferta o
   preguntale.
2. Leé todo el contenido de texto del diseño base. Junto con `data/cv_master.yaml`, esa es la
   única fuente de hechos.
3. **Hacé una copia** del diseño base y nombrala según `canva.nombre_copia` (la fecha va como
   AAAA-MM-DD). Movela a la misma carpeta. Si el servidor de Canva no tiene una herramienta para
   copiar diseños, pedile que lo duplique en Canva (Archivo → Hacer una copia), que te diga el
   nombre de la copia, y seguí con esa. **Nunca edites el diseño base.**
4. Planificá los cambios texto por texto:
   - Título profesional alineado al puesto, sin subir el seniority.
   - Resumen o perfil reescrito para esta oferta, con sus keywords cubiertas.
   - En cada experiencia, las viñetas más relevantes primero, con el vocabulario de la oferta.
   - Habilidades ordenadas por relevancia, solo las que ya tiene.
   - Mantené la longitud de cada texto parecida a la original (±15%) para que el diseño no se
     desborde. No agregues ni borres cuadros de texto salvo que haga falta, y nunca cambies
     fechas, empresas, cargos ni contacto.
5. Aplicá los cambios en la copia con las herramientas de edición de Canva: abrir una
   transacción de edición, reemplazar los textos y confirmar los cambios (commit). Si algo falla
   a mitad de camino, cancelá la transacción y volvé a intentar.
6. Revisá el resultado con la vista previa o las páginas del diseño: tiene que seguir teniendo
   la misma cantidad de páginas y ningún texto cortado o encimado. Si algo se desbordó,
   acortalo.

## 3. Bajar el PDF

1. Exportá la copia a PDF (calidad estándar) con la herramienta de exportación de Canva.
2. Descargá el archivo desde el link que devuelve a la carpeta local
   `postulacion.carpeta_local_cvs`:
   `mkdir -p cvs && curl -sSL -o "cvs/CV_<Nombre>_<Empresa>_<AAAA-MM-DD>.pdf" "<url>"`
   (sin espacios ni tildes en el nombre del archivo).
3. Verificá que el archivo exista y pese más de 10 KB. Ese PDF es el que se sube; no subas otro.

## 4. Postularse en LinkedIn

Usá el navegador `playwright`. Para leer cada pantalla preferí el snapshot de accesibilidad
(`browser_snapshot`) antes que las capturas de pantalla.

1. Abrí la URL de la oferta. Si LinkedIn pide iniciar sesión, pedile que inicie sesión en la
   ventana del navegador y esperá a que te avise. Nunca escribas su contraseña.
2. Si hay botón **"Solicitud sencilla" / "Easy Apply"**, hacé clic y recorré cada paso:
   - **Datos de contacto:** controlá email y teléfono contra `perfil/respuestas.yaml`.
   - **Currículum:** subí el PDF de `cvs/` (ruta absoluta) con la herramienta de subida de
     archivos y dejalo seleccionado en lugar de cualquier CV viejo. Si piden carta de
     presentación, escribí una breve (150-250 palabras, concreta, en el idioma de la oferta).
   - **Preguntas adicionales:** ver la sección 5.
   - Después de cada "Siguiente", leé si aparecieron errores de validación ("Ingresá un número
     entero", "Este campo es obligatorio") y corregilos.
3. Si solo hay botón **"Solicitar" / "Apply"** que lleva al sitio de la empresa (Greenhouse,
   Lever, Workday, etc.): seguí ahí con las mismas reglas. Si el sitio pide **crear una cuenta**,
   frená y preguntale.
4. En la pantalla de **revisión**, antes de enviar, mostrale un resumen:

   ```
   Oferta: <puesto> — <empresa>   Compatibilidad: <n>/100
   CV: cvs/<archivo>.pdf   Canva: <link de la copia>
   Respuestas:
   - <pregunta> → <respuesta>   (fuente: CV / respuestas.yaml / te pregunté)
   ```

   - Con `envio_automatico: false`, esperá su "sí".
   - Con `true`, enviá solo si todas las respuestas tienen fuente CV o `respuestas.yaml`.
5. Hacé clic en "Enviar solicitud" y confirmá que aparezca el mensaje de enviada. Si LinkedIn
   pregunta por "Seguir a la empresa", dejá la opción como venga salvo que te pida otra cosa.

## 5. Preguntas adicionales

Leé el texto exacto de cada pregunta y el tipo de campo (texto, número, desplegable, sí/no,
casilla, texto largo). Resolvé cada una en este orden:

1. **`perfil/respuestas.yaml`**: datos, disponibilidad, situación legal, pretensión, idiomas,
   años de experiencia, preguntas demográficas y respuestas guardadas en `otras`.
2. **Su CV** (base de Canva y `data/cv_master.yaml`):
   - **Años de experiencia con X:** sumá los períodos de los trabajos y proyectos en que usó X,
     redondeá hacia abajo y usá un número entero. Si X no aparece en ningún lado, la respuesta
     es 0. No redondees hacia arriba.
   - **"¿Tenés experiencia con X?" (sí/no):** respondé "sí" solo si está en el CV.
3. **Texto libre** ("¿Por qué te interesa?", "Contanos de un proyecto"): escribí algo breve y
   específico para esta empresa, basado en hechos del CV.
4. **Si no está en ningún lado** (pretensión vacía, preguntas legales nuevas, certificaciones,
   "¿te referenció alguien?"), **preguntale**. Junta todas las preguntas pendientes de la
   pantalla en un solo mensaje. Después agregá cada respuesta nueva a `perfil/respuestas.yaml`
   (en la sección que corresponda, o en `otras`) para no volver a preguntar.

En un desplegable, elegí la opción que coincida con la respuesta. Si ninguna coincide exacto,
elegí la más cercana sin exagerar (con 2 años y opciones "1-2" y "3-5", va "1-2").

## 6. Registrar

1. `python -m job_agent log <url> --title "<puesto>" --company "<empresa>" --state postulada --cv-file "cvs/<archivo>.pdf" --canva "<link de la copia>"`
2. Guardá `postulaciones/<AAAA-MM-DD>-<empresa>.md` con:
   - puesto, link, puntaje, keywords y brechas;
   - qué cambió en el CV;
   - todas las preguntas con la respuesta enviada.
   Le va a servir para preparar la entrevista.
3. Contale en dos o tres líneas cómo quedó, con la ruta del PDF y el link de Canva.

## Si algo sale mal

- **CAPTCHA o verificación:** pedile que la resuelva en el navegador.
- **El botón no aparece o la oferta está cerrada** ("Ya no se aceptan solicitudes"): avisale y
  registrala con `--state descartada`.
- **Canva no responde o pide autorizar:** pedile que corra `/mcp` en Claude Code y autentique
  Canva.
- **Ya se había postulado** ("Solicitud enviada hace X días"): no vuelvas a postular; registrala
  como `postulada`.
