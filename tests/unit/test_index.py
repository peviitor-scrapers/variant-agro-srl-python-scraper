"""Unit tests for the ANOFM-only index pipeline."""

import json

from scraper import index


def test_map_to_job_model_adds_company_and_status():
    index.COMPANY_NAME = "VARIANT AGRO S.R.L."
    raw = {
        "url": "https://mediere.anofm.ro/app/module/mediere/job/1",
        "title": "Lucrător comercial",
        "location": ["Târgu Jiu"],
    }
    job = index.map_to_job_model(raw, "41873878")
    assert job["company"] == "VARIANT AGRO S.R.L."
    assert job["cif"] == "41873878"
    assert job["status"] == "scraped"
    assert job["location"] == ["Târgu Jiu"]
    assert job["date"]


def test_map_to_job_model_without_location():
    raw = {"url": "https://mediere.anofm.ro/app/module/mediere/job/2",
           "title": "Vânzător"}
    job = index.map_to_job_model(raw, "41873878", company_name="VARIANT AGRO S.R.L.")
    assert "location" not in job


def test_map_to_job_model_keeps_optional_fields():
    raw = {
        "url": "https://mediere.anofm.ro/app/module/mediere/job/3",
        "title": "SUDOR",
        "salary": "4000-5000 RON",
        "tags": ["sudor", "cu-norma-intreaga"],
        "workmode": "on-site",
        "expirationdate": "2027-01-31",
    }
    job = index.map_to_job_model(raw, "41873878", company_name="VARIANT AGRO S.R.L.")
    assert job["salary"] == "4000-5000 RON"
    assert job["tags"] == ["sudor", "cu-norma-intreaga"]
    assert job["workmode"] == "on-site"
    assert job["expirationdate"] == "2027-01-31"


def test_transform_jobs_for_solr_uppercases_company():
    jobs = [{"url": "https://x/job", "title": "Test", "location": ["Cluj-Napoca"]}]
    transformed = index.transform_jobs_for_solr({"company": "Variant Agro S.R.L.", "jobs": jobs})
    assert transformed["company"] == "VARIANT AGRO S.R.L."
    assert transformed["jobs"][0]["location"] == ["Cluj-Napoca"]


def test_transform_jobs_for_solr_location_fallback():
    jobs = [{"url": "https://x/job", "title": "Test", "location": []}]
    transformed = index.transform_jobs_for_solr({"company": "VARIANT AGRO S.R.L.", "jobs": jobs})
    assert transformed["jobs"][0]["location"] == ["România"]


def test_transform_jobs_for_solr_missing_location_fallback():
    jobs = [{"url": "https://x/job", "title": "Test"}]
    transformed = index.transform_jobs_for_solr({"company": "VARIANT AGRO S.R.L.", "jobs": jobs})
    assert transformed["jobs"][0]["location"] == ["România"]


def _stub_main(monkeypatch, tmp_path, raw_jobs):
    monkeypatch.setattr(index, "query_solr", lambda cif: {"numFound": 0, "docs": []})
    monkeypatch.setattr(index, "upsert_jobs", lambda jobs: None)
    monkeypatch.setattr(index, "delete_job_by_url", lambda url: None)
    monkeypatch.setattr(index, "upsert_company", lambda cfg: None)
    monkeypatch.setattr(index, "validate_and_get_company", lambda: {
        "company": "VARIANT AGRO S.R.L.", "cif": "41873878", "address": "TÂRGU JIU"})
    monkeypatch.setattr(index, "search_anofm_jobs", lambda cif: raw_jobs)
    monkeypatch.setattr(index, "drop_dead_urls", lambda jobs: jobs)
    return tmp_path


def test_main_writes_summary(tmp_path, monkeypatch):
    fake_jobs = [
        {"url": f"https://mediere.anofm.ro/app/module/mediere/job/{i}",
         "title": f"Job {i}", "location": ["Târgu Jiu"]}
        for i in range(3)
    ]
    root = _stub_main(monkeypatch, tmp_path, fake_jobs)

    index.main(root=root)

    out = tmp_path / "scraper" / "jobs.json"
    assert out.exists()
    data = json.loads(out.read_text(encoding="utf-8"))
    assert len(data["jobs"]) == 3
    assert data["company"] == "VARIANT AGRO S.R.L."
    assert (tmp_path / "docs" / "jobs.md").exists()


def test_main_preserves_enriched_fields(tmp_path, monkeypatch):
    fake_jobs = [{
        "url": "https://mediere.anofm.ro/app/module/mediere/job/3447055",
        "title": "SUDOR",
        "location": ["TARGU JIU"],
        "salary": "4000-5000 RON",
        "tags": ["sudor", "cu-norma-intreaga"],
        "workmode": "on-site",
        "expirationdate": "2027-01-31",
    }]
    root = _stub_main(monkeypatch, tmp_path, fake_jobs)

    index.main(root=root)

    data = json.loads((tmp_path / "scraper" / "jobs.json").read_text(encoding="utf-8"))
    job = data["jobs"][0]
    assert job["salary"] == "4000-5000 RON"
    assert job["tags"] == ["sudor", "cu-norma-intreaga"]
    assert job["workmode"] == "on-site"
    assert job["expirationdate"] == "2027-01-31"


def test_main_dedupes_anofm_urls(tmp_path, monkeypatch):
    job = {"url": "https://mediere.anofm.ro/app/module/mediere/job/1", "title": "Job"}
    root = _stub_main(monkeypatch, tmp_path, [job, dict(job)])

    index.main(root=root)

    data = json.loads((tmp_path / "scraper" / "jobs.json").read_text(encoding="utf-8"))
    assert len(data["jobs"]) == 1


def test_main_canary_aborts_before_any_write(tmp_path, monkeypatch):
    upserted = []
    root = _stub_main(monkeypatch, tmp_path, [])
    monkeypatch.setattr(index, "upsert_jobs", lambda jobs: upserted.append(jobs))
    monkeypatch.setattr(index, "upsert_company", lambda cfg: (_ for _ in ()).throw(AssertionError("no write")))

    index.main(root=root)

    assert upserted == []
    assert not (tmp_path / "scraper" / "jobs.json").exists()


def test_drop_dead_urls_drops_soft_404(monkeypatch):
    good = {"url": "https://x/good", "title": "Good"}
    old = {"url": "https://x/old", "title": "Old"}
    monkeypatch.setattr(index, "validate_by_content", lambda url: {
        "url": url, "status": "active" if url.endswith("good") else "expired",
        "http_status": 200, "error": None})

    assert index.drop_dead_urls([good, old]) == [good]


def _anofm_row(job_id=1, **overrides):
    row = {
        "id": job_id,
        "employer_tax_code": "41873878",
        "occupation": "SUDOR",
        "address_locality_name": "Gorj > MUNICIPIUL TARGU JIU > TARGU JIU",
        "minimum_salary": "4000.00",
        "maximum_salary": "5000.00",
        "work_regime_name": "Sediu",
        "job_expiry_date": "2099-01-31",
        "job_domain_name": "Producție și logistică",
        "job_posting_target_name": "PCLM",
        "work_type_name": "Cu normă întreagă",
        "contact_name": "PERSOANA DE CONTACT",
        "contact_email": "contact@example.com",
        "contact_phone": "0700000000",
        "description": "Descriere care nu trebuie stocată",
    }
    row.update(overrides)
    return row


def test_search_anofm_jobs_maps_non_personal_fields(mock_post):
    mock_post.return_value.status_code = 200
    mock_post.return_value.json.return_value = {"rows": [_anofm_row()]}

    jobs = index.search_anofm_jobs("41873878")

    assert len(jobs) == 1
    job = jobs[0]
    assert job["url"] == "https://mediere.anofm.ro/app/module/mediere/job/1"
    assert job["title"] == "SUDOR"
    assert job["location"] == ["TARGU JIU"]
    assert job["salary"] == "4000-5000 RON"
    assert job["workmode"] == "on-site"
    assert job["expirationdate"] == "2099-01-31"
    assert "productie-si-logistica" in job["tags"]
    assert "cu-norma-intreaga" in job["tags"]
    assert not {"contact_name", "contact_email", "contact_phone", "description"} & job.keys()


def test_search_anofm_jobs_sends_cif_filter(mock_post):
    mock_post.return_value.status_code = 200
    mock_post.return_value.json.return_value = {"rows": []}

    index.search_anofm_jobs("41873878")

    payload = mock_post.call_args.kwargs["json"]
    assert payload["employer_tax_code"] == "41873878"
    assert payload["current"] == 1
    assert payload["rowCount"] == 250
    assert payload["sort"] == {"created_at": "desc"}


def test_search_anofm_jobs_dedupes_and_filters_wrong_cif(mock_post):
    mock_post.return_value.status_code = 200
    mock_post.return_value.json.return_value = {"rows": [
        _anofm_row(1), _anofm_row(1), _anofm_row(2, employer_tax_code="99999999"),
    ]}

    jobs = index.search_anofm_jobs("41873878")

    assert [job["url"].rsplit("/", 1)[-1] for job in jobs] == ["1"]


def test_search_anofm_jobs_skips_expired_and_placeholders(mock_post):
    mock_post.return_value.status_code = 200
    mock_post.return_value.json.return_value = {"rows": [
        _anofm_row(1, job_expiry_date="2020-01-01"),
        _anofm_row(2, occupation="N/A"),
        _anofm_row(3),
    ]}

    jobs = index.search_anofm_jobs("41873878")

    assert len(jobs) == 1
    assert jobs[0]["url"].endswith("/3")


def test_search_anofm_jobs_empty_on_http_error(mock_post):
    mock_post.return_value.status_code = 503
    assert index.search_anofm_jobs("41873878") == []


def test_search_anofm_jobs_empty_on_network_error(mock_post):
    mock_post.side_effect = RuntimeError("network")
    assert index.search_anofm_jobs("41873878") == []


def test_salary_variants():
    assert index._salary({"minimum_salary": "4325.00"}) == "4325 RON"
    assert index._salary({"maximum_salary": "6000.00"}) is None
    assert index._salary({"minimum_salary": "abc"}) is None


def test_workmode_variants():
    assert index._workmode({"work_regime_name": "Telemuncă"}) == "remote"
    assert index._workmode({"work_regime_name": "Muncă la distanță"}) == "remote"
    assert index._workmode({"work_regime_name": "Hibrid"}) == "hybrid"
    assert index._workmode({"work_regime_name": "Sediu"}) == "on-site"
    assert index._workmode({}) is None


def test_tags_are_lowercase_without_diacritics_and_capped():
    row = {field: "Școală profesională" for field in index.TAG_SOURCE_FIELDS}
    assert index._tags(row) == ["scoala-profesionala"]
    many = {field: f"tag {i}" for i, field in enumerate(index.TAG_SOURCE_FIELDS)}
    assert len(index._tags(many)) <= 20
