"""Búsqueda de ofertas en LinkedIn usando la vista pública (sin iniciar sesión).

Importante: no usa tu cuenta ni tu cookie de sesión, a propósito. Automatizar una
cuenta logueada (scraping o postulaciones automáticas) va contra los términos de
LinkedIn y puede terminar en restricción de la cuenta. Acá solo se leen las
páginas públicas de empleos, despacio y con pocas solicitudes.
"""

from __future__ import annotations

import html
import re
import time
from urllib.parse import urlencode

import httpx

from .models import JobPosting

SEARCH_URL = "https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search"
DETAIL_URL = "https://www.linkedin.com/jobs-guest/jobs/api/jobPosting/{job_id}"
VIEW_URL = "https://www.linkedin.com/jobs/view/{job_id}/"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/126.0 Safari/537.36"
    ),
    "Accept-Language": "es-AR,es;q=0.9,en;q=0.8",
}
DELAY_SECONDS = 2.5  # pausa entre solicitudes para no saturar

_CARD_RE = re.compile(r"<li>(.*?)</li>", re.S)
_URN_RE = re.compile(r"urn:li:jobPosting:(\d+)")
_TAG_RE = re.compile(r"<[^>]+>")


def _text(fragment: str) -> str:
    fragment = re.sub(r"<br\s*/?>|</p>|</li>", "\n", fragment, flags=re.I)
    fragment = re.sub(r"<li[^>]*>", "• ", fragment, flags=re.I)
    text = html.unescape(_TAG_RE.sub("", fragment))
    lines = [re.sub(r"[ \t]+", " ", line).strip() for line in text.splitlines()]
    return "\n".join(line for line in lines if line)


def _class_text(block: str, css_class: str) -> str:
    m = re.search(rf'class="[^"]*\b{re.escape(css_class)}\b[^"]*"[^>]*>(.*?)</', block, re.S)
    return _text(m.group(1)) if m else ""


def job_id_from_url(url: str) -> str | None:
    m = re.search(r"currentJobId=(\d+)", url) or re.search(r"/jobs/view/(?:[^/]*-)?(\d+)", url)
    return m.group(1) if m else None


def search(
    client: httpx.Client,
    keywords: str,
    location: str,
    *,
    posted_within_days: int | None = None,
    remote: bool = False,
    experience_levels: list[int] | None = None,
    max_results: int = 25,
) -> list[JobPosting]:
    params: dict[str, str] = {"keywords": keywords, "location": location}
    if posted_within_days:
        params["f_TPR"] = f"r{posted_within_days * 86400}"
    if remote:
        params["f_WT"] = "2,3"  # 2=remoto, 3=híbrido
    if experience_levels:
        params["f_E"] = ",".join(str(level) for level in experience_levels)

    jobs: list[JobPosting] = []
    start = 0
    while len(jobs) < max_results:
        resp = client.get(f"{SEARCH_URL}?{urlencode({**params, 'start': start})}")
        if resp.status_code == 429:
            print("  LinkedIn pidió bajar el ritmo (429). Corto esta búsqueda.")
            break
        resp.raise_for_status()
        cards = _CARD_RE.findall(resp.text)
        if not cards:
            break
        for card in cards:
            urn = _URN_RE.search(card)
            if not urn:
                continue
            posted = re.search(r'datetime="([^"]+)"', card)
            jobs.append(
                JobPosting(
                    job_id=urn.group(1),
                    title=_class_text(card, "base-search-card__title"),
                    company=_class_text(card, "base-search-card__subtitle"),
                    location=_class_text(card, "job-search-card__location"),
                    url=VIEW_URL.format(job_id=urn.group(1)),
                    posted=posted.group(1) if posted else "",
                )
            )
        start += len(cards)
        time.sleep(DELAY_SECONDS)
    return jobs[:max_results]


def fetch_description(client: httpx.Client, job: JobPosting) -> JobPosting:
    resp = client.get(DETAIL_URL.format(job_id=job.job_id))
    resp.raise_for_status()
    page = resp.text
    m = re.search(r'class="[^"]*show-more-less-html__markup[^"]*"[^>]*>(.*?)</div>', page, re.S)
    job.description = _text(m.group(1)) if m else ""
    if not job.title:
        job.title = _class_text(page, "top-card-layout__title")
    if not job.company:
        job.company = _class_text(page, "topcard__org-name-link")
    if not job.location:
        job.location = _class_text(page, "topcard__flavor--bullet")
    time.sleep(DELAY_SECONDS)
    return job


def make_client() -> httpx.Client:
    return httpx.Client(headers=HEADERS, timeout=30, follow_redirects=True)
