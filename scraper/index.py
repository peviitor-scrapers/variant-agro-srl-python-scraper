"""
VARIANT AGRO S.R.L. ANOFM Scraper

Collects job postings published by VARIANT AGRO S.R.L. (CUI 41873878) on ANOFM
(mediere.anofm.ro) and publishes them to peviitor.ro via the v1 API.
"""

import datetime
import json
import pathlib
import re
import sys
import unicodedata

import requests

from .api import delete_job_by_url, map_with_concurrency, query_solr, upsert_company, upsert_jobs
from .company import validate_and_get_company
from .config import company_config, scraper_config
from .job_validator import validate_by_content
from .markdown_generator import generate_jobs_markdown

COMPANY_CIF = company_config["id"]
JOB_DETAILS_PREFIX = scraper_config["jobDetailsPrefix"]
COMPANY_NAME = None

LIVE_CHECK_CONCURRENCY = 5
DELETE_CONCURRENCY = 3
OPTIONAL_JOB_FIELDS = ("salary", "tags", "workmode", "expirationdate")

ANOFM_API_URL = "https://mediere.anofm.ro/api/entity/vw_public_job_posting"
JOB_URL_TEMPLATE = "https://mediere.anofm.ro/app/module/mediere/job/{id}"
ANOFM_HEADERS = {"User-Agent": "job_seeker_ro_spider", "Content-Type": "application/json"}
ANOFM_TIMEOUT = 10
ROW_COUNT = 250

TAG_SOURCE_FIELDS = (
    "job_domain_name",
    "job_posting_target_name",
    "work_type_name",
    "contract_type_name",
    "work_regime_name",
    "education_level_name",
    "professional_experience_name",
)
PLACEHOLDER_TITLES = {"n/a", "-", "nespecificat", "niciunul", "none"}


def _clean(value):
    return re.sub(r"\s+", " ", value or "").strip()


def _slug(value):
    value = (value or "").replace("ş", "s").replace("ţ", "t").replace("Ş", "S").replace("Ţ", "T")
    value = "".join(c for c in unicodedata.normalize("NFD", value) if unicodedata.category(c) != "Mn")
    value = value.lower().replace("&", " si ")
    return re.sub(r"-+", "-", re.sub(r"[^a-z0-9]+", "-", value)).strip("-")


def _city(row):
    parts = [part.strip() for part in (row.get("address_locality_name") or "").split(">")]
    return parts[-1] if parts and parts[-1] else None


def _workmode(row):
    regime = (row.get("work_regime_name") or "").lower()
    if "telemunc" in regime or "distan" in regime:
        return "remote"
    if "hibrid" in regime:
        return "hybrid"
    if "sediu" in regime:
        return "on-site"
    return None


def _tags(row):
    tags = []
    for field in TAG_SOURCE_FIELDS:
        tag = _slug(row.get(field))
        if tag and len(tag) <= 60 and tag not in tags:
            tags.append(tag)
    return tags[:20]


def _salary(row):
    try:
        minimum = f"{float(row['minimum_salary']):.0f}" if row.get("minimum_salary") else None
        maximum = f"{float(row['maximum_salary']):.0f}" if row.get("maximum_salary") else None
    except (TypeError, ValueError):
        return None
    if minimum and maximum:
        return f"{minimum}-{maximum} RON"
    if minimum:
        return f"{minimum} RON"
    return None


def search_anofm_jobs(cif, row_count=ROW_COUNT):
    """Returns peviitor-ready job dicts for one employer tax code."""
    payload = {
        "current": 1,
        "rowCount": row_count,
        "sort": {"created_at": "desc"},
        "employer_tax_code": str(cif),
    }
    try:
        res = requests.post(
            ANOFM_API_URL, json=payload, headers=ANOFM_HEADERS, timeout=ANOFM_TIMEOUT)
        if res.status_code != 200:
            print(f"  ANOFM returned {res.status_code}")
            return []
        rows = res.json().get("rows") or []
    except Exception as err:
        print(f"  ANOFM error: {err}")
        return []

    today = datetime.date.today().isoformat()
    jobs = []
    known_urls = set()
    for row in rows:
        if str(row.get("employer_tax_code") or "") != str(cif) or not row.get("id"):
            continue
        title = _clean(row.get("occupation"))
        if len(title) < 3 or title.lower() in PLACEHOLDER_TITLES:
            continue
        expiry = _clean(row.get("job_expiry_date")) or None
        if expiry and expiry < today:
            continue

        url = JOB_URL_TEMPLATE.format(id=row["id"])
        if url in known_urls:
            continue
        known_urls.add(url)

        job = {"url": url, "title": title[:200]}
        city = _city(row)
        if city:
            job["location"] = [city]
        salary = _salary(row)
        if salary:
            job["salary"] = salary
        tags = _tags(row)
        if tags:
            job["tags"] = tags
        workmode = _workmode(row)
        if workmode:
            job["workmode"] = workmode
        if expiry:
            job["expirationdate"] = expiry
        jobs.append(job)

    print(f"  Found {len(jobs)} jobs on ANOFM")
    return jobs


def map_to_job_model(raw_job, cif, company_name=None):
    now = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    job = {
        "url": raw_job["url"],
        "title": raw_job["title"],
        "company": company_name or COMPANY_NAME,
        "cif": cif,
        "date": raw_job.get("date") or now,
        "status": "scraped",
    }
    if raw_job.get("location"):
        job["location"] = raw_job["location"]
    for field in OPTIONAL_JOB_FIELDS:
        if raw_job.get(field):
            job[field] = raw_job[field]
    return job


def transform_jobs_for_solr(payload):
    company = (payload.get("company") or "").upper()
    jobs = []
    for job in payload.get("jobs", []):
        locations = [loc for loc in (job.get("location") or []) if loc]
        jobs.append({**job, "location": locations or ["România"]})
    return {**payload, "company": company, "jobs": jobs}


def drop_dead_urls(jobs):
    """GET-check every job with bounded concurrency and drop soft-404s.

    A 200 response can still be a "no longer available" page; validate_by_content
    scans the visible body for the shared expiry keywords.
    """
    checks = map_with_concurrency(
        jobs, lambda job, _: validate_by_content(job["url"]), limit=LIVE_CHECK_CONCURRENCY)
    alive = []
    for job, result in zip(jobs, checks):
        if result["status"] == "active":
            alive.append(job)
        else:
            reason = result.get("error") or f"HTTP {result.get('http_status', 0)}"
            print(f"  dropped \"{job['title']}\" ({job['url']}): live URL check failed — {reason}")
    if len(alive) < len(jobs):
        print(f"  {len(jobs) - len(alive)}/{len(jobs)} job(s) failed live URL validation and were dropped")
    return alive


def _validated_company():
    try:
        return validate_and_get_company()
    except Exception as err:
        print(f"CUIScan validation failed ({err}) — using config identity")
        return {
            "cif": company_config["id"],
            "company": company_config["company"],
            "address": (company_config.get("location") or ["România"])[0],
        }


def main(root=None):
    root = root or pathlib.Path(__file__).resolve().parents[1]

    print("=== Step 1: Get existing jobs from SOLR ===")
    existing_result = query_solr(COMPANY_CIF)
    existing_count = existing_result["numFound"]
    existing_urls = {doc.get("url") for doc in existing_result["docs"]
                     if doc.get("url") and doc["url"].startswith(JOB_DETAILS_PREFIX)}
    print(f"Found {existing_count} existing jobs in SOLR ({len(existing_urls)} from ANOFM)")

    print("=== Step 2: Validate company via CUIScan/CUIFirma ===")
    validated = _validated_company()
    global COMPANY_NAME
    COMPANY_NAME = validated["company"]

    print("=== Step 3: Scrape VARIANT AGRO S.R.L. jobs from ANOFM ===")
    raw_jobs = []
    known_urls = set()
    for job in search_anofm_jobs(validated["cif"]):
        if job["url"] not in known_urls:
            raw_jobs.append(job)
            known_urls.add(job["url"])
    print(f"Jobs scraped from ANOFM: {len(raw_jobs)}")

    jobs = [map_to_job_model(job, validated["cif"]) for job in raw_jobs]
    payload = {
        "source": "mediere.anofm.ro",
        "scrapedAt": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "company": COMPANY_NAME,
        "cif": validated["cif"],
        "jobs": jobs,
    }

    transformed = transform_jobs_for_solr(payload)
    transformed["jobs"] = drop_dead_urls(transformed["jobs"])
    print(f"Jobs with valid locations: {len(transformed['jobs'])}")
    if not transformed["jobs"]:
        print("Canary: no live jobs after URL validation — aborting before any write")
        return

    try:
        upsert_company({
            "id": validated["cif"],
            "company": validated["company"],
            "brand": company_config.get("brand"),
            "status": company_config.get("status") or "activ",
            "location": [validated["address"]] if validated.get("address") else company_config["location"],
            "website": company_config.get("website"),
            "career": company_config.get("career"),
            "scraperFile": company_config.get("scraperFile"),
            "lastScraped": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d"),
        })
    except Exception as err:
        print(f"Note: Could not upsert company: {err}")

    jobs_path = root / "scraper" / "jobs.json"
    jobs_path.parent.mkdir(parents=True, exist_ok=True)
    jobs_path.write_text(json.dumps(transformed, ensure_ascii=False, indent=2), encoding="utf-8")
    print("Saved scraper/jobs.json")

    company_data = {
        "id": validated["cif"],
        "company": transformed["company"],
        "brand": company_config.get("brand"),
        "status": company_config.get("status") or "activ",
        "location": [validated["address"]] if validated.get("address") else company_config["location"],
        "website": company_config.get("website"),
        "career": company_config.get("career"),
        "lastScraped": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d"),
    }
    markdown = generate_jobs_markdown(company_data, transformed["jobs"])
    (root / "docs").mkdir(exist_ok=True)
    (root / "docs" / "jobs.md").write_text(markdown, encoding="utf-8")
    print("Saved docs/jobs.md")

    src_company = pathlib.Path(__file__).resolve().parent / "config" / "company.json"
    (root / "docs" / "company.json").write_text(src_company.read_text(encoding="utf-8"), encoding="utf-8")

    print("\n=== Step 4: Upsert jobs to SOLR ===")
    upsert_jobs(transformed["jobs"])

    scraped_urls = {job["url"] for job in transformed["jobs"]}
    stale_urls = [url for url in existing_urls if url not in scraped_urls]
    if stale_urls:
        print(f"\n=== Step 4.5: Delete {len(stale_urls)} stale job(s) ===")

        def _delete_stale(url):
            try:
                delete_job_by_url(url)
            except Exception as err:
                print(f"  Failed to delete: {url} — {err}")

        map_with_concurrency(stale_urls, lambda url, _: _delete_stale(url), limit=DELETE_CONCURRENCY)
    else:
        print("\nNo stale jobs to delete")

    print("\n=== Step 5: Summary ===")
    final_result = query_solr(COMPANY_CIF)
    print(f"Jobs existing in SOLR before scrape: {existing_count}")
    print(f"Jobs scraped from ANOFM: {len(transformed['jobs'])}")
    print(f"Stale jobs attempted: {len(stale_urls)}")
    print(f"Jobs in SOLR after scrape: {final_result['numFound']}")


if __name__ == "__main__":
    try:
        main()
    except Exception as err:
        print("Scraper failed:", err)
        sys.exit(1)
