from pathlib import Path

ROOT = Path(__file__).parents[1]


def _app_script() -> str:
    return (ROOT / "app/static/app.js").read_text(encoding="utf-8")


def test_review_can_switch_patient_images_without_losing_field_or_region_drafts():
    script = _app_script()
    html = (ROOT / "app/static/index.html").read_text(encoding="utf-8")
    assert 'id="review-document-select"' in html
    assert 'id="review-document-previous"' in html
    assert 'id="review-document-next"' in html
    assert "reviewFieldDrafts: {}, reviewRegionDrafts: {}" in script
    assert "captureCurrentReviewDraft();captureCurrentRegionDraft();" in script
    assert "const draft=state.reviewRegionDrafts[observation?.id]?.[doc.id]" in script
    assert "const draft=state.reviewFieldDrafts[observation.id]" in script
    assert "openSavedDocumentPreview(doc.id,state.selectedObservationId)" in script


def test_current_field_reextract_uses_saved_position_and_priority_queue():
    script = _app_script()
    html = (ROOT / "app/static/index.html").read_text(encoding="utf-8")
    assert 'id="review-save-location"' not in html
    assert 'id="delete-review-position"' in html
    assert 'id="reextract-review-field"' in html
    assert "保存定位并重新提取当前字段" in html
    assert "/evidence-location" in script
    assert "saveCurrentReviewLocation()" in script
    assert 'target:"FIELD_ONLY"' in script
    assert 'state.processingJobs.unshift({' in script
    assert 'fieldOnly?"/extract-field":"/extract"' in script
    assert "field_name:job.fieldName,region_ids:job.regionIds||[]" in script


def test_virtual_review_field_is_materialized_before_position_save_and_reextract():
    script = _app_script()
    handler = script[
        script.index('$("#reextract-review-field").onclick') : script.index("function selectedObservation")
    ]
    assert "observation=await materializeVirtualObservation(" in handler
    assert handler.index("materializeVirtualObservation(") < handler.index("saveCurrentReviewLocation()")
    assert "const targetId=candidate?.id||observation.id" in script


def test_field_reextraction_replaces_current_value_instead_of_restoring_stale_draft():
    script = _app_script()
    ai_worker = script[
        script.index("async function runAiQueue") : script.index("function runProcessingQueue")
    ]
    assert "job.resultObservationId=extraction.observation?.id||null" in ai_worker
    assert "job.resultValue=extraction.observation?.value??null" in ai_worker
    assert "delete state.reviewFieldDrafts[job.observationId]" in ai_worker
    assert "delete state.reviewFieldDrafts[job.resultObservationId]" in ai_worker
    assert "state.reviewCandidateObservationId=job.resultObservationId" in ai_worker
    assert "updated.current_value=job.resultValue;updated.ai_value=job.resultValue" in ai_worker
    assert "重新提取结果已覆盖当前值" in ai_worker
    assert 'else if(job.target==="FIELD_ONLY"&&job.resultMessage)' in ai_worker


def test_derived_readonly_fields_cannot_enter_field_reextract_queue():
    script = _app_script()
    derived = (ROOT / "app/static/derived_fields.js").read_text(encoding="utf-8")
    assert "function isDerivedReviewField(fieldName)" in script
    assert '$("#reextract-review-field").disabled=derived||' in script
    assert "自动整理字段不能单独重新提取" in script
    assert 'replace(/^字段名\\s*[:：]\\s*/, "")' in derived
