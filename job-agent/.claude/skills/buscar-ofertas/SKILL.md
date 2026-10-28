---
name: buscar-ofertas
description: Buscar ofertas nuevas en LinkedIn según config.yaml, puntuarlas contra su CV y proponer a cuáles postularse. Usar cuando diga "buscame trabajos", "qué ofertas hay" o similar.
---

# Buscar ofertas

1. Corré `python -m job_agent search`. Busca en las páginas públicas de LinkedIn con los
   filtros de `config.yaml` y registra solo las ofertas que no se vieron antes.
2. Para cada oferta nueva (como máximo 20 por vez), corré `python -m job_agent show <id>` y
   puntuala de 0 a 100 contra su CV. Tomá como CV el diseño base de Canva (`canva.cv_base`) y, si
   existe, `data/cv_master.yaml`. Sé realista: si piden más seniority o años de los que tiene,
   el puntaje baja.
3. Mostrale una tabla ordenada por puntaje con estas columnas: puntaje, puesto, empresa,
   modalidad, la brecha principal y el link. Marcá las que superan `matching.min_fit_score`.
4. Las que quedan por debajo del mínimo registralas como descartadas:
   `python -m job_agent log <id> --state descartada`.
5. Preguntale a cuáles quiere postularse. Para cada una que elija, seguí el skill `/postular`
   de a una por vez, respetando `postulacion.max_postulaciones_por_dia`.

Si la búsqueda vuelve vacía (LinkedIn limitó el ritmo o cambió su página), decíselo y ofrecele
pegar links de ofertas que haya encontrado por su cuenta.
