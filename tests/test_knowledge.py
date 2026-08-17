from pathlib import Path

import yaml

ROOT = Path(__file__).parents[1]


def test_cohort_dictionary_has_unique_stable_fields():
    payload = yaml.safe_load((ROOT / "knowledge/schema/cohort_fields.yaml").read_text(encoding="utf-8"))
    fields = payload["fields"]
    keys = [field["key"] for field in fields]
    labels = [field["label"] for field in fields]
    assert len(fields) >= 150
    assert len(keys) == len(set(keys))
    assert len(labels) == len(set(labels))
    assert fields[0]["label"] == "病案号（7位）"
    assert fields[-1]["label"] == "其他收集信息"


def test_direct_identifiers_are_manual_restricted():
    payload = yaml.safe_load((ROOT / "knowledge/schema/cohort_fields.yaml").read_text(encoding="utf-8"))
    by_key = {field["key"]: field for field in payload["fields"]}
    for key in ("record_number", "contact"):
        assert by_key[key]["capture"] == "manual_restricted"
        assert by_key[key]["sensitivity"] == "direct_identifier"


def test_tnm_policy_requires_review_for_inference():
    policy = yaml.safe_load((ROOT / "knowledge/rules/staging_policy.yaml").read_text(encoding="utf-8"))
    assert policy["inference"]["output_status"] == "REVIEW_REQUIRED"
    assert policy["review"]["always_required_for_inferred_tnm"] is True
    assert policy["review"]["verified_only_by_human"] is True


def test_reference_registry_has_unique_ids_and_https_urls():
    registry = yaml.safe_load((ROOT / "knowledge/references/sources.yaml").read_text(encoding="utf-8"))
    sources = registry["sources"]
    ids = [source["id"] for source in sources]
    assert len(sources) >= 20
    assert len(ids) == len(set(ids))
    assert all(source["url"].startswith("https://") for source in sources)


def test_root_readme_lists_every_registered_primary_source():
    registry = yaml.safe_load((ROOT / "knowledge/references/sources.yaml").read_text(encoding="utf-8"))
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    missing = [source["id"] for source in registry["sources"] if source["url"] not in readme]
    assert not missing, f"README 缺少知识库来源: {missing}"
