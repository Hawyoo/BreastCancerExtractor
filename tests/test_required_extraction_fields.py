from app.knowledge import extraction_prompt


def test_cover_prompt_includes_contact_but_not_sex():
    prompt, allowed = extraction_prompt("MEDICAL_RECORD_COVER", "联系电话 13800000000")
    assert "contact" in allowed
    assert "sex" not in allowed
    assert "联系电话是必查字段" in prompt


def test_treatment_prompt_requires_last_visit_date():
    prompt, allowed = extraction_prompt("TREATMENT", "末次就诊时间 2026-08-01")
    assert "last_visit_date" in allowed
    assert "末次就诊时间是必查字段" in prompt
    assert "只要ROI或正文存在明确日期就必须输出last_visit_date" in prompt
