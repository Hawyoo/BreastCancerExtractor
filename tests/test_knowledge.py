from pathlib import Path

import yaml

from app.knowledge import extraction_prompt, questionnaire_field_index, source_priority
from app.main import immunotherapy_evidence_is_valid, normalize_observation_value, observation_value_is_valid

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


def test_document_roi_mapping_only_targets_known_cohort_fields():
    cohort = yaml.safe_load((ROOT / "knowledge/schema/cohort_fields.yaml").read_text(encoding="utf-8"))
    mapping = yaml.safe_load((ROOT / "knowledge/schema/document_roi_mapping.yaml").read_text(encoding="utf-8"))
    known_fields = {field["key"] for field in cohort["fields"]}
    assert set(mapping["documents"]) == {
        "MEDICAL_RECORD_COVER", "ADMISSION", "SURGERY", "DISCHARGE", "ULTRASOUND", "MAMMOGRAPHY",
        "MRI", "BIOPSY_PATHOLOGY", "SURGICAL_PATHOLOGY", "IHC", "TREATMENT", "OTHER",
    }
    for document in mapping["documents"].values():
        region_keys = [region["key"] for region in document["regions"]]
        assert len(region_keys) == len(set(region_keys))
        for region in document["regions"]:
            assert set(region.get("target_fields", [])) <= known_fields


def test_imaging_roi_policy_separates_neoadjuvant_timepoints():
    mapping = yaml.safe_load((ROOT / "knowledge/schema/document_roi_mapping.yaml").read_text(encoding="utf-8"))
    rules = "\n".join(mapping["imaging_rules"])
    assert "恶性病灶" in rules
    assert "PRE_TREATMENT" in rules
    assert "POST_NEOADJUVANT" in rules
    assert "不得覆盖" in rules


def test_tnm_policy_requires_review_for_inference():
    policy = yaml.safe_load((ROOT / "knowledge/rules/staging_policy.yaml").read_text(encoding="utf-8"))
    assert policy["inference"]["output_status"] == "REVIEW_REQUIRED"
    assert policy["review"]["always_required_for_inferred_tnm"] is True
    assert policy["review"]["verified_only_by_human"] is True


def test_sex_is_excluded_from_cover_and_allowed_from_admission():
    rules = yaml.safe_load((ROOT / "knowledge/rules/document_rules.yaml").read_text(encoding="utf-8"))
    sex_rule = rules["document_rules"]["MEDICAL_RECORD_COVER"][0]
    assert sex_rule["action"] == "EXCLUDE"

    cover_prompt, cover_allowed = extraction_prompt("MEDICAL_RECORD_COVER", "性别 2 1.男 2.女")
    admission_prompt, admission_allowed = extraction_prompt("ADMISSION", "患者女性，末次月经2026-08-01")
    assert "sex" not in cover_allowed
    assert "sex" in admission_allowed
    assert "medical_record_cover_sex_exclusion" in cover_prompt
    assert "last_menstrual_period_near_admission" in admission_prompt


def test_data_processing_preferences_capture_user_rules():
    preferences = yaml.safe_load(
        (ROOT / "knowledge/rules/data_processing_preferences.yaml").read_text(encoding="utf-8")
    )
    assert preferences["source_priority"]["sex"]["exclude_documents"] == ["MEDICAL_RECORD_COVER"]
    assert preferences["derivations"]["metastatic_at_presentation_default"]["output"] == "NO"
    measurement = preferences["measurements"]["breast_lesion_size"]
    assert measurement["input_slots"] == 3
    assert measurement["optional_slots"] == ["height"]
    assert preferences["conditional_questions"]["representation"]["export_value"] == "NA"

    cohort = yaml.safe_load((ROOT / "knowledge/schema/cohort_fields.yaml").read_text(encoding="utf-8"))
    by_key = {field["key"]: field for field in cohort["fields"]}
    assert by_key["pre_us_tumor_size_mm"]["dimensions"] == ["length", "width", "height"]
    assert by_key["pre_us_tumor_size_mm"]["optional_dimensions"] == ["height"]
    assert by_key["neoadjuvant_cycles"]["depends_on"]["field"] == "neoadjuvant_received"


def test_wps_form_choice_logic_and_conditionals_are_machine_readable():
    form = yaml.safe_load(
        (ROOT / "knowledge/schema/wps_form_2026_04_09.yaml").read_text(encoding="utf-8")
    )
    assert form["source_url"] == "https://f.kdocs.cn/g/kD2Xj3eU/"
    assert form["verification"]["expanded_question_count"] == 127
    assert form["choice_fields"]["pre_mmg_single_lesion"]["options"]["多发"] == "MULTIPLE"
    assert form["choice_fields"]["pre_mmg_birads"]["options"]["4级"] == "4"
    assert form["choice_fields"]["pre_mmg_birads"]["options"]["4A级"] == "4A"
    assert form["choice_fields"]["pre_mmg_birads"]["options"]["4B级"] == "4B"
    assert form["choice_fields"]["pre_mmg_birads"]["options"]["4C级"] == "4C"
    assert "4B" in form["choice_fields"]["pre_mmg_birads"]["accepted_report_subcategories"]
    assert form["choice_fields"]["chronic_disease"]["type"] == "multiple_choice"
    dependencies = {
        item["when"]["field"]: item
        for item in form["conditional_sections"]
        if item["when"]["field"] == "menopausal_status"
    }
    assert dependencies["menopausal_status"]["reveal"] == ["menopause_age"]
    field_index = questionnaire_field_index()
    assert field_index["breast_laterality"]["field_options"] == [
        {"label": "左侧", "value": "LEFT"},
        {"label": "右侧", "value": "RIGHT"},
        {"label": "双侧", "value": "BILATERAL"},
    ]
    assert field_index["neoadjuvant_received"]["field_options"][1] == {
        "label": "否", "value": "NO"
    }
    assert {item["value"] for item in field_index["pre_mmg_birads"]["field_options"]} >= {
        "4", "4A", "4B", "4C"
    }
    assert {item["label"]: item["value"] for item in field_index["postop_node_her2"]["field_options"]}["-"] == "0"


def test_postop_other_ihc_excludes_core_markers_and_grade_is_single_arabic_digit():
    cohort = yaml.safe_load((ROOT / "knowledge/schema/cohort_fields.yaml").read_text(encoding="utf-8"))
    by_key = {field["key"]: field for field in cohort["fields"]}
    other = by_key["postop_tumor_other_ihc"]
    assert other["exclude_markers"] == ["ER", "PR", "HER2", "Ki-67"]
    grade = by_key["postop_tumor_pathology_grade"]
    assert grade["values"] == ["1", "2", "3", "UNKNOWN"]
    assert grade["single_value_per_context"] is True

    assert normalize_observation_value("postop_tumor_pathology_grade", "G2") == "2"
    assert normalize_observation_value("postop_tumor_pathology_grade", "Ⅱ级") == "2"
    assert normalize_observation_value("pre_mmg_birads", "BI-RADS 4B") == "4B"
    assert normalize_observation_value("pre_mmg_birads", "3级") == "3"
    assert normalize_observation_value("primary_her2", "negative") == "0"
    assert normalize_observation_value("postop_node_her2", "阴性") == "0"
    assert normalize_observation_value(
        "postop_tumor_other_ihc", "ER 90%；PR 80%；HER2 2+；Ki-67 30%；P53 60%；AR +"
    ) == "P53 60%；AR +"

    prompt, _ = extraction_prompt("SURGICAL_PATHOLOGY", "ER 90%; P53 60%; 病理分级II级")
    assert "postop_tumor_other_ihc_excludes_core_four" in prompt
    assert "postop_tumor_pathology_grade_single_arabic_digit" in prompt


def test_regular_and_staging_prompts_can_be_split():
    regular_prompt, regular = extraction_prompt(
        "SURGICAL_PATHOLOGY", "术后病理文字", exclude_fields={"clinical_stage", "pathological_stage"}
    )
    staging_prompt, staging = extraction_prompt(
        "SURGICAL_PATHOLOGY", "术后病理文字", include_fields={"clinical_stage", "pathological_stage"}
    )
    assert not ({"clinical_stage", "pathological_stage"} & regular)
    assert staging == {"clinical_stage", "pathological_stage"}
    assert "postop_tumor_er" in regular_prompt
    assert "pathological_stage" in staging_prompt


def test_tnm_context_and_postoperative_pathology_source_strategy():
    surgery_prompt, surgery_fields = extraction_prompt("SURGERY", "术中见肿块及淋巴结")
    pathology_prompt, pathology_fields = extraction_prompt(
        "SURGICAL_PATHOLOGY", "浸润性癌，淋巴结2/15，ypT2N1M0"
    )
    assert "postop_tumor_pathology_type" not in surgery_fields
    assert "pathological_stage" not in surgery_fields
    assert "postop_tumor_pathology_type" in pathology_fields
    assert "pathological_stage" in pathology_fields
    assert "术后病理报告" in pathology_prompt
    assert source_priority("postop_node_metastasis", "SURGICAL_PATHOLOGY") > source_priority(
        "postop_node_metastasis", "DISCHARGE"
    )
    assert source_priority("postop_node_metastasis", "DISCHARGE") > source_priority(
        "postop_node_metastasis", "SURGERY"
    )
    assert source_priority("surgery_date", "SURGERY") > source_priority("surgery_date", "DISCHARGE")
    preferences = yaml.safe_load(
        (ROOT / "knowledge/rules/data_processing_preferences.yaml").read_text(encoding="utf-8")
    )
    component_evidence = preferences["staging_summary"]["component_evidence"]
    assert component_evidence["cT"]["preferred_sources"][:3] == [
        "pretreatment_ultrasound", "pretreatment_mammography", "pretreatment_mri"
    ]
    assert component_evidence["pT_or_ypT"]["preferred_sources"] == [
        "surgical_pathology_invasive_tumor_size"
    ]


def test_tnm_values_require_correct_context_prefix_and_all_components():
    assert normalize_observation_value("clinical_stage", "cT2 cN1 cM0") == "cT2N1M0"
    assert normalize_observation_value("pathological_stage", "ypT1 ypN0 cM0") == "ypT1N0M0"
    assert observation_value_is_valid("clinical_stage", "cT2N1M0") is True
    assert observation_value_is_valid("clinical_stage", "pT2N1M0") is False
    assert observation_value_is_valid("pathological_stage", "ypT1N0M0") is True
    assert observation_value_is_valid("pathological_stage", "IIA期") is False


def test_supportive_immune_care_is_not_antitumor_immunotherapy():
    assert immunotherapy_evidence_is_valid("住院给予免疫及对症支持治疗，予升白针") is False
    assert immunotherapy_evidence_is_valid("予帕博利珠单抗抗肿瘤免疫治疗") is True
    prompt, _ = extraction_prompt("TREATMENT", "住院给予免疫及对症支持治疗")
    assert "支持治疗" in prompt
    assert "帕博利珠单抗" in prompt


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
