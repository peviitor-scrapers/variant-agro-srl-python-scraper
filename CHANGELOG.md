# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

### Added
- Job mappings from ANOFM include salary, standardized tags, work mode and
  expiry date, while excluding descriptions and personal contact data (#1).
- ANOFM job mapping embedded in `scraper/index.py`, with unit coverage for
  the new fields and for excluding personal contact data (#1).

### Changed
- Company identity, CIF and repository links set to VARIANT AGRO S.R.L. (#1).

## [1.0.0] - 2026-08-03

### Added
- Python scraper for **VARIANT AGRO S.R.L.** (CIF `41873878`), reading jobs from ANOFM (`mediere.anofm.ro`).
- Publisher to peviitor v1 API: company upsert, job upload, stale-job delete.
- ANAF company validation with CUIScan fallback and cache.
- ANOFM job search mirroring the Node.js template.
- `validate_jobs.py` CLI for head/content URL validation.
- Unit, integration, e2e, and consistency tests.
- GitHub Actions workflows: `job-seeker-ro-spider`, `automation-testing`, deep-validate, recovery.
- GitHub Pages (`docs/`) with generated `jobs.md` and `company.json`.
- AI documentation under `ai/`.

### Fixed
- Location normalization: common spellings (`Bucuresti`, `Turda`, etc.) and case/diacritic variants are no longer dropped to `România`.
- Stale-job deletion is scoped to this scraper's ANOFM job URLs, so jobs published by other peviitor scrapers under the same CIF are never removed.
- E2E `EXPECTED_MIN_JOBS` and integration tests reflect ANOFM and CIF `41873878`.
