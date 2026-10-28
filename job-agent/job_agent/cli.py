"""Línea de comandos del agente.

  python -m job_agent run                  busca, evalúa y adapta el CV a las mejores ofertas
  python -m job_agent search               solo busca y registra ofertas nuevas
  python -m job_agent tailor <url|id>      adapta el CV a una oferta puntual
  python -m job_agent tailor --file x.txt  ... o a una oferta pegada en un archivo de texto
  python -m job_agent list [--state X]     muestra el registro de ofertas
  python -m job_agent applied <id>         marca una oferta como postulada
  python -m job_agent status <id> <estado> cambia el estado (entrevista, rechazada, oferta...)
  python -m job_agent show <url|id>        muestra la descripción completa de una oferta
  python -m job_agent log <url|id> ...     registra una postulación hecha (lo usa el skill /postular)
"""

from __future__ import annotations

import argparse
import re
import sys
from datetime import date
from pathlib import Path

import yaml

from . import linkedin, render
from .llm import ClaudeClient
from .models import JobPosting, MasterCV
from .tracker import STATES, Tracker

ROOT = Path(__file__).resolve().parent.parent
OUTPUT = ROOT / "output"


def load_config(path: Path) -> dict:
    if not path.exists():
        sys.exit(f"Falta {path.name}. Copiá config.example.yaml a config.yaml y ajustalo.")
    return yaml.safe_load(path.read_text())


def load_cv(path: Path) -> MasterCV:
    if not path.exists():
        sys.exit(f"Falta {path}. Copiá data/cv_master.example.yaml a data/cv_master.yaml y completalo.")
    return MasterCV.model_validate(yaml.safe_load(path.read_text()))


def _excluded(job: JobPosting, search_cfg: dict) -> bool:
    title = job.title.lower()
    if any(word.lower() in title for word in search_cfg.get("exclude_title_words", [])):
        return True
    return job.company.lower() in {c.lower() for c in search_cfg.get("exclude_companies", [])}


def do_search(cfg: dict, tracker: Tracker) -> list[JobPosting]:
    s = cfg["search"]
    new_jobs: dict[str, JobPosting] = {}
    with linkedin.make_client() as http:
        for keywords in s["keywords"]:
            for location in s["locations"]:
                print(f"Buscando '{keywords}' en {location}...")
                results = linkedin.search(
                    http, keywords, location,
                    posted_within_days=s.get("posted_within_days"),
                    remote=s.get("remote", False),
                    experience_levels=s.get("experience_levels"),
                    max_results=s.get("max_results_per_query", 25),
                )
                for job in results:
                    if tracker.seen(job.job_id) or job.job_id in new_jobs:
                        continue
                    if _excluded(job, s):
                        tracker.upsert(job.job_id, state="descartada", reason="filtro", job=job.model_dump())
                        continue
                    new_jobs[job.job_id] = job
    for job in new_jobs.values():
        tracker.upsert(job.job_id, job=job.model_dump())
    tracker.save()
    print(f"{len(new_jobs)} ofertas nuevas.")
    return list(new_jobs.values())


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:40]


def tailor_one(job: JobPosting, cv: MasterCV, cfg: dict, claude: ClaudeClient, tracker: Tracker,
               fit=None, force: bool = False) -> Path | None:
    if not job.description:
        print(f"  Sin descripción para {job.job_id}; no se puede adaptar.")
        return None
    fit = fit or claude.assess_fit(cv, job)
    tracker.upsert(job.job_id, job=job.model_dump(), score=fit.score)
    min_score = cfg["matching"]["min_fit_score"]
    if fit.score < min_score and not force:
        tracker.upsert(job.job_id, state="descartada", reason=f"score {fit.score} < {min_score}")
        tracker.save()
        print(f"  {fit.score}/100 — descartada ({fit.reasoning})")
        return None

    language = cfg["cv"].get("language", "auto")
    lang = fit.language if language == "auto" else language
    print(f"  {fit.score}/100 — adaptando CV ({lang})...")
    tailored = claude.tailor_cv(cv, job, fit, language)
    warnings = render.validate(cv, tailored)
    kit = claude.application_kit(cv, job, fit, language) if cfg["cv"].get("generate_cover_letter") else None

    folder = OUTPUT / f"{job.job_id}-{_slug(job.company)}"
    folder.mkdir(parents=True, exist_ok=True)
    cv_name = f"CV_{_slug(cv.name).replace('-', '_')}_{_slug(job.company)}"
    render.to_docx(cv, tailored, lang, folder / f"{cv_name}.docx")
    (folder / f"{cv_name}.md").write_text(render.to_markdown(cv, tailored, lang))
    (folder / "postulacion.md").write_text(render.report(job, fit, tailored, warnings, kit))

    tracker.upsert(job.job_id, state="adaptada", folder=str(folder))
    tracker.save()
    for w in warnings:
        print(f"  ⚠️  {w}")
    print(f"  Listo: {folder}/")
    return folder


def cmd_run(args, cfg, tracker):
    cv = load_cv(args.cv)
    claude = ClaudeClient(cfg["llm"]["model"])
    jobs = do_search(cfg, tracker)
    if not jobs:
        return

    print("\nLeyendo descripciones y evaluando compatibilidad...")
    scored = []
    with linkedin.make_client() as http:
        for job in jobs:
            try:
                linkedin.fetch_description(http, job)
            except Exception as exc:  # una oferta caída no frena el resto
                print(f"  No pude leer {job.url}: {exc}")
                continue
            fit = claude.assess_fit(cv, job)
            tracker.upsert(job.job_id, job=job.model_dump(), score=fit.score)
            print(f"  {fit.score:3d}  {job.title} — {job.company}")
            scored.append((fit, job))
    tracker.save()

    scored.sort(key=lambda pair: pair[0].score, reverse=True)
    limit = cfg["matching"]["max_tailored_per_run"]
    print(f"\nAdaptando CV para las mejores (máximo {limit})...")
    done = 0
    for fit, job in scored:
        if done >= limit:
            break
        print(f"- {job.title} — {job.company}")
        if tailor_one(job, cv, cfg, claude, tracker, fit=fit):
            done += 1
    print(f"\n{done} postulaciones preparadas en output/. Revisalas y postulate desde LinkedIn.")


def cmd_search(args, cfg, tracker):
    for job in do_search(cfg, tracker):
        print(f"  {job.job_id}  {job.title} — {job.company} ({job.location})")


def cmd_tailor(args, cfg, tracker):
    cv = load_cv(args.cv)
    claude = ClaudeClient(cfg["llm"]["model"])
    if args.file:
        text = Path(args.file).read_text()
        job = JobPosting(job_id=args.target or f"manual-{_slug(Path(args.file).stem)}",
                         title=args.title or Path(args.file).stem, company=args.company or "",
                         description=text)
    else:
        if not args.target:
            sys.exit("Indicá una URL o id de LinkedIn, o --file con la descripción.")
        job = _job_from_target(args.target, tracker)
        if not job.description:
            with linkedin.make_client() as http:
                linkedin.fetch_description(http, job)
    print(f"- {job.title} — {job.company}")
    tailor_one(job, cv, cfg, claude, tracker, force=True)


def cmd_list(args, cfg, tracker):
    rows = sorted(tracker.data.items(), key=lambda kv: kv[1].get("score") or -1, reverse=True)
    for job_id, entry in rows:
        if args.state and entry["state"] != args.state:
            continue
        job = entry.get("job", {})
        score = entry.get("score")
        print(f"{job_id:>12}  {entry['state']:<11} {score if score is not None else '-':>3}  "
              f"{job.get('title', '')} — {job.get('company', '')}")


def cmd_status(args, cfg, tracker):
    tracker.set_state(args.job_id, args.state)
    tracker.save()
    print(f"{args.job_id} -> {args.state}")


def _job_from_target(target: str, tracker: Tracker) -> JobPosting:
    job_id = linkedin.job_id_from_url(target) or target
    cached = tracker.data.get(job_id, {}).get("job")
    if cached:
        return JobPosting(**cached)
    return JobPosting(job_id=job_id, title="", company="", url=linkedin.VIEW_URL.format(job_id=job_id))


def _applied_today(tracker: Tracker) -> int:
    return sum(1 for e in tracker.data.values() if e.get("applied") == date.today().isoformat())


def cmd_show(args, cfg, tracker):
    job = _job_from_target(args.target, tracker)
    if not job.description:
        with linkedin.make_client() as http:
            linkedin.fetch_description(http, job)
        tracker.upsert(job.job_id, job=job.model_dump())
        tracker.save()
    print(f"id: {job.job_id}\npuesto: {job.title}\nempresa: {job.company}\n"
          f"ubicación: {job.location}\nurl: {job.url}\n"
          f"estado: {tracker.data[job.job_id]['state'] if job.job_id in tracker.data else 'sin registrar'}\n"
          f"postulaciones hoy: {_applied_today(tracker)}\n\n{job.description}")


def cmd_log(args, cfg, tracker):
    job = _job_from_target(args.target, tracker)
    job.title = args.title or job.title
    job.company = args.company or job.company
    tracker.upsert(job.job_id, job=job.model_dump(), state=args.state, cv=args.cv_file,
                   canva_design=args.canva, applied=date.today().isoformat() if args.state == "postulada" else None)
    tracker.save()
    print(f"{job.job_id} -> {args.state}. Postulaciones hoy: {_applied_today(tracker)}")


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="job_agent", description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--config", type=Path, default=ROOT / "config.yaml")
    parser.add_argument("--cv", type=Path, default=ROOT / "data" / "cv_master.yaml")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("run").set_defaults(func=cmd_run)
    sub.add_parser("search").set_defaults(func=cmd_search)
    p = sub.add_parser("tailor")
    p.add_argument("target", nargs="?")
    p.add_argument("--file")
    p.add_argument("--title")
    p.add_argument("--company")
    p.set_defaults(func=cmd_tailor)
    p = sub.add_parser("list")
    p.add_argument("--state", choices=STATES)
    p.set_defaults(func=cmd_list)
    p = sub.add_parser("applied")
    p.add_argument("job_id")
    p.set_defaults(func=cmd_status, state="postulada")
    p = sub.add_parser("status")
    p.add_argument("job_id")
    p.add_argument("state", choices=STATES)
    p.set_defaults(func=cmd_status)

    p = sub.add_parser("show")
    p.add_argument("target")
    p.set_defaults(func=cmd_show)
    p = sub.add_parser("log")
    p.add_argument("target")
    p.add_argument("--title")
    p.add_argument("--company")
    p.add_argument("--state", choices=STATES, default="postulada")
    p.add_argument("--cv-file")
    p.add_argument("--canva", help="link del diseño adaptado en Canva")
    p.set_defaults(func=cmd_log)

    args = parser.parse_args(argv)
    cfg = load_config(args.config)
    tracker = Tracker(OUTPUT / "tracker.json")
    args.func(args, cfg, tracker)
