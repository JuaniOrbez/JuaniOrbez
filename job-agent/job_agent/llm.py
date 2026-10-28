"""Llamadas a Claude: evaluar compatibilidad, adaptar el CV y armar el kit de postulación."""

from __future__ import annotations

import anthropic
import yaml
from pydantic import BaseModel

from .models import ApplicationKit, FitAssessment, JobPosting, MasterCV, TailoredCV

RULES = """\
Sos un reclutador técnico y especialista en sistemas ATS (Applicant Tracking Systems).
Ayudás a un candidato a postularse a ofertas de LinkedIn.

Regla principal: la honestidad no se negocia. Solo podés usar hechos que estén en el
CV maestro. Podés reordenar, recortar, reformular y usar la terminología exacta de la
oferta cuando sea un sinónimo legítimo de algo que el candidato hizo (por ejemplo
"MySQL" -> "bases de datos relacionales (MySQL)"). No inventes empresas, cargos,
fechas, métricas, tecnologías, títulos ni años de experiencia. Si a la oferta le
falta algo que el candidato no tiene, se reporta como brecha, no se esconde.

Para que el CV pase los filtros ATS y llame la atención de una persona:
- Las keywords imprescindibles de la oferta tienen que aparecer textualmente cuando
  el CV las respalda.
- Viñetas que empiecen con verbo de acción y muestren resultado o impacto.
- Lo más relevante para esta oferta va primero.
- Frases concretas, sin relleno ni clichés ("proactivo", "apasionado", etc.).
"""


class ClaudeClient:
    def __init__(self, model: str = "claude-opus-5-5"):
        self.client = anthropic.Anthropic()
        self.model = model

    def _parse(self, prompt: str, output: type[BaseModel], effort: str) -> BaseModel:
        response = self.client.beta.messages.parse(
            model=self.model,
            max_tokens=16000,
            betas=["server-side-fallback-2026-07-01"],
            fallbacks="default",
            output_config={"effort": effort},
            system=RULES,
            messages=[{"role": "user", "content": prompt}],
            output_format=output,
        )
        if response.stop_reason == "refusal":
            raise RuntimeError("Claude rechazó la solicitud.")
        if response.parsed_output is None:
            raise RuntimeError(f"Respuesta sin datos (stop_reason={response.stop_reason}).")
        return response.parsed_output

    @staticmethod
    def _context(cv: MasterCV, job: JobPosting) -> str:
        cv_yaml = yaml.safe_dump(cv.model_dump(), allow_unicode=True, sort_keys=False)
        return (
            f"<cv_maestro>\n{cv_yaml}</cv_maestro>\n\n"
            f"<oferta>\nPuesto: {job.title}\nEmpresa: {job.company}\n"
            f"Ubicación: {job.location}\n\n{job.description}\n</oferta>"
        )

    def assess_fit(self, cv: MasterCV, job: JobPosting) -> FitAssessment:
        prompt = (
            f"{self._context(cv, job)}\n\n"
            "Evaluá qué tan compatible es el candidato con esta oferta. El puntaje es la "
            "probabilidad realista de pasar el primer filtro (ATS + recruiter), no un "
            "puntaje optimista. Penalizá fuerte si piden años de experiencia o seniority "
            "claramente por encima de lo que muestra el CV."
        )
        return self._parse(prompt, FitAssessment, effort="low")

    def tailor_cv(self, cv: MasterCV, job: JobPosting, fit: FitAssessment, language: str) -> TailoredCV:
        lang = fit.language if language == "auto" else language
        prompt = (
            f"{self._context(cv, job)}\n\n"
            f"<analisis>\nKeywords clave: {', '.join(fit.must_have_keywords)}\n"
            f"Respaldadas por el CV: {', '.join(fit.matched)}\n"
            f"Brechas: {', '.join(fit.gaps)}\n</analisis>\n\n"
            f"Armá una versión del CV adaptada a esta oferta, escrita en idioma '{lang}', "
            "que entre en una o dos páginas.\n"
            "- `experience` y `projects`: usá el `id` de la entrada del CV maestro en "
            "`source_id`. Omití lo que no aporte a esta oferta.\n"
            "- Cada viñeta reescrita tiene que listar en `source_ids` los ids de las "
            "viñetas maestras que la respaldan. Podés combinar dos viñetas en una.\n"
            "- `skills`: solo skills que estén en el CV maestro o que se desprendan "
            "directamente de una viñeta (en ese caso usá el nombre de la oferta).\n"
            "- `changes_note`: explicá brevemente qué ajustaste y qué brechas quedan."
        )
        return self._parse(prompt, TailoredCV, effort="high")

    def application_kit(self, cv: MasterCV, job: JobPosting, fit: FitAssessment, language: str) -> ApplicationKit:
        lang = fit.language if language == "auto" else language
        prompt = (
            f"{self._context(cv, job)}\n\n"
            f"Escribí en idioma '{lang}' el material para postularse: carta de "
            "presentación, mensaje corto para el recruiter y respuestas sugeridas a las "
            "preguntas de screening más probables (años de experiencia por tecnología, "
            "disponibilidad, por qué esta empresa, etc.). Si una respuesta depende de un "
            "dato que no está en el CV (pretensión salarial, disponibilidad), dejá "
            "[COMPLETAR] en lugar de inventarlo."
        )
        return self._parse(prompt, ApplicationKit, effort="medium")
