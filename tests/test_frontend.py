from pathlib import Path

ROOT = Path(__file__).parents[1]


def test_import_controls_are_above_canvas_in_requested_order():
    html = (ROOT / "app/static/index.html").read_text(encoding="utf-8")
    document_type = html.index('id="document-type"')
    roi_type = html.index('id="roi-type"')
    display_name = html.index('id="display-name"')
    canvas = html.index('id="image-canvas"')
    assert document_type < roi_type < display_name < canvas


def test_editor_does_not_show_redundant_step_flow():
    html = (ROOT / "app/static/index.html").read_text(encoding="utf-8")
    assert 'class="steps"' not in html
    assert "1 选择原图" not in html


def test_unselected_patient_workspace_is_visually_empty():
    html = (ROOT / "app/static/index.html").read_text(encoding="utf-8")
    assert '<div id="empty-state" class="empty-state" aria-hidden="true"></div>' in html
    assert "请先新建或选择患者" not in html


def test_roi_types_are_document_specific_and_resizable():
    javascript = (ROOT / "app/static/app.js").read_text(encoding="utf-8")
    assert "roiTypesByDocument" in javascript
    assert 'MEDICAL_RECORD_COVER: [["cover_identity","病案号与出生日期"]' in javascript
    assert 'ADMISSION: [["admission_identity","病案号、性别与职业"]' in javascript
    assert '["imaging_date_phase","检查日期与治疗阶段"]' in javascript
    assert '["ihc_panel","ER/PR/HER2/Ki-67面板"]' in javascript
    assert "state.roiResize" in javascript
    assert "resizeRoi" in javascript


def test_sanitized_save_runs_ocr_before_ai_automatically():
    javascript = (ROOT / "app/static/app.js").read_text(encoding="utf-8")
    save_start = javascript.index('$("#save-sanitized").onclick')
    save_end = javascript.index("function rawStatusText", save_start)
    assert 'status:"OCR_QUEUED"' in javascript[save_start:save_end]
    ocr_worker = javascript[javascript.index("async function runOcrQueue"):javascript.index("async function runAiQueue")]
    assert "/ocr" in ocr_worker
    assert 'job.status="AI_QUEUED"' in ocr_worker


def test_batch_import_and_background_pipeline_do_not_block_next_image():
    html = (ROOT / "app/static/index.html").read_text(encoding="utf-8")
    javascript = (ROOT / "app/static/app.js").read_text(encoding="utf-8")
    assert 'id="raw-file" type="file" accept="image/*" multiple' in html
    assert 'id="raw-folder"' in html and "webkitdirectory" in html
    assert 'id="processing-queue"' in html
    assert "state.processingJobs.push(job)" in javascript
    assert "runProcessingQueue();" in javascript
    save_start = javascript.index('$("#save-sanitized").onclick')
    save_handler = javascript[save_start:javascript.index("function rawStatusText")]
    assert save_handler.index("runProcessingQueue()") < save_handler.index("loadRawItem(nextIndex)")


def test_ocr_and_ai_use_independent_parallel_workers_and_refresh_patient():
    javascript = (ROOT / "app/static/app.js").read_text(encoding="utf-8")
    assert "async function runOcrQueue" in javascript
    assert "async function runAiQueue" in javascript
    assert "state.ocrWorkerActive" in javascript
    assert "state.aiWorkerActive" in javascript
    ocr_worker = javascript[javascript.index("async function runOcrQueue"):javascript.index("async function runAiQueue")]
    assert "/ocr" in ocr_worker
    assert "refreshCurrentPatient(job.patientId)" in ocr_worker
    assert 'job.status="AI_QUEUED"' in ocr_worker


def test_document_buttons_use_visible_background_queue():
    javascript = (ROOT / "app/static/app.js").read_text(encoding="utf-8")
    document_renderer = javascript[javascript.index("function renderDocuments"):javascript.index("function renderObservations")]
    assert 'queueDocuments([doc],"OCR_ONLY")' in document_renderer
    assert 'queueDocuments([doc],"AI_ONLY")' in document_renderer
    assert "OCR任务已加入后台队列" in document_renderer


def test_batch_import_controls_are_separate_and_each_image_defaults_to_crop():
    html = (ROOT / "app/static/index.html").read_text(encoding="utf-8")
    javascript = (ROOT / "app/static/app.js").read_text(encoding="utf-8")
    batch_start = html.index('<div class="batch-import-bar">')
    batch_end = html.index('<div class="editor-toolbar">', batch_start)
    batch_bar = html[batch_start:batch_end]
    assert 'id="raw-file"' in batch_bar and 'id="raw-folder"' in batch_bar
    assert 'data-mode="crop"' not in batch_bar
    load_start = javascript.index("async function loadRawItem")
    load_end = javascript.index("function addRawFiles", load_start)
    assert 'state.mode="crop"' in javascript[load_start:load_end]


def test_original_enhanced_switch_persists_between_images():
    html = (ROOT / "app/static/index.html").read_text(encoding="utf-8")
    javascript = (ROOT / "app/static/app.js").read_text(encoding="utf-8")
    assert 'id="image-enhancement-toggle"' in html
    assert "原图" in html and "增强图" in html


def test_web_model_manager_can_select_current_ollama_model():
    html = (ROOT / "app/static/index.html").read_text(encoding="utf-8")
    javascript = (ROOT / "app/static/app.js").read_text(encoding="utf-8")
    assert 'id="current-model-status"' in html
    assert "设为当前模型" in javascript
    assert 'api("/api/settings/ollama-model"' in javascript
    assert "model.selected" in javascript


def test_model_refresh_shows_progress_and_prevents_repeated_clicks():
    html = (ROOT / "app/static/index.html").read_text(encoding="utf-8")
    javascript = (ROOT / "app/static/app.js").read_text(encoding="utf-8")
    assert 'id="model-refresh-status"' in html
    assert 'button.disabled=true' in javascript
    assert 'button.classList.add("is-loading")' in javascript
    assert "正在查询可用模型" in javascript
    assert "查询完成" in javascript
    assert 'api("/api/models/local-files")' in javascript
    assert 'api("/api/models/installed")' in javascript


def test_ai_queue_displays_live_stage_elapsed_token_rate_and_processor():
    javascript = (ROOT / "app/static/app.js").read_text(encoding="utf-8")
    assert "monitorAiProgress" in javascript
    assert "/extract-progress" in javascript
    assert "elapsed_seconds" in javascript
    assert "token_rate" in javascript
    assert "progress.processor" in javascript
    assert "正在生成结构化JSON" in javascript
    assert 'localStorage.getItem("image-enhancement")' in javascript
    assert 'localStorage.setItem("image-enhancement"' in javascript
    assert "createEnhancedImage(image)" in javascript
    assert 'persistEnhancement=!editingDocumentId&&state.enhancementEnabled' in javascript
    assert 'enhancement_mode:persistEnhancement?"ENHANCED":"ORIGINAL"' in javascript


def test_model_manager_distinguishes_local_file_from_pending_import():
    html = (ROOT / "app/static/index.html").read_text(encoding="utf-8")
    javascript = (ROOT / "app/static/app.js").read_text(encoding="utf-8")
    assert "本地 GGUF 文件" in html
    assert "待导入 GGUF" not in html
    assert "file.imported" in javascript
    assert "同一权重的标签" in javascript


def test_web_can_select_docker_or_windows_host_ollama():
    html = (ROOT / "app/static/index.html").read_text(encoding="utf-8")
    javascript = (ROOT / "app/static/app.js").read_text(encoding="utf-8")
    assert '<option value="DOCKER">Docker Ollama</option>' in html
    assert '<option value="WINDOWS_HOST">Windows宿主机 Ollama（AMD GPU）</option>' in html
    assert 'id="switch-ollama-provider"' in html
    assert 'api("/api/settings/ollama-provider"' in javascript
    assert "测试连接并使用" in javascript


def test_background_pipeline_runs_ocr_before_ai():
    javascript = (ROOT / "app/static/app.js").read_text(encoding="utf-8")
    ocr_start = javascript.index("async function runOcrQueue")
    ai_start = javascript.index("async function runAiQueue")
    end = javascript.index("function runProcessingQueue", ai_start)
    assert "/ocr" in javascript[ocr_start:ai_start]
    assert 'job.status="AI_QUEUED"' in javascript[ocr_start:ai_start]
    assert "/extract" in javascript[ai_start:end]


def test_saved_documents_have_bulk_ocr_and_ai_actions():
    html = (ROOT / "app/static/index.html").read_text(encoding="utf-8")
    javascript = (ROOT / "app/static/app.js").read_text(encoding="utf-8")
    assert 'id="bulk-ocr"' in html and "一键OCR" in html
    assert 'id="bulk-ai"' in html and "一键AI提取" in html
    assert 'queueDocuments(documents,"OCR_ONLY")' in javascript
    assert 'queueDocuments(documents,"AI_ONLY")' in javascript
    assert '!doc.ocr&&!activeIds.has(doc.id)' in javascript
    assert 'doc.ocr&&doc.status!=="AI_PROCESSED"' in javascript


def test_review_record_opens_editable_source_image_with_zoom_and_enhancement():
    html = (ROOT / "app/static/index.html").read_text(encoding="utf-8")
    javascript = (ROOT / "app/static/app.js").read_text(encoding="utf-8")
    assert "原图只会在此处本地显示" not in html
    assert 'id="zoom-out"' in html and 'id="zoom-in"' in html and 'id="zoom-fit"' in html
    assert "chooseObservation(obs)" in javascript
    assert "openSavedDocumentPreview(observation.document_id,observation.id)" in javascript
    assert "state.editingDocumentId=doc.id" in javascript
    assert "doc.regions||[]" in javascript
    assert "保存修改并重新识别" in javascript
    assert 'method:editingDocumentId?"PUT":"POST"' in javascript


def test_each_image_version_allows_only_one_ocr_and_one_ai_run():
    javascript = (ROOT / "app/static/app.js").read_text(encoding="utf-8")
    assert '${doc.ocr?"OCR已完成":"OCR识别"}' in javascript
    assert '${hasAi?"AI已完成":"AI提取"}' in javascript
    assert 'doc.ocr?"disabled":""' in javascript
    assert '!doc.ocr||hasAi?"disabled":""' in javascript
    assert "editorRevisionSignature()===state.editorBaseline" in javascript


def test_selected_patient_collapses_browser_and_field_review_uses_sidebar():
    html = (ROOT / "app/static/index.html").read_text(encoding="utf-8")
    javascript = (ROOT / "app/static/app.js").read_text(encoding="utf-8")
    assert 'id="patient-browser"' in html
    assert 'id="selected-patient-summary"' in html
    assert 'id="exit-patient"' in html
    assert 'id="field-review-panel"' in html
    assert 'id="review-current-value"' in html
    assert 'id="review-choice-options"' in html
    assert 'id="save-field-edit"' in html and 'id="verify-field"' in html
    assert '$("#patient-browser").hidden=selected' in javascript
    assert "state.selectedObservationId=observation.id" in javascript
    assert 'api(`/api/observations/${observation.id}`' in javascript
    assert 'api(`/api/observations/${observation.id}/verify`' in javascript
    assert "function renderReviewChoices(observation)" in javascript
    assert 'button.className="review-choice-option"' in javascript


def test_initial_patient_selection_is_main_view_and_review_can_advance_continuously():
    html = (ROOT / "app/static/index.html").read_text(encoding="utf-8")
    javascript = (ROOT / "app/static/app.js").read_text(encoding="utf-8")
    styles = (ROOT / "app/static/styles.css").read_text(encoding="utf-8")
    assert 'id="main-layout" class="layout patient-selection-mode"' in html
    assert ".layout.patient-selection-mode .workspace-panel { display: none; }" in styles
    assert 'id="previous-field"' in html and 'id="next-field"' in html
    assert 'id="review-position"' in html
    assert "navigateObservation(-1)" in javascript and "navigateObservation(1)" in javascript
    assert "nextUnverifiedObservation(confirmedId)" in javascript
    assert "已进入下一条待审核记录" in javascript


def test_verified_fields_remain_editable_and_can_be_confirmed_again():
    javascript = (ROOT / "app/static/app.js").read_text(encoding="utf-8")
    assert '$("#review-current-value").disabled=false' in javascript
    assert '$("#save-field-edit").disabled=false' in javascript
    assert 'verified?"再次确认":"人工确认"' in javascript


def test_review_fields_are_grouped_by_review_status_and_questionnaire_order():
    html = (ROOT / "app/static/index.html").read_text(encoding="utf-8")
    javascript = (ROOT / "app/static/app.js").read_text(encoding="utf-8")
    assert 'id="review-field-key"' in html
    assert "function orderedObservations()" in javascript
    assert 'left.status==="VERIFIED"' in javascript
    assert "left.field_order" in javascript
    assert 'reviewGroup==="VERIFIED"?"已人工审核":"待人工审核"' in javascript
    assert "const observations=orderedObservations()" in javascript
    assert 'observation.field_label||observation.field_name' in javascript
    assert 'class="observation-field-key">字段名：' in javascript
    assert "observation.candidate_values" in javascript
    assert "已合并 ${obs.candidate_count} 条候选" in javascript


def test_homepage_has_all_patient_data_preview_and_csv_export():
    html = (ROOT / "app/static/index.html").read_text(encoding="utf-8")
    javascript = (ROOT / "app/static/app.js").read_text(encoding="utf-8")
    styles = (ROOT / "app/static/styles.css").read_text(encoding="utf-8")
    assert 'id="open-data-preview"' in html
    assert 'id="data-preview-view"' in html
    assert 'id="data-preview-table"' in html
    assert 'id="data-preview-scope"' in html
    assert 'id="export-data-csv"' in html
    assert "导出CSV（Excel兼容）" not in html
    assert "function renderDataPreview()" in javascript
    assert "function loadDataPreview()" in javascript
    assert "/api/data-preview.csv?verified_only=" in javascript
    assert "position: sticky" in styles


def test_review_actions_completion_summary_delete_and_conflict_gallery_are_present():
    html = (ROOT / "app/static/index.html").read_text(encoding="utf-8")
    javascript = (ROOT / "app/static/app.js").read_text(encoding="utf-8")
    assert html.index('class="field-review-actions"') < html.index("AI原值")
    for element_id in (
        "delete-patient", "review-complete-panel", "review-patient-summary", "quick-add-patient",
        "conflict-evidence-gallery", "patient-review-dialog",
    ):
        assert f'id="{element_id}"' in html
    assert "renderConflictEvidence" in javascript
    assert 'api(`/api/patients/${id}`' in javascript
    assert "全部问题与答案" in javascript
    assert 'id="review-inference-basis"' in html
    assert "TNM评估依据" in javascript
