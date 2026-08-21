from pathlib import Path

import yaml

ROOT = Path(__file__).parents[1]


def test_roi_mapping_is_atomic_one_item_per_region():
    mapping = yaml.safe_load(
        (ROOT / "knowledge/schema/document_roi_mapping.yaml").read_text(encoding="utf-8")
    )
    assert mapping["version"] == "0.2.0"
    for document_name, document in mapping["documents"].items():
        assert document["regions"], document_name
        for region in document["regions"]:
            targets = list(region.get("target_fields", []))
            metadata = list(region.get("metadata_fields", []))
            assert not (targets and metadata), (document_name, region["key"])
            assert len(targets) + len(metadata) == 1, (document_name, region["key"])


def test_atomic_roi_policy_explicitly_allows_overlapping_single_item_boxes():
    mapping = yaml.safe_load(
        (ROOT / "knowledge/schema/document_roi_mapping.yaml").read_text(encoding="utf-8")
    )
    rules = "\n".join(mapping["global_rules"])
    assert "每个 ROI 只允许" in rules
    assert "逐项建立 ROI" in rules
    assert "可以重叠" in rules


def test_imaging_date_phase_and_measurements_are_split():
    mapping = yaml.safe_load(
        (ROOT / "knowledge/schema/document_roi_mapping.yaml").read_text(encoding="utf-8")
    )
    for document_type in ("ULTRASOUND", "MAMMOGRAPHY", "MRI"):
        regions = {region["key"]: region for region in mapping["documents"][document_type]["regions"]}
        assert regions["meta_exam_date"]["metadata_fields"] == ["exam_date"]
        assert regions["meta_treatment_phase"]["metadata_fields"] == ["treatment_phase"]
    us = {region["key"] for region in mapping["documents"]["ULTRASOUND"]["regions"]}
    assert {"pre_us_tumor_size_mm", "pre_us_tumor_location", "pre_us_nipple_distance_cm", "pre_us_skin_distance"} <= us


def test_ihc_core_markers_are_independent_roi_options():
    mapping = yaml.safe_load(
        (ROOT / "knowledge/schema/document_roi_mapping.yaml").read_text(encoding="utf-8")
    )
    ihc = {region["key"]: region for region in mapping["documents"]["IHC"]["regions"]}
    for key in ("primary_er", "primary_pr", "primary_her2", "primary_ki67"):
        assert ihc[key]["target_fields"] == [key]
    labels = {region["label"] for region in mapping["documents"]["IHC"]["regions"]}
    assert "ER/PR/HER2/Ki-67面板" not in labels


def test_treatment_regimen_and_cycles_are_independent_roi_options():
    mapping = yaml.safe_load(
        (ROOT / "knowledge/schema/document_roi_mapping.yaml").read_text(encoding="utf-8")
    )
    treatment = {region["key"]: region for region in mapping["documents"]["TREATMENT"]["regions"]}
    for key in (
        "neoadjuvant_regimen",
        "neoadjuvant_cycles",
        "postoperative_chemotherapy_regimen",
        "postoperative_chemotherapy_cycles",
        "postoperative_targeted_regimen",
        "postoperative_targeted_cycles",
        "postoperative_immunotherapy_regimen",
        "postoperative_immunotherapy_cycles",
    ):
        assert treatment[key]["target_fields"] == [key]


def test_frontend_runtime_menu_uses_atomic_options_and_removes_composite_labels():
    javascript = (ROOT / "app/static/atomic_roi.js").read_text(encoding="utf-8")
    assert "Object.assign(roiTypesByDocument, atomic)" in javascript
    for expected in (
        '["record_number","病案号"]',
        '["birth_date","出生日期"]',
        '["meta_exam_date","检查日期"]',
        '["meta_treatment_phase","治疗阶段"]',
        '["primary_er","原发灶ER"]',
        '["primary_pr","原发灶PR"]',
        '["primary_her2","原发灶HER2"]',
        '["primary_ki67","原发灶Ki-67"]',
        '["postoperative_chemotherapy_regimen","术后化疗方案"]',
        '["postoperative_chemotherapy_cycles","术后化疗周期"]',
    ):
        assert expected in javascript
    for merged_label in (
        "病案号与出生日期",
        "病案号、性别与职业",
        "检查日期与治疗阶段",
        "ER/PR/HER2/Ki-67面板",
        "术后化疗方案与周期",
    ):
        assert merged_label not in javascript


def test_atomic_roi_override_loads_before_windows_shutdown_early_return():
    javascript = (ROOT / "app/static/shutdown.js").read_text(encoding="utf-8")
    loader = javascript.index('roiScript.src = "/atomic_roi.js"')
    early_return = javascript.index("if (!token) return")
    assert loader < early_return
    assert 'roiScript.dataset.bceAtomicRoi = "1"' in javascript
