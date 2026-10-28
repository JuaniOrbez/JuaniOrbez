"""Valida el CV adaptado contra el maestro y lo exporta a .docx y .md (formato apto ATS)."""

from __future__ import annotations

from pathlib import Path

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.shared import Pt

from .models import ApplicationKit, FitAssessment, JobPosting, MasterCV, TailoredCV

DEFAULT_TITLES = {
    "es": {
        "summary": "Perfil", "experience": "Experiencia", "projects": "Proyectos",
        "education": "Educación", "skills": "Habilidades", "languages": "Idiomas",
        "certifications": "Certificaciones",
    },
    "en": {
        "summary": "Summary", "experience": "Experience", "projects": "Projects",
        "education": "Education", "skills": "Skills", "languages": "Languages",
        "certifications": "Certifications",
    },
}


def validate(master: MasterCV, tailored: TailoredCV) -> list[str]:
    """Descarta todo lo que no tenga respaldo en el CV maestro. Devuelve advertencias."""
    warnings: list[str] = []
    valid_bullets = master.bullet_ids()
    entries = {"experience": {e.id for e in master.experience}, "projects": {p.id for p in master.projects}}

    for section, valid_entries in entries.items():
        kept = []
        for entry in getattr(tailored, section):
            if entry.source_id not in valid_entries:
                warnings.append(f"Se descartó una entrada de {section} sin respaldo: {entry.source_id}")
                continue
            ok_bullets = []
            for bullet in entry.bullets:
                if bullet.source_ids and set(bullet.source_ids) <= valid_bullets:
                    ok_bullets.append(bullet)
                else:
                    warnings.append(f"Se descartó una viñeta sin respaldo: {bullet.text[:70]}...")
            entry.bullets = ok_bullets
            kept.append(entry)
        setattr(tailored, section, kept)

    master_skills = {s.lower() for s in master.skills}
    for skill in tailored.skills:
        if skill.lower() not in master_skills:
            warnings.append(f"Skill nueva (verificá que sea cierta): {skill}")
    return warnings


def _blocks(master: MasterCV, tailored: TailoredCV, lang: str):
    """Genera el CV como una secuencia (tipo, contenido) común a docx y md."""
    titles = DEFAULT_TITLES.get(lang, DEFAULT_TITLES["en"])
    exp_by_id = {e.id: e for e in master.experience}
    proj_by_id = {p.id: p for p in master.projects}

    yield "name", master.name
    yield "headline", tailored.headline
    yield "contact", " | ".join(v for v in master.contact.values() if v)
    yield "section", titles["summary"]
    yield "para", tailored.summary

    if tailored.experience:
        yield "section", titles["experience"]
        for entry in tailored.experience:
            exp = exp_by_id[entry.source_id]
            place = f", {exp.location}" if exp.location else ""
            yield "item", (f"{exp.role} — {exp.company}{place}", f"{exp.start} – {exp.end}")
            for bullet in entry.bullets:
                yield "bullet", bullet.text

    if tailored.projects:
        yield "section", titles["projects"]
        for entry in tailored.projects:
            proj = proj_by_id[entry.source_id]
            yield "item", (proj.name, proj.url)
            for bullet in entry.bullets:
                yield "bullet", bullet.text

    if master.education:
        yield "section", titles["education"]
        for edu in master.education:
            dates = " – ".join(str(d) for d in (edu.start, edu.end) if d)
            yield "item", (f"{edu.degree} — {edu.institution}", dates)

    yield "section", titles["skills"]
    yield "para", ", ".join(tailored.skills)
    if master.languages:
        yield "section", titles["languages"]
        yield "para", ", ".join(master.languages)
    if master.certifications:
        yield "section", titles["certifications"]
        for cert in master.certifications:
            yield "bullet", cert


def to_docx(master: MasterCV, tailored: TailoredCV, lang: str, path: Path) -> None:
    doc = Document()
    style = doc.styles["Normal"]
    style.font.name = "Calibri"
    style.font.size = Pt(10.5)
    for section in doc.sections:
        section.top_margin = section.bottom_margin = Pt(42)
        section.left_margin = section.right_margin = Pt(50)

    for kind, value in _blocks(master, tailored, lang):
        if kind == "name":
            p = doc.add_paragraph()
            run = p.add_run(value)
            run.bold, run.font.size = True, Pt(18)
            p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        elif kind in ("headline", "contact"):
            p = doc.add_paragraph(value)
            p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        elif kind == "section":
            doc.add_heading(value.upper(), level=2)
        elif kind == "para":
            doc.add_paragraph(value)
        elif kind == "item":
            title, right = value
            p = doc.add_paragraph()
            p.add_run(title).bold = True
            if right:
                p.add_run(f"   {right}")
            p.paragraph_format.space_after = Pt(2)
        elif kind == "bullet":
            doc.add_paragraph(value, style="List Bullet")
    doc.save(path)


def to_markdown(master: MasterCV, tailored: TailoredCV, lang: str) -> str:
    lines: list[str] = []
    for kind, value in _blocks(master, tailored, lang):
        if kind == "name":
            lines.append(f"# {value}")
        elif kind in ("headline", "contact", "para"):
            lines.append(f"{value}\n")
        elif kind == "section":
            lines.append(f"\n## {value}")
        elif kind == "item":
            title, right = value
            lines.append(f"**{title}**" + (f" · {right}" if right else ""))
        elif kind == "bullet":
            lines.append(f"- {value}")
    return "\n".join(lines) + "\n"


def report(job: JobPosting, fit: FitAssessment, tailored: TailoredCV, warnings: list[str],
           kit: ApplicationKit | None) -> str:
    out = [
        f"# {job.title} — {job.company}",
        f"{job.location} · {job.url}\n",
        f"## Compatibilidad: {fit.score}/100",
        fit.reasoning + "\n",
        f"**Keywords clave:** {', '.join(fit.must_have_keywords)}",
        f"**Cubiertas:** {', '.join(fit.matched) or '—'}",
        f"**Brechas:** {', '.join(fit.gaps) or '—'}\n",
        "## Cambios en el CV",
        tailored.changes_note + "\n",
    ]
    if warnings:
        out += ["## ⚠️ Revisar", *[f"- {w}" for w in warnings], ""]
    if kit:
        out += ["## Carta de presentación", kit.cover_letter + "\n",
                "## Mensaje para el recruiter", kit.recruiter_message + "\n",
                "## Preguntas de screening probables"]
        for q, a in zip(kit.likely_questions, kit.suggested_answers):
            out += [f"**{q}**", f"{a}\n"]
    out += ["## Antes de postular", "- [ ] Leí el CV y es 100% cierto",
            "- [ ] Completé los [COMPLETAR]", "- [ ] Subí el .docx en la postulación",
            f"- [ ] Marqué como postulado: `python -m job_agent applied {job.job_id}`"]
    return "\n".join(out) + "\n"
