# VERIFY

How to verify the scraper works.

## Local setup

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
source .venv/bin/activate   # apoi comenzile de mai jos folosesc python3 din venv
```

## Offline

```bash
python3 -m pytest tests/unit tests/consistency   # all fast suites
# SAU, când vrei o singură suită:
python3 -m pytest tests/integration              # live APIs (skip-safe)
python3 -m pytest tests/e2e                      # live ANOFM (skip-safe)
python3 -m pytest                                # everything
```

Expect: all green, no network needed for the unit/consistency suites. The full
live publish (`python3 -m scraper.index`) is manual and is not part of the test
suite.

## Live — company

```bash
python3 -c "from scraper.anaf import get_company_from_anaf; print(get_company_from_anaf('41873878'))"
```

Expect: `denumire == "VARIANT AGRO S.R.L."`, `cif == "41873878"`.

## Live — ANOFM

```bash
python3 -m pytest tests/e2e
```

Expect: `>= 1` jobs scraped from ANOFM, unique URLs, titles present.

## Live — peviitor SOLR

```bash
curl "https://api.peviitor.ro/v1/scraper/jobs/?cif=41873878&rows=500"
```

Expect: `success: true`. Note CIF `41873878` is shared with other peviitor
scrapers (jobviewtrack, ejobs, olx, multijobs, targuldecariere), so the
total count includes their jobs; confirm the scraped ANOFM job URLs are present.

## Full pipeline

```bash
python3 -m scraper.index
```

Then check:

- `scraper/jobs.json` exists and has jobs.
- `docs/jobs.md` regenerated with the job list.
- `docs/company.json` mirrors `scraper/config/company.json`.
- SOLR count matches scraped count (minus filtered locations).

## GitHub Pages

```bash
gh api repos/peviitor-scrapers/variant-agro-srl-python-scraper/pages --jq .html_url
curl -s -o /dev/null -w "%{http_code}\n" https://peviitor-scrapers.github.io/variant-agro-srl-python-scraper/
```

Expect: `https://peviitor-scrapers.github.io/variant-agro-srl-python-scraper/` and HTTP `200`.
The site is built from `docs/` on `main` (source: branch `main`, path `/docs`).

## GitHub Actions

For each workflow in `.github/workflows/`, run it from **Actions** → *Run workflow* (on `main`) and check all jobs are green:

| Workflow | Trigger | Ce verifici |
|----------|---------|-------------|
| `job-seeker-ro-spider.yml` | `workflow_dispatch` | Scraperul rulează → job-uri în API + `docs/jobs.md` generat |
| `automation-testing.yml` | `workflow_dispatch` | Toate testele + validare job-uri |

After a successful run, verify via API that the company jobs appear:

```bash
curl -s "https://api.peviitor.ro/v1/scraper/jobs/?cif=41873878&rows=500"
```

Check `docs/jobs.md` was regenerated and jobs are visible on https://peviitor.ro (CIF `41873878`).
