[![Oportunitati si Cariere](https://github.com/peviitor-scrapers/variant-agro-srl-python-scraper/actions/workflows/job-seeker-ro-spider.yml/badge.svg)](https://github.com/peviitor-scrapers/variant-agro-srl-python-scraper/actions/workflows/job-seeker-ro-spider.yml)
[![Automation Tests](https://github.com/peviitor-scrapers/variant-agro-srl-python-scraper/actions/workflows/automation-testing.yml/badge.svg)](https://github.com/peviitor-scrapers/variant-agro-srl-python-scraper/actions/workflows/automation-testing.yml)
[![Version](https://img.shields.io/badge/version-1.0.0-blue)](CHANGELOG.md)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.12-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![Website](https://img.shields.io/website?url=https%3A%2F%2Fpeviitor.ro&label=peviitor.ro)](https://peviitor.ro)
[![API](https://img.shields.io/website?url=https%3A%2F%2Fapi.peviitor.ro%2F&label=api.peviitor.ro)](https://api.peviitor.ro/)
[![GitHub Pages](https://img.shields.io/github/deployments/peviitor-scrapers/variant-agro-srl-python-scraper/github-pages?label=GitHub%20Pages)](https://peviitor-scrapers.github.io/variant-agro-srl-python-scraper/)

# job_seeker_ro_spider — VARIANT AGRO S.R.L. Scraper

**job_seeker_ro_spider** — a scraper for VARIANT AGRO S.R.L. jobs in Romania. It collects the announcements published by VARIANT AGRO S.R.L. on [ANOFM](https://mediere.anofm.ro/app/module/mediere/jobs) and [jobRapid](https://www.jobrapid.ro/) and publishes them to [peviitor.ro](https://peviitor.ro) through the Peviitor API.

ANOFM is the authoritative source. jobRapid postings are kept as separate jobs because peviitor.ro identifies jobs by their unique URL — a jobRapid mirror of an ANOFM offer has its own URL and is therefore a distinct listing. Other portals found during discovery (Ziarul Muncii, Careerjet, Jooble) only mirror the ANOFM ads without exposing their own job-detail URLs, so they add no additional listings.

> **🌱 Derived scraper.** This repository is derived from [electrogrup-sa-python-scraper](https://github.com/peviitor-scrapers/electrogrup-sa-python-scraper), the reference implementation for Python scrapers in the peviitor.ro ecosystem.

## Overview

The project automates the daily collection of VARIANT AGRO jobs in Romania, keeping the peviitor.ro board up to date with the latest career opportunities.

## Features

- Extracts jobs from ANOFM (`mediere.anofm.ro`) by company CIF
- Extracts job postings published by the company on jobRapid (`www.jobrapid.ro`), with title, location, salary and posting date from their JSON-LD `JobPosting` blocks
- Deduplicates by URL across both sources; distinct URLs remain distinct jobs
- Publishes non-personal fields stated by the source: location, salary, tags, work mode and expiry date
- Never stores job descriptions, contact names, emails or phone numbers (GDPR data minimization)
- Validates the company via CUIScan (legal name and address, by CIF) and CUIFirma (brand search)
- **Company cache** — does not hit the APIs on every scrape
- **Stale cache / config fallback** when CUIScan is unavailable
- Cross-validates against the Peviitor API
- Deletes stale jobs from peviitor when they are no longer published on ANOFM or jobRapid (scoped to this scraper's URLs)
- Stores to the Peviitor API (job core + company core)
- Generates `docs/jobs.md` automatically — accessible on GitHub Pages
- **Company identity in a single file** (`scraper/config/company.json`)
- GitHub Actions: daily scrape + automated testing (unit, integration, e2e, consistency)
- Identifies itself through the User-Agent: `job_seeker_ro_spider`

## Local setup

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python -m pytest tests/unit tests/consistency   # offline checks
.venv/bin/python -m scraper.index                         # full scrape + publish
```

## License

Copyright (c) 2026 Alexandra Ifrim

Licensed under the [MIT License](LICENSE).

## Managed By

This project is managed by [ASOCIATIA OPORTUNITATI SI CARIERE](https://oportunitatisicariere.ro) and used as a web scraper for the [peviitor.ro](https://peviitor.ro) job board project.

## Disclaimer

This scraper is designed for educational purposes and legitimate job data aggregation for the Romanian job market.
