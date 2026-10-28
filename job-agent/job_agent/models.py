"""Modelos de datos: CV maestro, ofertas y salidas del LLM."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class _YamlModel(BaseModel):
    # En YAML "2023" se lee como número; lo aceptamos como texto.
    model_config = ConfigDict(coerce_numbers_to_str=True)


# ---------- CV maestro (lo escribe el usuario) ----------

class Bullet(_YamlModel):
    id: str
    text: str


class Experience(_YamlModel):
    id: str
    company: str
    role: str
    location: str = ""
    start: str
    end: str = "presente"
    bullets: list[Bullet] = []


class Project(_YamlModel):
    id: str
    name: str
    url: str = ""
    bullets: list[Bullet] = []


class Education(_YamlModel):
    id: str
    institution: str
    degree: str
    start: str = ""
    end: str = ""


class MasterCV(_YamlModel):
    name: str
    headline: str
    contact: dict[str, str] = {}
    summary: str
    experience: list[Experience] = []
    projects: list[Project] = []
    education: list[Education] = []
    skills: list[str] = []
    languages: list[str] = []
    certifications: list[str] = []

    def bullet_ids(self) -> set[str]:
        ids = set()
        for item in [*self.experience, *self.projects]:
            ids.update(b.id for b in item.bullets)
        return ids


# ---------- Ofertas ----------

class JobPosting(BaseModel):
    job_id: str
    title: str
    company: str
    location: str = ""
    url: str = ""
    posted: str = ""
    description: str = ""


# ---------- Salidas estructuradas de Claude ----------

class FitAssessment(BaseModel):
    score: int = Field(description="0-100: probabilidad realista de pasar el filtro inicial")
    language: str = Field(description="Idioma de la oferta: 'es' o 'en'")
    must_have_keywords: list[str] = Field(description="Requisitos/keywords clave que el ATS va a buscar")
    matched: list[str] = Field(description="Keywords que el CV maestro respalda con evidencia real")
    gaps: list[str] = Field(description="Requisitos que el CV maestro NO respalda")
    reasoning: str = Field(description="2-3 frases explicando el puntaje")


class TailoredBullet(BaseModel):
    text: str = Field(description="Viñeta reescrita para la oferta")
    source_ids: list[str] = Field(description="ids de las viñetas del CV maestro que respaldan esta viñeta")


class TailoredEntry(BaseModel):
    source_id: str = Field(description="id de la experiencia o proyecto del CV maestro")
    bullets: list[TailoredBullet]


class TailoredCV(BaseModel):
    headline: str = Field(description="Título profesional alineado al puesto, sin exagerar seniority")
    summary: str = Field(description="Resumen de 2-4 líneas orientado a la oferta")
    experience: list[TailoredEntry] = Field(description="Experiencias en el orden a mostrar (solo las relevantes)")
    projects: list[TailoredEntry] = Field(description="Proyectos en el orden a mostrar (pueden ir vacíos)")
    skills: list[str] = Field(description="Skills del CV maestro, ordenadas por relevancia, usando la terminología de la oferta")
    changes_note: str = Field(description="Qué se cambió y por qué (para que el usuario revise)")


class ApplicationKit(BaseModel):
    cover_letter: str = Field(description="Carta breve (150-250 palabras), concreta, sin clichés")
    recruiter_message: str = Field(description="Mensaje corto (<300 caracteres) para enviar al recruiter por LinkedIn")
    likely_questions: list[str] = Field(description="Preguntas de screening probables")
    suggested_answers: list[str] = Field(description="Respuesta sugerida para cada pregunta, basada solo en el CV maestro")
