const $ = (selector) => document.querySelector(selector);
const $$ = (selector) => [...document.querySelectorAll(selector)];
const documentImageCache = new Map();
const DOCUMENT_IMAGE_CACHE_LIMIT = 8;

const state = {
  patients: [], patient: null, sourceImage: null, enhancedImage: null,
  mode: "crop", crop: null, cropEditable: false, cropResize: null,
  redactions: [], rois: [], activeRoiIndex: -1, roiResize: null, drawing: null,
  autoDisplayName: true,
  rawQueue: [], activeRawIndex: -1, rawLoadToken: 0, rawQueuePatientId: null,
  processingJobs: [], ocrWorkerActive: false, aiWorkerActive: false,
  enhancementEnabled: localStorage.getItem("image-enhancement") === "enhanced",
  viewZoom: 1, canvasFitScale: 1, reviewDocumentId: null, reviewObservationId: null,
  editingDocumentId: null, editorBaseline: null,
  selectedObservationId: null, reviewCandidateObservationId: null, reviewMode: false,
  reviewLocationDirty: false,
  reviewFieldDrafts: {}, reviewRegionDrafts: {},
  dataPreview: null,
};

const documentTypeLabels = {
  OTHER:"其他", MEDICAL_RECORD_COVER:"病案首页", ADMISSION:"入院记录", DISCHARGE:"出院记录",
  SURGERY:"手术记录", ULTRASOUND:"超声", MRI:"MRI", MAMMOGRAPHY:"钼靶",
  BIOPSY_PATHOLOGY:"穿刺病理", SURGICAL_PATHOLOGY:"术后病理", TREATMENT:"治疗记录",
};

const commonRoiTypes = [["OTHER","其他信息"]];
const roiTypesByDocument = {
  OTHER: commonRoiTypes,
  MEDICAL_RECORD_COVER: [["cover_identity","病案号与出生日期"],["cover_contact","联系方式"],["cover_occupation","职业"],...commonRoiTypes],
  ADMISSION: [["admission_identity","性别与职业"],["chronic_and_other_cancer_history","既往史、慢性病与其他癌种"],["prior_breast_history","乳腺癌及既往乳腺手术史"],["reproductive_history","婚育史"],["menstrual_history","月经与绝经史"],["family_history","家族史"],["lifestyle_history","吸烟与饮酒史"],["presentation_disease","偏侧性、来院转移与转移部位"],...commonRoiTypes],
  DISCHARGE: [["discharge_diagnosis","出院诊断、偏侧性与确诊日期"],["tnm_stage","TNM、临床分期与病理分期"],["pathology_summary","穿刺及术后病理摘要"],["ihc_summary","免疫组化摘要"],["fish_summary","FISH结果"],["surgery_summary","手术摘要"],["treatment_summary","治疗经过与方案"],["followup_plan","出院用药与随访计划"],...commonRoiTypes],
  SURGERY: [["surgery_date","手术日期"],["breast_surgery","乳房手术方式"],["axillary_surgery","腋窝手术方式"],["reconstruction","是否重建及重建方式"],...commonRoiTypes],
  ULTRASOUND: [["imaging_date_phase","检查日期与治疗阶段"],["malignant_lesion_size","恶性肿块大小"],["malignant_lesion_location","恶性肿块位置及距乳头/皮肤距离"],["regional_nodes","区域淋巴结情况"],["ultrasound_birads","BI-RADS分级"],["post_neoadj_response","新辅助后肿块及淋巴结缓解"],...commonRoiTypes],
  MRI: [["imaging_date_phase","检查日期与治疗阶段"],["malignant_lesion_size","恶性肿块大小"],["malignant_lesion_location","恶性肿块位置及距乳头/皮肤距离"],["regional_nodes","区域淋巴结情况"],["mri_birads","BI-RADS分级"],["post_neoadj_response","新辅助后肿块及淋巴结缓解"],...commonRoiTypes],
  MAMMOGRAPHY: [["imaging_date_phase","检查日期与治疗阶段"],["lesion_number_and_size","恶性肿块单发/多发及大小"],["malignant_lesion_location","恶性肿块位置及距乳头/皮肤距离"],["mammography_birads","BI-RADS分级"],["calcification","钙化情况"],["regional_nodes","区域淋巴结情况"],["other_mammography","其他钼靶结果"],...commonRoiTypes],
  BIOPSY_PATHOLOGY: [["specimen_and_date","标本部位与报告日期"],["primary_pathology","原发灶病理类型与分级"],["primary_ihc","原发灶ER/PR/HER2/Ki-67及其他IHC"],["node_pathology","淋巴结病理类型与分级"],["node_ihc","淋巴结ER/PR/HER2/Ki-67及其他IHC"],["metastasis_pathology","转移灶病理类型与分级"],["metastasis_ihc","转移灶ER/PR/HER2/Ki-67及其他IHC"],["biopsy_fish","FISH结果"],...commonRoiTypes],
  SURGICAL_PATHOLOGY: [["specimen_and_date","标本部位与报告日期"],["postop_tumor_pathology","术后肿块类型、分级与大小"],["postop_tumor_ihc","术后肿块ER/PR/HER2/Ki-67及其他IHC"],["postop_nodes","术后淋巴结数量与转移情况"],["postop_node_ihc","术后淋巴结ER/PR/HER2/Ki-67及其他IHC"],["surgical_fish","FISH结果"],["pathological_stage","pTNM/ypTNM及病理分期"],["neoadj_pathology_response","pCR、MP与RCB评估"],...commonRoiTypes],
  TREATMENT: [["neoadjuvant_treatment","新辅助方案、周期与日期"],["radiotherapy","放疗"],["chemotherapy","术后化疗方案与周期"],["endocrine_therapy","内分泌治疗方案"],["targeted_therapy","靶向治疗方案与周期"],["immunotherapy","免疫治疗方案与周期"],["palliative_treatment","姑息全身治疗方案"],["recurrence_metastasis","复发、转移及事件日期"],["second_primary","第二原发癌、日期及病理"],["followup_and_death","末次就诊、死亡状态与日期"],...commonRoiTypes],
};

function updateRoiTypeOptions() {
  const select=$("#roi-type"), options=roiTypesByDocument[$("#document-type").value]||commonRoiTypes;
  select.innerHTML=options.map(([value,label])=>`<option value="${value}">${label}</option>`).join("");
}

const canvas = $("#image-canvas");
const ctx = canvas.getContext("2d");
const ENHANCEMENT_VERSION = "browser-demoire-v1";

function activeImageSource() {
  return state.enhancementEnabled && state.enhancedImage ? state.enhancedImage : state.sourceImage;
}

function createEnhancedImage(image) {
  const reduced=document.createElement("canvas"),output=document.createElement("canvas");
  const factor=0.82;
  reduced.width=Math.max(1,Math.round(image.naturalWidth*factor));
  reduced.height=Math.max(1,Math.round(image.naturalHeight*factor));
  const reducedContext=reduced.getContext("2d",{alpha:false});
  reducedContext.imageSmoothingEnabled=true;reducedContext.imageSmoothingQuality="high";
  reducedContext.drawImage(image,0,0,reduced.width,reduced.height);
  output.width=image.naturalWidth;output.height=image.naturalHeight;
  const outputContext=output.getContext("2d",{alpha:false});
  outputContext.fillStyle="#fff";outputContext.fillRect(0,0,output.width,output.height);
  outputContext.imageSmoothingEnabled=true;outputContext.imageSmoothingQuality="high";
  outputContext.filter="contrast(1.14) saturate(.9)";
  outputContext.drawImage(reduced,0,0,output.width,output.height);
  outputContext.filter="none";outputContext.globalAlpha=.16;
  outputContext.drawImage(image,0,0,output.width,output.height);
  outputContext.globalAlpha=1;
  return output;
}

function updateEnhancementSwitch() {
  const button=$("#image-enhancement-toggle");
  button.setAttribute("aria-checked",String(state.enhancementEnabled));
  button.classList.toggle("active",state.enhancementEnabled);
}

$("#image-enhancement-toggle").onclick=()=>{
  state.enhancementEnabled=!state.enhancementEnabled;
  localStorage.setItem("image-enhancement",state.enhancementEnabled?"enhanced":"original");
  state.enhancedImage=state.enhancementEnabled&&state.sourceImage?createEnhancedImage(state.sourceImage):null;
  updateEnhancementSwitch();draw();
};
updateEnhancementSwitch();

function formatApiErrorDetail(detail, fallback) {
  if(typeof detail==="string"&&detail.trim())return detail.trim();
  if(Array.isArray(detail)){
    const messages=detail.map(item=>{
      if(typeof item==="string")return item;
      if(!item||typeof item!=="object")return String(item||"");
      const location=Array.isArray(item.loc)
        ? item.loc.filter(part=>!["body","query","path"].includes(String(part))).join(".")
        : "";
      const message=String(item.msg||item.message||item.error||"").replace(/^Value error,\s*/i,"");
      return [location,message].filter(Boolean).join("：");
    }).filter(Boolean);
    if(messages.length)return messages.join("；");
  }
  if(detail&&typeof detail==="object"){
    const nested=detail.message||detail.msg||detail.error||detail.detail;
    if(nested&&nested!==detail)return formatApiErrorDetail(nested,fallback);
    try{return JSON.stringify(detail);}catch(_){}
  }
  return fallback;
}

async function api(path, options = {}) {
  const response = await fetch(path, options);
  if (!response.ok) {
    let message = `请求失败 (${response.status})`;
    try {
      const payload=await response.json();
      message=formatApiErrorDetail(payload?.detail??payload?.message,message);
    } catch (_) {}
    throw new Error(message);
  }
  return response.status === 204 ? null : response.json();
}

function toast(message) {
  const box = $("#toast"); box.textContent = message; box.classList.add("show");
  setTimeout(() => box.classList.remove("show"), 2400);
}

async function loadHealth() {
  const health = await api("/api/health");
  const provider=health.ollama?.provider==="WINDOWS_HOST"?"宿主机":"Docker";
  const processor=health.ollama?.processor&&health.ollama.processor!=="IDLE"?` · ${health.ollama.processor}`:"";
  const selected=health.ollama?.default_model?` · ${health.ollama.default_model}`:"";
  const ollama = health.ollama?.available ? `${provider} Ollama ${health.ollama.models}个模型${selected}${processor}` : `${provider} Ollama未连接`;
  const ocr = health.ocr?.available ? "OCR已连接" : "OCR未连接";
  $("#service-status").textContent = `● 本地模式 · ${ollama} · ${ocr}`;
}

async function loadOllamaProviderSetting(){
  try{
    const setting=await api("/api/settings/ollama-provider");
    $("#ollama-provider").value=setting.provider;
    const processor=setting.health.processor==="IDLE"?"空闲":setting.health.processor;
    $("#ollama-provider-status").textContent=`当前：${setting.provider==="WINDOWS_HOST"?"Windows宿主机":"Docker"} · ${setting.health.available?`${setting.health.models}个模型 · ${processor}`:"未连接"}`;
  }catch(error){$("#ollama-provider-status").textContent=error.message;}
}

$("#switch-ollama-provider").onclick=async(event)=>{
  const button=event.currentTarget,provider=$("#ollama-provider").value;
  button.disabled=true;button.textContent="正在测试…";
  try{
    const result=await api("/api/settings/ollama-provider",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({provider})});
    toast(`已切换到${provider==="WINDOWS_HOST"?"Windows宿主机":"Docker"} Ollama`);
    await Promise.all([loadHealth(),loadOllamaProviderSetting()]);
    $("#refresh-models").click();
  }catch(error){toast(error.message);await loadOllamaProviderSetting();}
  finally{button.disabled=false;button.textContent="测试连接并使用";}
};

const systemTheme = window.matchMedia("(prefers-color-scheme: dark)");
function applyTheme(preference = localStorage.getItem("theme-preference") || "system") {
  const dark = preference === "dark" || (preference === "system" && systemTheme.matches);
  document.documentElement.dataset.theme = dark ? "dark" : "light";
  $("#theme-toggle").setAttribute("aria-checked", String(dark));
  $("#theme-system").classList.toggle("active", preference === "system");
}
$("#theme-toggle").addEventListener("click", () => {
  const preference = document.documentElement.dataset.theme === "dark" ? "light" : "dark";
  localStorage.setItem("theme-preference", preference); applyTheme(preference);
});
$("#theme-system").onclick = () => { localStorage.removeItem("theme-preference"); applyTheme("system"); };
systemTheme.addEventListener("change", () => {
  if (!localStorage.getItem("theme-preference")) applyTheme("system");
});
applyTheme();

function formatPatientDateTime(value) {
  const date=new Date(value);
  if(Number.isNaN(date.getTime()))return "—";
  return new Intl.DateTimeFormat("zh-CN",{
    year:"numeric",month:"2-digit",day:"2-digit",hour:"2-digit",minute:"2-digit",hour12:false,
  }).format(date).replace(/\//g,"-");
}

async function loadPatients() {
  state.patients = await api("/api/patients");
  const list = $("#patient-list"); list.innerHTML = "";
  for (const patient of state.patients) {
    const button = document.createElement("button");
    button.className = `patient-item ${state.patient?.id === patient.id ? "active" : ""}`;
    button.innerHTML = `<strong>${escapeHtml(patient.patient_code)}</strong><small>${patient.document_count} 张脱敏图 · ${statusText(patient.status)}</small><div class="patient-card-dates"><small>创建：${formatPatientDateTime(patient.created_at)}</small><small>修改：${formatPatientDateTime(patient.updated_at)}</small></div>`;
    button.onclick = () => selectPatient(patient.id);
    list.appendChild(button);
  }
  updatePatientSidebar();
  window.dispatchEvent(new CustomEvent("bce:patients-rendered",{detail:{count:state.patients.length}}));
}

function packageCounts(item){
  const counts=item.counts||{};
  return `${counts.documents||0} 张图片 · ${counts.observations||0} 条字段`;
}

async function importPatientPackage(packageName,action){
  const labels={IMPORT_NEW:"导入",KEEP_LOCAL:"保留本机",USE_EXTERNAL:"使用外部",MERGE:"合并"};
  if(["USE_EXTERNAL","MERGE"].includes(action)&&!confirm(`确定对该患者执行“${labels[action]}”吗？\n所有操作会写入审计记录。`))return;
  const result=await api("/api/data-migration/import",{
    method:"POST",headers:{"Content-Type":"application/json"},
    body:JSON.stringify({package_name:packageName,action}),
  });
  const suffix=result.conflicts?.length?`，${result.conflicts.length} 项冲突已进入人工审核`:"";
  toast(`患者 ${result.patient_code} 已${labels[action]}${suffix}`);
  await Promise.all([loadPatients(),loadPatientPackages()]);
}

function packageActionButton(label,item,action,className="tool"){
  const button=document.createElement("button");button.type="button";button.className=className;button.textContent=label;
  button.onclick=()=>importPatientPackage(item.package_name,action).catch(error=>toast(error.message));
  return button;
}

function renderPatientPackages(scan){
  const container=$("#patient-package-results");container.innerHTML="";
  const sections=[
    ["待导入",scan.new||[],item=>[packageActionButton("导入患者",item,"IMPORT_NEW","primary")]],
    ["重复患者 / 需要选择",scan.conflicts||[],item=>[
      packageActionButton("保留本机",item,"KEEP_LOCAL"),
      packageActionButton("使用外部",item,"USE_EXTERNAL","danger-tool"),
      packageActionButton("合并并审核冲突",item,"MERGE","primary"),
    ]],
    ["已登记",scan.current||[],()=>[]],
    ["无效目录",scan.invalid||[],()=>[]],
  ];
  let total=0;
  for(const [title,items,actions] of sections){
    if(!items.length)continue;total+=items.length;
    const heading=document.createElement("h5");heading.textContent=`${title}（${items.length}）`;container.appendChild(heading);
    for(const item of items){
      const card=document.createElement("div");card.className="patient-package-card";
      const info=document.createElement("div");
      const code=item.patient_code||item.package_name;
      info.innerHTML=`<strong>${escapeHtml(code)}</strong><small>${escapeHtml(item.error||packageCounts(item))}</small>`;
      if(item.verified_conflicts?.length){
        const warning=document.createElement("small");warning.className="package-conflict-note";
        warning.textContent=`${item.verified_conflicts.length} 项人工确认值冲突`;
        info.appendChild(warning);
      }
      const actionBox=document.createElement("div");actionBox.className="patient-package-actions";
      actions(item).forEach(button=>actionBox.appendChild(button));card.append(info,actionBox);container.appendChild(card);
    }
  }
  if(!total)container.innerHTML='<div class="muted-empty">未发现可登记或冲突的患者目录</div>';
}

async function loadPatientPackages(){
  const button=$("#scan-patient-packages");button.disabled=true;button.textContent="正在扫描…";
  try{renderPatientPackages(await api("/api/data-migration/scan"));}
  finally{button.disabled=false;button.textContent="扫描患者目录";}
}

$("#scan-patient-packages").onclick=async()=>{
  $("#patient-package-panel").hidden=false;
  try{await loadPatientPackages();}catch(error){toast(error.message);}
};
$("#close-patient-packages").onclick=()=>{$("#patient-package-panel").hidden=true;};

function renderDataPreview() {
  const dataset=state.dataPreview,table=$("#data-preview-table"),head=table.querySelector("thead"),body=table.querySelector("tbody");
  head.innerHTML="";body.innerHTML="";
  if(!dataset)return;
  const metrics=dataset.review_metrics||{};
  $("#review-quality-metrics").innerHTML=[
    ["审核完成率",`${Number(metrics.verification_rate||0).toFixed(1)}%`],
    ["已确认字段",metrics.verified_fields||0],
    ["待审核字段",metrics.pending_fields||0],
    ["冲突字段",metrics.conflict_fields||0],
    ["人工修改字段",metrics.manually_modified_fields||0],
  ].map(([label,value])=>`<div class="review-quality-metric"><strong>${escapeHtml(value)}</strong><span>${escapeHtml(label)}</span></div>`).join("");
  const headerRow=document.createElement("tr");
  for(const column of dataset.columns){
    const th=document.createElement("th");th.textContent=column.label;th.title=`字段名：${column.key}`;headerRow.appendChild(th);
  }
  head.appendChild(headerRow);
  const query=$("#data-preview-search").value.trim();
  const rows=dataset.rows.filter(row=>!query||row.patient_code.includes(query));
  for(const row of rows){
    const tr=document.createElement("tr");
    for(const column of dataset.columns){
      const td=document.createElement("td"),value=row.values[column.key]??"",status=row.statuses[column.key]||"EMPTY";
      td.textContent=value;td.title=value?`${column.label}：${value}\n字段名：${column.key}`:column.label;
      if(status==="VERIFIED")td.classList.add("status-verified");
      else if(!["EMPTY","UNAVAILABLE","NOT_APPLICABLE"].includes(status))td.classList.add("status-pending");
      tr.appendChild(td);
    }
    body.appendChild(tr);
  }
  $("#data-preview-summary").textContent=`${rows.length} 名患者 · ${dataset.columns.length} 个问卷字段 · ${dataset.verified_only?"仅显示人工已确认结果":"显示全部当前结果"}`;
}

async function loadDataPreview() {
  const verifiedOnly=$("#data-preview-scope").value==="verified",loading=$("#data-preview-loading");
  loading.hidden=false;$("#data-preview-table").hidden=true;
  try{
    state.dataPreview=await api(`/api/data-preview?verified_only=${verifiedOnly}`);
    renderDataPreview();
  }finally{
    loading.hidden=true;$("#data-preview-table").hidden=false;
  }
}

$("#open-data-preview").onclick=async()=>{
  $("#main-layout").hidden=true;$("#data-preview-view").hidden=false;
  try{
    await loadDataPreview();
    requestAnimationFrame(()=>document.querySelector(".data-table-shell")?.scrollIntoView({behavior:"smooth",block:"start"}));
  }catch(error){toast(error.message);}
};
$("#close-data-preview").onclick=()=>{$("#data-preview-view").hidden=true;$("#main-layout").hidden=false;};
$("#data-preview-scope").onchange=()=>loadDataPreview().catch(error=>toast(error.message));
$("#data-preview-search").oninput=()=>renderDataPreview();
$("#export-data-csv").onclick=()=>{
  const verifiedOnly=$("#data-preview-scope").value==="verified";
  const link=document.createElement("a");link.href=`/api/data-preview.csv?verified_only=${verifiedOnly}`;link.download="";
  document.body.appendChild(link);link.click();link.remove();
};

function updatePatientSidebar() {
  const selected=Boolean(state.patient);
  $("#main-layout").classList.toggle("patient-selection-mode",!selected);
  $("#patient-browser").hidden=selected;
  $("#selected-patient-summary").hidden=!selected;
  if(!selected){$("#field-review-panel").hidden=true;$("#review-complete-panel").hidden=true;return;}
  $("#sidebar-patient-code").textContent=state.patient.patient_code;
  $("#sidebar-patient-meta").textContent=`${state.patient.documents?.length||0} 张脱敏图 · ${statusText(state.patient.status)}`;
  renderFieldReview();
}

async function selectPatient(id) {
  const switching=state.patient&&state.patient.id!==id;
  if (state.rawQueuePatientId && state.rawQueuePatientId !== id) clearRawQueue();
  if(switching){
    clearEditor();state.selectedObservationId=null;documentImageCache.clear();
    state.reviewFieldDrafts={};state.reviewRegionDrafts={};
  }
  state.patient = await api(`/api/patients/${id}?review_blank_parents=true`);
  $("#empty-state").hidden = true; $("#patient-workspace").hidden = false;
  $("#current-patient-code").textContent = state.patient.patient_code;
  $("#current-patient-status").textContent = statusText(state.patient.status);
  renderDocuments(); renderObservations(); updatePatientSidebar(); await loadPatients();
}

async function refreshCurrentPatient(patientId) {
  if (!state.patient || state.patient.id !== patientId) return;
  const selectedFieldName=(state.patient.observations||[])
    .find(item=>item.id===state.selectedObservationId)?.field_name||null;
  state.patient = await api(`/api/patients/${patientId}?review_blank_parents=true`);
  if(state.selectedObservationId&&!state.patient.observations.some(item=>item.id===state.selectedObservationId)&&selectedFieldName){
    const replacement=state.patient.observations.find(item=>item.field_name===selectedFieldName);
    state.selectedObservationId=replacement?.id||null;
  }
  $("#current-patient-status").textContent = statusText(state.patient.status);
  renderDocuments(); renderObservations(); updatePatientSidebar(); await loadPatients();
}

let patientListRefreshTimer=null;
function schedulePatientListRefresh() {
  if(patientListRefreshTimer!==null)clearTimeout(patientListRefreshTimer);
  patientListRefreshTimer=setTimeout(()=>{
    patientListRefreshTimer=null;
    loadPatients().catch(error=>toast(error.message));
  },500);
}

function applyObservationReviewResult(result) {
  if(!state.patient)return;
  const observation=(state.patient.observations||[]).find(item=>item.id===(result.requested_id||result.id))
    ||(state.patient.observations||[]).find(item=>item.id===result.id);
  if(observation){
    if(result.region){
      const selectedCandidate=(observation.candidate_values||[]).find(candidate=>candidate.id===result.id);
      const replacedRegionIds=new Set([observation.region_id,selectedCandidate?.region_id].filter(Boolean));
      for(const doc of state.patient.documents||[]){
        doc.regions=(doc.regions||[]).filter(region=>!replacedRegionIds.has(region.id));
      }
      const regionDocument=(state.patient.documents||[]).find(doc=>doc.id===result.region.document_id);
      if(regionDocument)regionDocument.regions.push(result.region);
    }
    observation.id=result.id;
    observation.document_id=result.document_id;
    observation.region_id=result.region_id;
    observation.evidence_status=result.evidence_status;
    observation.current_value=result.value;
    observation.status=result.status;
    observation.confidence=result.confidence;
    for(const candidate of observation.candidate_values||[]){
      candidate.selected=candidate.id===result.id;
      if(candidate.selected&&result.region){
        candidate.document_id=result.document_id;candidate.region_id=result.region_id;
      }
    }
    state.selectedObservationId=result.id;
  }
  const superseded=new Set(result.superseded_ids||[]);
  for(const candidate of state.patient.observations||[]){
    if(superseded.has(candidate.id))candidate.status="SUPERSEDED";
  }
  if(result.patient_status)state.patient.status=result.patient_status;
  state.reviewLocationDirty=false;
  $("#current-patient-status").textContent=statusText(state.patient.status);
  renderObservations();updatePatientSidebar();schedulePatientListRefresh();
}

function leavePatient() {
  const pending=state.rawQueue.some(item=>item.file&&item.status!=="SAVED");
  if(pending&&!confirm("仍有未保存的导入图片，退出患者将清空当前待处理队列。确定退出吗？"))return false;
  const reviewDialog=$("#patient-review-dialog");
  if(reviewDialog?.open)reviewDialog.close();
  clearRawQueue();state.patient=null;state.selectedObservationId=null;state.reviewFieldDrafts={};state.reviewRegionDrafts={};
  $("#patient-workspace").hidden=true;$("#empty-state").hidden=false;
  updatePatientSidebar();loadPatients().catch(error=>toast(error.message));
  return true;
}

$("#exit-patient").onclick=leavePatient;

$("#delete-patient").onclick=async()=>{
  if(!state.patient)return;
  const {id,patient_code:code}=state.patient;
  if(!confirm(`确定永久删除患者 ${code} 吗？\n该患者的全部脱敏图片、OCR、AI结果、人工修改和审计记录都会删除。`))return;
  try{
    await api(`/api/patients/${id}`,{method:"DELETE"});
    state.processingJobs=state.processingJobs.filter(job=>job.patientId!==id);
    clearRawQueue();state.patient=null;state.selectedObservationId=null;
    $("#patient-workspace").hidden=true;$("#empty-state").hidden=false;
    updatePatientSidebar();renderProcessingQueue();await loadPatients();toast(`患者 ${code} 已删除`);
  }catch(error){toast(error.message);}
};

function suggestedDisplayName() {
  const type = $("#document-type").value;
  const label = documentTypeLabels[type] || "文档";
  const existing = (state.patient?.documents || []).filter(document => document.document_type === type).length;
  return `${label}-第${existing + 1}页`;
}

function refreshDefaultDisplayName(force = false) {
  if (force || state.autoDisplayName || !$("#display-name").value.trim()) {
    $("#display-name").value = suggestedDisplayName();
    state.autoDisplayName = true;
  }
}

$("#document-type").addEventListener("change", () => {
  refreshDefaultDisplayName(); updateRoiTypeOptions();
  const item=state.rawQueue[state.activeRawIndex];
  if(item){item.documentType=$("#document-type").value;item.displayName=$("#display-name").value;item.autoDisplayName=state.autoDisplayName;renderRawQueue();}
});
$("#display-name").addEventListener("input", () => {
  state.autoDisplayName = false;
  const item=state.rawQueue[state.activeRawIndex];
  if(item){item.displayName=$("#display-name").value;item.autoDisplayName=false;renderRawQueue();}
});
updateRoiTypeOptions();

function statusText(status) {
  return ({UNPROCESSED:"未处理",AI_PROCESSED:"AI 已处理",REVIEW_REQUIRED:"待人工确认",VERIFIED:"人工已确认",EMPTY:"未填写",UNAVAILABLE:"不可用",NOT_APPLICABLE:"不适用"})[status] || status;
}

function escapeHtml(value) {
  const div = document.createElement("div"); div.textContent = value ?? ""; return div.innerHTML;
}

$("#patient-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  try {
    const patient = await api("/api/patients", {method:"POST", headers:{"Content-Type":"application/json"}, body:JSON.stringify({patient_code:$("#patient-code").value.trim()})});
    $("#patient-code").value = ""; await loadPatients(); await selectPatient(patient.id);
  } catch (error) { toast(error.message); }
});
$("#refresh-patients").onclick = loadPatients;

function guessDocumentType(filename) {
  const name=filename.toLowerCase();
  const patterns=[
    ["MEDICAL_RECORD_COVER",/首页|病案/],["ADMISSION",/入院|首次病程/],["DISCHARGE",/出院/],
    ["SURGERY",/手术记录|手术/],["ULTRASOUND",/超声|彩超/],["MRI",/mri|磁共振/],
    ["MAMMOGRAPHY",/钼靶|乳腺摄影/],["SURGICAL_PATHOLOGY",/术后病理|大病理/],
    ["BIOPSY_PATHOLOGY",/穿刺|活检|免疫组化|ihc/],["TREATMENT",/化疗|放疗|内分泌|靶向|治疗/],
  ];
  return patterns.find(([,pattern])=>pattern.test(name))?.[0]||"OTHER";
}

function currentEditorSnapshot() {
  return {
    crop:state.crop?{...state.crop}:null,cropEditable:state.cropEditable,
    redactions:state.redactions.map(item=>({...item})),rois:state.rois.map(item=>({...item})),
    documentType:$("#document-type").value,displayName:$("#display-name").value,
    autoDisplayName:state.autoDisplayName,
  };
}

function editorRevisionSignature() {
  const cleanRect=rect=>({
    x:Number(rect.x.toFixed(3)),y:Number(rect.y.toFixed(3)),
    width:Number(rect.width.toFixed(3)),height:Number(rect.height.toFixed(3)),
    ...(rect.type?{type:rect.type}:{}),
  });
  return JSON.stringify({
    crop:state.crop?cleanRect(state.crop):null,
    redactions:state.redactions.map(cleanRect),
    rois:state.rois.map(cleanRect),
  });
}

function updateSaveAction() {
  const button=$("#save-sanitized");
  if(!state.sourceImage){button.disabled=true;button.textContent="确认脱敏并保存";return;}
  if(state.editingDocumentId){
    const changed=editorRevisionSignature()!==state.editorBaseline;
    button.disabled=!changed;
    button.textContent=changed?"保存修改并重新识别":"修改图片或ROI后可保存";
  }else{
    button.disabled=false;button.textContent="确认脱敏并保存";
  }
}

function persistActiveRawItem() {
  const item=state.rawQueue[state.activeRawIndex];
  if(item&&state.sourceImage&&item.status!=="SAVED")Object.assign(item,currentEditorSnapshot());
}

function clearEditor() {
  state.sourceImage=null;state.enhancedImage=null;state.crop=null;state.cropEditable=false;state.cropResize=null;
  state.redactions=[];state.rois=[];state.activeRoiIndex=-1;state.roiResize=null;state.drawing=null;
  state.viewZoom=1;state.canvasFitScale=1;state.reviewDocumentId=null;state.reviewObservationId=null;
  state.editingDocumentId=null;state.editorBaseline=null;
  state.reviewMode=false;state.reviewLocationDirty=false;
  setReviewWorkspace(false);
  ctx.clearRect(0,0,canvas.width,canvas.height);canvas.width=0;canvas.height=0;
  $("#canvas-placeholder").hidden=false;enableEditor(false);setMetadataControlsEnabled(true);updateZoomControls();
}

function clearRawQueue() {
  clearEditor();state.rawQueue=[];state.activeRawIndex=-1;state.rawQueuePatientId=null;state.rawLoadToken+=1;
  $("#raw-file").value="";$("#raw-folder").value="";renderRawQueue();
}

async function loadRawItem(index) {
  const item=state.rawQueue[index]; if(!item||!item.file||item.status==="SAVED")return;
  const previous=state.rawQueue[state.activeRawIndex];persistActiveRawItem();
  if(previous&&previous!==item&&previous.status==="EDITING")previous.status="WAITING";
  clearEditor();state.activeRawIndex=index;item.status="EDITING";renderRawQueue();
  const token=++state.rawLoadToken,url=URL.createObjectURL(item.file),image=new Image();
  await new Promise((resolve,reject)=>{
    image.onload=()=>{URL.revokeObjectURL(url);resolve();};
    image.onerror=()=>{URL.revokeObjectURL(url);reject(new Error(`无法读取 ${item.localName}`));};
    image.src=url;
  });
  if(token!==state.rawLoadToken)return;
  state.sourceImage=image;
  state.enhancedImage=state.enhancementEnabled?createEnhancedImage(image):null;
  state.viewZoom=1;state.reviewDocumentId=null;state.reviewObservationId=null;
  state.editingDocumentId=null;state.editorBaseline=null;
  state.mode="crop";
  $$('[data-mode]').forEach(button=>button.classList.toggle("active",button.dataset.mode==="crop"));
  state.crop=item.crop||{x:0,y:0,width:image.naturalWidth,height:image.naturalHeight};
  state.cropEditable=item.cropEditable||false;state.cropResize=null;
  state.redactions=(item.redactions||[]).map(value=>({...value}));state.rois=(item.rois||[]).map(value=>({...value}));
  state.activeRoiIndex=state.rois.length-1;state.roiResize=null;state.drawing=null;
  $("#document-type").value=item.documentType;updateRoiTypeOptions();
  state.autoDisplayName=item.autoDisplayName;$("#display-name").value=item.displayName;
  setMetadataControlsEnabled(true);enableEditor(true);fitCanvas();draw();$("#canvas-placeholder").hidden=true;
  $("#editor-help").textContent=`第 ${index+1}/${state.rawQueue.length} 张：完成后将自动打开下一张。`;
}

function addRawFiles(fileList) {
  if(!state.patient)return toast("请先选择患者");
  const files=[...fileList]
    .filter(file=>file.type.startsWith("image/"))
    .sort((left,right)=>(left.webkitRelativePath||left.name).localeCompare(
      right.webkitRelativePath||right.name,"zh-CN",{numeric:true},
    ));
  if(!files.length)return toast("未发现支持的图片");
  state.rawQueuePatientId=state.patient.id;
  for(const file of files){
    const documentType=guessDocumentType(file.name),label=documentTypeLabels[documentType]||"文档";
    const sequence=state.rawQueue.filter(item=>item.documentType===documentType).length+(state.patient.documents||[]).filter(doc=>doc.document_type===documentType).length+1;
    state.rawQueue.push({id:crypto.randomUUID(),file,localName:file.webkitRelativePath||file.name,status:"WAITING",documentType,displayName:`${label}-第${sequence}页`,autoDisplayName:true,crop:null,cropEditable:false,redactions:[],rois:[]});
  }
  renderRawQueue();
  if(state.activeRawIndex<0||!state.sourceImage)loadRawItem(state.rawQueue.findIndex(item=>item.status==="WAITING")).catch(error=>toast(error.message));
}

$("#raw-file").addEventListener("change",event=>{addRawFiles(event.target.files);event.target.value="";});
$("#raw-folder").addEventListener("change",event=>{addRawFiles(event.target.files);event.target.value="";});

function enableEditor(enabled) {
  $$(".editor-toolbar .tool").forEach(button => button.disabled = !enabled);
  $$(".editor-toolbar .preview-tool").forEach(button => button.disabled = !state.sourceImage);
  $("#save-sanitized").disabled = !enabled;
  updateSaveAction();
}

function setMetadataControlsEnabled(enabled) {
  [$("#document-type"),$("#roi-type"),$("#display-name")].forEach(control=>control.disabled=!enabled);
}

function updateZoomControls() {
  const percent=Math.round(state.viewZoom*100);
  $("#zoom-level").textContent=state.viewZoom===1?"适应窗口":`${percent}%`;
  $("#review-zoom-level").textContent=state.viewZoom===1?"适应窗口":`${percent}%`;
  $$(".preview-tool").forEach(button=>button.disabled=!state.sourceImage);
  $("#zoom-out").disabled=!state.sourceImage||state.viewZoom<=0.5;
  $("#zoom-in").disabled=!state.sourceImage||state.viewZoom>=4;
}

function fitCanvas() {
  const image = state.sourceImage; if (!image) return;
  const maxWidth = Math.min(1100, $(".canvas-shell").clientWidth - 4);
  state.canvasFitScale = Math.min(1, maxWidth / image.naturalWidth, 780 / image.naturalHeight);
  const dimensionLimit=Math.min(8192/image.naturalWidth,8192/image.naturalHeight);
  const scale = Math.min(state.canvasFitScale*state.viewZoom,dimensionLimit);
  canvas.width = Math.round(image.naturalWidth * scale);
  canvas.height = Math.round(image.naturalHeight * scale);
  updateZoomControls();
}

function setViewZoom(value) {
  if(!state.sourceImage)return;
  state.viewZoom=Math.max(0.5,Math.min(4,Math.round(value*4)/4));
  fitCanvas();draw();
}

$("#zoom-out").onclick=()=>setViewZoom(state.viewZoom-0.25);
$("#zoom-in").onclick=()=>setViewZoom(state.viewZoom+0.25);
$("#zoom-fit").onclick=()=>setViewZoom(1);
$("#review-zoom-out").onclick=()=>setViewZoom(state.viewZoom-0.25);
$("#review-zoom-in").onclick=()=>setViewZoom(state.viewZoom+0.25);
$("#review-zoom-fit").onclick=()=>setViewZoom(1);

function scaleX() { return state.sourceImage ? canvas.width / state.sourceImage.naturalWidth : 1; }
function scaleY() { return state.sourceImage ? canvas.height / state.sourceImage.naturalHeight : 1; }
function toSource(point) { return {x:point.x/scaleX(), y:point.y/scaleY()}; }
function normalizedRect(a,b) { return {x:Math.min(a.x,b.x),y:Math.min(a.y,b.y),width:Math.abs(a.x-b.x),height:Math.abs(a.y-b.y)}; }

function draw() {
  if (!state.sourceImage) return;
  ctx.clearRect(0,0,canvas.width,canvas.height);
  ctx.drawImage(activeImageSource(),0,0,canvas.width,canvas.height);
  if (state.crop) {
    const r = displayRect(state.crop); ctx.save(); ctx.fillStyle="rgba(0,0,0,.48)";
    ctx.fillRect(0,0,canvas.width,r.y); ctx.fillRect(0,r.y,r.x,r.height);
    ctx.fillRect(r.x+r.width,r.y,canvas.width-r.x-r.width,r.height);
    ctx.fillRect(0,r.y+r.height,canvas.width,canvas.height-r.y-r.height);
    ctx.strokeStyle="#f4c95d"; ctx.lineWidth=2; ctx.strokeRect(r.x,r.y,r.width,r.height);
    if (state.cropEditable) drawResizeHandles(r,"#f4c95d");
    ctx.restore();
  }
  for (const rect of state.redactions) drawOverlay(rect,"#000000","#000000","");
  state.rois.forEach((roi,index)=>{
    drawOverlay(roi,"rgba(39,147,104,.16)","#31a87a",roi.label);
    if(state.mode==="roi"&&state.activeRoiIndex===index)drawResizeHandles(displayRect(roi),"#31a87a");
  });
  if (state.drawing) {
    const draftFill=state.mode==="redact"?"rgba(18,18,18,.42)":"rgba(255,196,68,.16)";
    const draftStroke=state.mode==="redact"?"#111111":"#f2bd3e";
    drawDisplayOverlay(normalizedRect(state.drawing.start,state.drawing.end),draftFill,draftStroke,state.mode);
  }
  updateSaveAction();
}

function displayRect(rect) { return {x:rect.x*scaleX(),y:rect.y*scaleY(),width:rect.width*scaleX(),height:rect.height*scaleY()}; }
function drawOverlay(rect,fill,stroke,label) {
  drawDisplayOverlay(displayRect(rect),fill,stroke,label);
}
function drawDisplayOverlay(r,fill,stroke,label) {
  ctx.save(); ctx.fillStyle=fill; ctx.strokeStyle=stroke; ctx.lineWidth=2; ctx.fillRect(r.x,r.y,r.width,r.height); ctx.strokeRect(r.x,r.y,r.width,r.height);
  if (label && r.width > 45) { ctx.font="12px Segoe UI"; ctx.fillStyle=stroke; ctx.fillText(label,r.x+4,r.y+14); }
  ctx.restore();
}

function drawResizeHandles(r,stroke) {
  const points = [
    [r.x,r.y],[r.x+r.width/2,r.y],[r.x+r.width,r.y],
    [r.x,r.y+r.height/2],[r.x+r.width,r.y+r.height/2],
    [r.x,r.y+r.height],[r.x+r.width/2,r.y+r.height],[r.x+r.width,r.y+r.height],
  ];
  ctx.fillStyle="#fff"; ctx.strokeStyle=stroke; ctx.lineWidth=2;
  for (const [x,y] of points) { ctx.fillRect(x-5,y-5,10,10); ctx.strokeRect(x-5,y-5,10,10); }
}

function rectEdgesAt(rect,point,tolerance=11) {
  const r=displayRect(rect);
  const nearLeft=Math.abs(point.x-r.x)<=tolerance, nearRight=Math.abs(point.x-r.x-r.width)<=tolerance;
  const nearTop=Math.abs(point.y-r.y)<=tolerance, nearBottom=Math.abs(point.y-r.y-r.height)<=tolerance;
  const withinX=point.x>=r.x-tolerance&&point.x<=r.x+r.width+tolerance;
  const withinY=point.y>=r.y-tolerance&&point.y<=r.y+r.height+tolerance;
  const edges=[];
  if(nearLeft&&withinY)edges.push("left"); else if(nearRight&&withinY)edges.push("right");
  if(nearTop&&withinX)edges.push("top"); else if(nearBottom&&withinX)edges.push("bottom");
  return edges.length?edges:null;
}

function cropEdgeAt(point) {
  if (!state.crop || !state.cropEditable) return null;
  return rectEdgesAt(state.crop,point);
}

function roiHitAt(point) {
  for(let index=state.rois.length-1;index>=0;index--){
    const roi=state.rois[index], r=displayRect(roi), edges=rectEdgesAt(roi,point);
    const inside=point.x>=r.x&&point.x<=r.x+r.width&&point.y>=r.y&&point.y<=r.y+r.height;
    if(edges||inside)return {index,edges};
  }
  return null;
}

function cropCursor(edges) {
  if (!edges) return "default";
  const key=[...edges].sort().join("-");
  if(key==="left-top"||key==="bottom-right")return "nwse-resize";
  if(key==="right-top"||key==="bottom-left")return "nesw-resize";
  if(edges.includes("left")||edges.includes("right"))return "ew-resize";
  return "ns-resize";
}

function resizeCrop(point) {
  const resize=state.cropResize, original=resize.original, start=resize.start;
  const current=toSource(point), dx=current.x-start.x, dy=current.y-start.y, minimum=20;
  let left=original.x, top=original.y, right=original.x+original.width, bottom=original.y+original.height;
  if(resize.edges.includes("left"))left=Math.max(0,Math.min(right-minimum,original.x+dx));
  if(resize.edges.includes("right"))right=Math.min(state.sourceImage.naturalWidth,Math.max(left+minimum,original.x+original.width+dx));
  if(resize.edges.includes("top"))top=Math.max(0,Math.min(bottom-minimum,original.y+dy));
  if(resize.edges.includes("bottom"))bottom=Math.min(state.sourceImage.naturalHeight,Math.max(top+minimum,original.y+original.height+dy));
  state.crop={x:left,y:top,width:right-left,height:bottom-top};
}

function resizeRoi(point) {
  const resize=state.roiResize, original=resize.original, start=resize.start;
  const current=toSource(point), dx=current.x-start.x, dy=current.y-start.y, minimum=10;
  let left=original.x, top=original.y, right=original.x+original.width, bottom=original.y+original.height;
  if(resize.edges.includes("left"))left=Math.max(0,Math.min(right-minimum,original.x+dx));
  if(resize.edges.includes("right"))right=Math.min(state.sourceImage.naturalWidth,Math.max(left+minimum,original.x+original.width+dx));
  if(resize.edges.includes("top"))top=Math.max(0,Math.min(bottom-minimum,original.y+dy));
  if(resize.edges.includes("bottom"))bottom=Math.min(state.sourceImage.naturalHeight,Math.max(top+minimum,original.y+original.height+dy));
  state.rois[resize.index]={...state.rois[resize.index],x:left,y:top,width:right-left,height:bottom-top};
}

function canvasPoint(event) { const box=canvas.getBoundingClientRect(); return {x:(event.clientX-box.left)*(canvas.width/box.width),y:(event.clientY-box.top)*(canvas.height/box.height)}; }
canvas.addEventListener("pointerdown", (event) => {
  if (!state.sourceImage) return;
  const p=canvasPoint(event);
  if(state.mode==="crop"&&state.cropEditable){
    const edges=cropEdgeAt(p); if(!edges)return;
    canvas.setPointerCapture(event.pointerId);
    state.cropResize={edges,start:toSource(p),original:{...state.crop}}; return;
  }
  if(state.mode==="roi"){
    const hit=roiHitAt(p);
    if(hit){
      state.activeRoiIndex=hit.index;
      const roi=state.rois[hit.index], option=[...$("#roi-type").options].find(item=>item.value===roi.type);
      if(option)$("#roi-type").value=roi.type;
      if(hit.edges){
        canvas.setPointerCapture(event.pointerId);
        state.roiResize={index:hit.index,edges:hit.edges,start:toSource(p),original:{...roi}};
      }
      draw(); return;
    }
    state.activeRoiIndex=-1;
  }
  canvas.setPointerCapture(event.pointerId); state.drawing={start:p,end:p}; draw();
});
canvas.addEventListener("pointermove", (event) => {
  const point=canvasPoint(event);
  if(state.cropResize){resizeCrop(point);draw();return;}
  if(state.roiResize){resizeRoi(point);draw();return;}
  if(state.drawing){state.drawing.end=point;draw();return;}
  if(state.mode==="crop")canvas.style.cursor=cropCursor(cropEdgeAt(point));
  else if(state.mode==="roi")canvas.style.cursor=cropCursor(roiHitAt(point)?.edges)||"crosshair";
  else canvas.style.cursor="crosshair";
});
canvas.addEventListener("pointerup", () => {
  if(state.cropResize){state.cropResize=null;draw();return;}
  if(state.roiResize){state.roiResize=null;if(state.reviewMode)state.reviewLocationDirty=true;draw();return;}
  if (!state.drawing) return; const display = normalizedRect(state.drawing.start,state.drawing.end); state.drawing=null;
  if (display.width < 6 || display.height < 6) { draw(); return; }
  const rect = normalizedRect(toSource({x:display.x,y:display.y}),toSource({x:display.x+display.width,y:display.y+display.height}));
  if (state.mode === "crop") { state.crop=rect; state.cropEditable=true; $("#editor-help").textContent="拖动黄色边线或八个控制点，可继续微调裁剪范围。"; }
  if (state.mode === "redact") state.redactions.push(rect);
  if (state.mode === "roi") {
    const observation=selectedObservation();
    const roi=state.reviewMode
      ? {...rect,type:"FIELD_REVIEW_EVIDENCE",label:`字段定位：${observation?.field_label||observation?.field_name||"当前字段"}`}
      : {...rect,type:$("#roi-type").value,label:$("#roi-type").selectedOptions[0].text};
    if(state.reviewMode){state.rois=[roi];state.reviewLocationDirty=true;}else state.rois.push(roi);
    state.activeRoiIndex=state.rois.length-1;
    $("#editor-help").textContent=state.reviewMode?"当前字段定位已框选；可拖动边线微调，然后点击保存定位。":"点击任意ROI进行选择，拖动绿色边线或控制点微调。";
  }
  draw();updateReviewPositioningTools();
});
canvas.addEventListener("pointercancel", () => { state.drawing=null;state.cropResize=null;state.roiResize=null;draw(); });

$$('[data-mode]').forEach(button => button.onclick = () => {
  state.mode=button.dataset.mode; $$('[data-mode]').forEach(item=>item.classList.toggle("active",item===button));
  if(state.mode==="roi"&&state.activeRoiIndex<0&&state.rois.length)state.activeRoiIndex=state.rois.length-1;
  $("#editor-help").textContent = ({crop:state.cropEditable?"拖动黄色边线或八个控制点微调裁剪范围。":"拖动框选最终保留范围。",redact:"拖动选择需要实心遮盖的区域。",roi:state.rois.length?"点击任意ROI进行选择，拖动绿色边线或控制点微调。":"框选信息区域；建立后可拖动边线和控制点微调。"})[state.mode];
  draw();
});
$("#undo").onclick = () => { if (state.mode==="redact") state.redactions.pop(); else if(state.mode==="roi") {state.rois.pop();state.activeRoiIndex=state.rois.length-1;} else {state.crop={x:0,y:0,width:state.sourceImage.naturalWidth,height:state.sourceImage.naturalHeight};state.cropEditable=false;$("#editor-help").textContent="拖动框选最终保留范围。";} draw();updateReviewPositioningTools(); };
$("#reset-editor").onclick = () => { if (!state.sourceImage) return; state.crop={x:0,y:0,width:state.sourceImage.naturalWidth,height:state.sourceImage.naturalHeight}; state.cropEditable=false;state.cropResize=null;state.redactions=[];state.rois=[];state.activeRoiIndex=-1;state.roiResize=null;$("#editor-help").textContent="拖动框选最终保留范围。";draw();updateReviewPositioningTools(); };

$("#roi-type").addEventListener("change",()=>{
  if(state.mode!=="roi"||state.activeRoiIndex<0)return;
  const roi=state.rois[state.activeRoiIndex]; if(!roi)return;
  roi.type=$("#roi-type").value;roi.label=$("#roi-type").selectedOptions[0].text;draw();
});

function buildSanitizedBlob() {
  return new Promise((resolve,reject) => {
    const crop=state.crop; const output=document.createElement("canvas"); output.width=Math.round(crop.width);output.height=Math.round(crop.height);
    const out=output.getContext("2d",{alpha:false}); out.fillStyle="#fff";out.fillRect(0,0,output.width,output.height);
    // Enhancement remains a viewing aid while revising an already-sanitized image.
    const source=state.editingDocumentId?state.sourceImage:activeImageSource();
    out.drawImage(source,crop.x,crop.y,crop.width,crop.height,0,0,output.width,output.height);
    out.fillStyle="#111";
    for (const r of state.redactions) {
      const x=Math.max(r.x,crop.x),y=Math.max(r.y,crop.y),right=Math.min(r.x+r.width,crop.x+crop.width),bottom=Math.min(r.y+r.height,crop.y+crop.height);
      if(right>x&&bottom>y) out.fillRect(x-crop.x,y-crop.y,right-x,bottom-y);
    }
    output.toBlob(blob=>blob?resolve(blob):reject(new Error("脱敏图片生成失败")),"image/png");
  });
}

$("#save-sanitized").onclick = async () => {
  if (!state.patient || !state.sourceImage || !state.crop) return;
  const editingDocumentId=state.editingDocumentId;
  if(editingDocumentId&&editorRevisionSignature()===state.editorBaseline)return toast("图片和ROI没有变化，无需重新识别");
  const button=$("#save-sanitized"); button.disabled=true; button.textContent="正在保存…";
  const patientId=state.patient.id,item=state.rawQueue[state.activeRawIndex];
  if(item){persistActiveRawItem();item.status="SAVING";renderRawQueue();}
  let savedDocument=null;
  try {
    const blob=await buildSanitizedBlob(); const crop=state.crop;
    const regions=state.rois.map(r=>{
      const x=Math.max(r.x,crop.x),y=Math.max(r.y,crop.y),right=Math.min(r.x+r.width,crop.x+crop.width),bottom=Math.min(r.y+r.height,crop.y+crop.height);
      return {region_type:r.type,label:r.label,x:x-crop.x,y:y-crop.y,width:right-x,height:bottom-y};
    }).filter(r=>r.width>0&&r.height>0);
    const persistEnhancement=!editingDocumentId&&state.enhancementEnabled;
    const metadata={source_width:state.sourceImage.naturalWidth,source_height:state.sourceImage.naturalHeight,crop,redaction_count:state.redactions.length,client_reencoded:true,enhancement_mode:persistEnhancement?"ENHANCED":"ORIGINAL",enhancement_version:persistEnhancement?ENHANCEMENT_VERSION:null};
    const form=new FormData(); form.append("image",blob,"sanitized.png"); form.append("display_name",$("#display-name").value.trim()||suggestedDisplayName()); form.append("document_type",$("#document-type").value); form.append("sanitization",JSON.stringify(metadata)); form.append("regions",JSON.stringify(regions));
    const saveUrl=editingDocumentId?`/api/documents/${editingDocumentId}`:`/api/patients/${state.patient.id}/documents`;
    savedDocument=await api(saveUrl,{method:editingDocumentId?"PUT":"POST",body:form});
    const job={id:savedDocument.id,documentId:savedDocument.id,patientId,name:savedDocument.display_name,documentType:savedDocument.document_type,target:"FULL",status:"OCR_QUEUED",stage:"等待OCR",error:null,observationCount:null};
    state.processingJobs.push(job);renderProcessingQueue();runProcessingQueue();
    if(editingDocumentId){
      clearEditor();renderRawQueue();await refreshCurrentPatient(patientId);
      toast("脱敏图片已覆盖，旧识别结果已失效；新OCR和AI已进入后台队列");
      return;
    }
    // Release every browser reference to this raw source immediately after successful import.
    if(item){item.status="SAVED";item.file=null;item.crop=null;item.redactions=[];item.rois=[];}
    clearEditor();renderRawQueue();
    const next=state.rawQueue.findIndex((candidate,index)=>index>state.activeRawIndex&&candidate.status==="WAITING");
    const fallback=state.rawQueue.findIndex(candidate=>candidate.status==="WAITING");
    state.activeRawIndex=-1;
    const nextIndex=next>=0?next:fallback;
    if(nextIndex>=0)await loadRawItem(nextIndex);
    toast(nextIndex>=0?"脱敏图已保存，后台开始识别；已打开下一张":"全部原图已确认，后台继续识别");
  } catch(error) {
    if(item)item.status="EDITING";
    toast(`保存失败：${error.message}`);renderRawQueue();
  } finally {
    updateSaveAction();
  }
};

function rawStatusText(status){return ({WAITING:"等待处理",EDITING:"正在编辑",SAVING:"正在保存",SAVED:"已释放原图"})[status]||status;}
function processingStatusText(status){return ({OCR_QUEUED:"等待OCR",AI_QUEUED:"等待AI",OCR_RUNNING:"OCR处理中",AI_RUNNING:"AI抽取中",COMPLETED:"处理完成",FAILED:"处理失败"})[status]||status;}

function renderRawQueue(){
  const list=$("#raw-queue"),remaining=state.rawQueue.filter(item=>item.status!=="SAVED");
  $("#raw-queue-count").textContent=`${remaining.length}/${state.rawQueue.length} 张待确认`;list.innerHTML="";
  if(!state.rawQueue.length){list.innerHTML='<div class="muted-empty">尚未选择图片</div>';return;}
  state.rawQueue.forEach((item,index)=>{
    const row=document.createElement("div");row.className=`queue-row ${index===state.activeRawIndex?"active":""} ${item.status.toLowerCase()}`;
    row.innerHTML=`<button class="queue-open" ${item.status==="SAVED"||item.status==="SAVING"?"disabled":""}><span class="queue-sequence">${index+1}</span><span><strong>${escapeHtml(item.displayName)}</strong><small>${escapeHtml(item.localName)} · ${escapeHtml(documentTypeLabels[item.documentType]||item.documentType)}</small></span></button><span class="queue-status">${rawStatusText(item.status)}</span>`;
    row.querySelector(".queue-open").onclick=()=>loadRawItem(index).catch(error=>toast(error.message));list.appendChild(row);
  });
}

function renderProcessingQueue(){
  const list=$("#processing-queue"),active=state.processingJobs.filter(job=>!["COMPLETED","FAILED"].includes(job.status));
  $("#processing-count").textContent=`${active.length} 项进行中`;list.innerHTML="";
  if(!state.processingJobs.length){list.innerHTML='<div class="muted-empty">尚无后台任务</div>';return;}
  [...state.processingJobs].reverse().forEach(job=>{
    const row=document.createElement("div");row.className=`queue-row processing ${job.status.toLowerCase()}`;
    const runtime=job.status==="AI_RUNNING"||job.status==="COMPLETED"?[
      job.elapsedSeconds!==undefined?formatElapsed(job.elapsedSeconds):null,
      job.tokenRate?`${job.status==="AI_RUNNING"?"约 ":""}${Number(job.tokenRate).toFixed(1)} token/s`:null,
      job.processor&&job.processor!=="IDLE"?`${job.processor}${job.vramBytes?` ${(job.vramBytes/1073741824).toFixed(1)}GB`:""}`:null,
    ].filter(Boolean).join(" · "):"";
    row.innerHTML=`<div><strong>${escapeHtml(job.name)}</strong><small>${escapeHtml(job.stage)}${runtime?` · ${escapeHtml(runtime)}`:""}${job.observationCount!==null?` · ${job.observationCount} 个字段`:""}${job.error?` · ${escapeHtml(job.error)}`:""}</small></div><span class="queue-status">${processingStatusText(job.status)}</span>${job.status==="FAILED"?'<button class="tool retry-job">重试</button>':""}`;
    const retry=row.querySelector(".retry-job");if(retry)retry.onclick=()=>{job.status=job.failedStage==="AI"?"AI_QUEUED":"OCR_QUEUED";job.stage=job.failedStage==="AI"?"等待AI":"等待OCR";job.error=null;job.elapsedSeconds=undefined;job.tokenRate=null;job.processor=null;renderProcessingQueue();runProcessingQueue();};
    list.appendChild(row);
  });
}

function formatElapsed(seconds){
  const value=Math.max(0,Math.floor(Number(seconds)||0)),minutes=Math.floor(value/60),remaining=value%60;
  return minutes?`${minutes}分${String(remaining).padStart(2,"0")}秒`:`${remaining}秒`;
}

const aiStageLabels={
  MODEL_LOADING:"正在加载模型并处理OCR输入",THINKING:"模型正在分析病历",GENERATING_JSON:"正在生成结构化JSON",
  VALIDATING:"正在校验JSON",SAVING:"正在写入数据库",COMPLETED:"AI提取已完成",FAILED:"AI提取失败",IDLE:"等待AI",
  TNM_MODEL_LOADING:"普通字段完成，准备TNM分期",TNM_THINKING:"正在推断TNM分期",
  TNM_GENERATING_JSON:"正在生成TNM结构化结果",TNM_VALIDATING:"正在校验TNM结果",
};

async function monitorAiProgress(job){
  while(job.status==="AI_RUNNING"){
    await new Promise(resolve=>setTimeout(resolve,1200));
    if(job.status!=="AI_RUNNING")break;
    try{
      const progress=await api(`/api/documents/${job.documentId}/extract-progress`);
      job.stage=aiStageLabels[progress.stage]||job.stage;
      job.elapsedSeconds=progress.elapsed_seconds;job.tokenRate=progress.token_rate||0;
      job.processor=progress.processor;job.vramBytes=progress.vram_bytes||0;
      renderProcessingQueue();
    }catch(_){/* The extraction request remains authoritative; a missed heartbeat is harmless. */}
  }
}

async function runOcrQueue(){
  if(state.ocrWorkerActive)return;state.ocrWorkerActive=true;
  try{
    while(true){
      const job=state.processingJobs.find(candidate=>candidate.status==="OCR_QUEUED");if(!job)break;
      try{
        job.status="OCR_RUNNING";job.stage="正在OCR识别";renderProcessingQueue();
        await api(`/api/documents/${job.documentId}/ocr`,{method:"POST"});
        if(job.target==="OCR_ONLY"){
          job.status="COMPLETED";job.stage="OCR已完成";job.failedStage=null;
        }else{
          job.status="AI_QUEUED";job.stage="OCR已完成，等待AI";job.failedStage=null;
        }
      }catch(error){
        job.failedStage="OCR";job.status="FAILED";job.stage="OCR失败";job.error=error.message;
      }
      renderProcessingQueue();
      try{await refreshCurrentPatient(job.patientId);}catch(error){job.error=`结果刷新失败：${error.message}`;renderProcessingQueue();}
      runAiQueue();
    }
  }finally{state.ocrWorkerActive=false;}
}

async function runAiQueue(){
  if(state.aiWorkerActive)return;state.aiWorkerActive=true;
  try{
    while(true){
      const job=state.processingJobs.find(candidate=>candidate.status==="AI_QUEUED");if(!job)break;
      try{
        job.status="AI_RUNNING";job.stage="正在连接模型";job.failedStage=null;job.elapsedSeconds=0;job.tokenRate=0;job.processor="IDLE";job.vramBytes=0;renderProcessingQueue();
        monitorAiProgress(job);
        const fieldOnly=job.target==="FIELD_ONLY";
        const extractionPath=fieldOnly?"/extract-field":"/extract";
        const extraction=await api(`/api/documents/${job.documentId}${extractionPath}`,{
          method:"POST",
          ...(fieldOnly?{headers:{"Content-Type":"application/json"},body:JSON.stringify({
            field_name:job.fieldName,region_ids:job.regionIds||[],operator:"local-user",
          })}:{}),
        });
        job.observationCount=extraction.observation_count||0;job.status="COMPLETED";
        job.resultObservationId=extraction.observation?.id||job.observationId||null;
        job.tokenRate=extraction.performance?.token_rate||job.tokenRate;
        job.stage=fieldOnly?"当前字段优先提取已完成":(job.target==="AI_ONLY"?"AI提取已完成":"OCR与AI均已完成");
      }catch(error){
        job.failedStage="AI";job.status="FAILED";job.stage="AI失败";job.error=error.message;
      }
      renderProcessingQueue();
      try{
        await refreshCurrentPatient(job.patientId);
        if(job.target==="FIELD_ONLY"&&job.resultObservationId){
          state.selectedObservationId=job.resultObservationId;renderFieldReview();renderObservations();
        }
      }catch(error){job.error=`结果刷新失败：${error.message}`;renderProcessingQueue();}
    }
  }finally{state.aiWorkerActive=false;}
}

function runProcessingQueue(){
  runOcrQueue();
  runAiQueue();
}

function queueDocuments(documents,target){
  for(const doc of documents){
    state.processingJobs.push({
      id:`${doc.id}-${target}-${Date.now()}`,documentId:doc.id,patientId:state.patient.id,
      name:doc.display_name,documentType:doc.document_type,target,status:target==="AI_ONLY"?"AI_QUEUED":"OCR_QUEUED",
      stage:target==="AI_ONLY"?"等待AI":"等待OCR",error:null,observationCount:null,
    });
  }
  renderProcessingQueue();runProcessingQueue();
}

$("#bulk-ocr").onclick=()=>{
  if(!state.patient)return;
  const activeIds=new Set(state.processingJobs.filter(job=>!["COMPLETED","FAILED"].includes(job.status)&&job.target!=="AI_ONLY").map(job=>job.documentId));
  const documents=state.patient.documents.filter(doc=>!doc.ocr&&!activeIds.has(doc.id));
  if(!documents.length)return toast("没有需要OCR的脱敏图片");
  queueDocuments(documents,"OCR_ONLY");toast(`已加入 ${documents.length} 张OCR任务`);
};

$("#bulk-ai").onclick=()=>{
  if(!state.patient)return;
  const observed=new Set(state.patient.observations.map(observation=>observation.document_id));
  const activeIds=new Set(state.processingJobs.filter(job=>!["COMPLETED","FAILED"].includes(job.status)&&job.target!=="OCR_ONLY").map(job=>job.documentId));
  const documents=state.patient.documents.filter(doc=>doc.ocr&&doc.status!=="AI_PROCESSED"&&!observed.has(doc.id)&&!activeIds.has(doc.id));
  if(!documents.length)return toast("没有可进行AI提取的图片；请先完成OCR");
  queueDocuments(documents,"AI_ONLY");toast(`已加入 ${documents.length} 张AI提取任务`);
};

function renderDocuments() {
  const docs=state.patient?.documents||[]; $("#doc-count").textContent=`${docs.length} 张`; const list=$("#document-list");list.innerHTML="";
  if(!docs.length){list.innerHTML='<div class="muted-empty">尚无脱敏图片</div>';return;}
  const aiDocumentIds=new Set((state.patient?.observations||[]).map(observation=>observation.document_id));
  for(const doc of docs){
    const card=document.createElement("article");card.className="document-card";
    const ocrText=doc.ocr?.full_text||"";
    const hasAi=doc.status==="AI_PROCESSED"||aiDocumentIds.has(doc.id);
    card.innerHTML=`<img src="/api/documents/${doc.id}/image" alt="脱敏病历" title="在上方预览和修改"><div class="document-info"><strong title="${escapeHtml(doc.display_name)}">${escapeHtml(doc.display_name)}</strong><small>${escapeHtml(documentTypeLabels[doc.document_type]||doc.document_type)} · ${doc.regions.length} ROI · ${escapeHtml(doc.status)}</small><div class="document-actions"><button class="tool run-ocr" ${doc.ocr?"disabled":""}>${doc.ocr?"OCR已完成":"OCR识别"}</button><button class="tool run-ai" ${!doc.ocr||hasAi?"disabled":""}>${hasAi?"AI已完成":"AI提取"}</button><button class="tool delete-document">删除此图</button></div>${ocrText?`<details class="ocr-preview"><summary>查看OCR文字</summary><pre>${escapeHtml(ocrText)}</pre></details>`:""}</div>`;
    card.querySelector("img").onclick=()=>openSavedDocumentPreview(doc.id,state.selectedObservationId).catch(error=>toast(error.message));
    card.querySelector(".run-ocr").onclick=()=>{const active=state.processingJobs.some(job=>job.documentId===doc.id&&!["COMPLETED","FAILED"].includes(job.status));if(active)return toast("该图片已有后台任务");queueDocuments([doc],"OCR_ONLY");toast("OCR任务已加入后台队列");};
    card.querySelector(".run-ai").onclick=()=>{const active=state.processingJobs.some(job=>job.documentId===doc.id&&!["COMPLETED","FAILED"].includes(job.status));if(active)return toast("该图片已有后台任务");queueDocuments([doc],"AI_ONLY");toast("AI任务已加入后台队列");};
    card.querySelector(".delete-document").onclick=async()=>{if(!confirm(`确定删除“${doc.display_name}”吗？\n该图片的ROI、OCR和AI抽取字段也会删除，审计记录会保留。`))return;try{await api(`/api/documents/${doc.id}`,{method:"DELETE"});toast("脱敏图片已删除");await selectPatient(state.patient.id);}catch(error){toast(error.message);}};
    list.appendChild(card);
  }
}

function setReviewWorkspace(active,doc=null,observation=null) {
  state.reviewMode=active;
  $(".editor-toolbar").hidden=active;
  $(".import-options").hidden=active;
  $("#review-evidence-workspace").hidden=!active;
  if(!active)return;
  $("#review-location-field").textContent=observation?.field_label||observation?.field_name||"当前字段";
  const selector=$("#review-document-select"),selected=doc?.id||selector.value;
  selector.innerHTML=(state.patient?.documents||[]).map(item=>
    `<option value="${item.id}">${escapeHtml(item.display_name)} · ${escapeHtml(documentTypeLabels[item.document_type]||item.document_type)}</option>`
  ).join("");
  selector.value=selected;
  updateReviewPositioningTools();
}

function loadCurrentFieldLocation(doc,observation) {
  if(!state.reviewMode){
    state.rois=(doc.regions||[]).map(region=>({
      id:region.id,x:Number(region.x),y:Number(region.y),width:Number(region.width),height:Number(region.height),
      type:region.region_type,label:region.label,
    }));
    state.reviewLocationDirty=false;
    return;
  }
  const draft=state.reviewRegionDrafts[observation?.id]?.[doc.id];
  if(draft){
    state.rois=(draft.rois||[]).map(region=>({...region}));
    state.reviewLocationDirty=Boolean(draft.dirty);
    return;
  }
  const candidate=(observation?.candidate_values||[]).find(item=>item.id===state.reviewCandidateObservationId);
  const regionId=candidate?.region_id||observation?.region_id;
  const region=(doc.regions||[]).find(item=>item.id===regionId);
  state.rois=region?[{
    id:region.id,x:Number(region.x),y:Number(region.y),width:Number(region.width),height:Number(region.height),
    type:"FIELD_REVIEW_EVIDENCE",label:`字段定位：${observation.field_label||observation.field_name}`,
  }]:[];
  state.reviewLocationDirty=false;
}

function documentImageUrl(doc) {
  return `/api/documents/${doc.id}/image?v=${encodeURIComponent(doc.sha256||doc.id)}`;
}

function loadCachedDocumentImage(doc) {
  const url=documentImageUrl(doc);
  if(documentImageCache.has(url))return documentImageCache.get(url);
  const promise=new Promise((resolve,reject)=>{
    const image=new Image();
    image.onload=()=>resolve(image);
    image.onerror=()=>{documentImageCache.delete(url);reject(new Error(`无法打开 ${doc.display_name}`));};
    image.src=url;
  });
  documentImageCache.set(url,promise);
  while(documentImageCache.size>DOCUMENT_IMAGE_CACHE_LIMIT){
    documentImageCache.delete(documentImageCache.keys().next().value);
  }
  return promise;
}

function preloadAdjacentReviewDocuments(documentId) {
  if(!state.reviewMode)return;
  const documents=state.patient?.documents||[],index=documents.findIndex(item=>item.id===documentId);
  for(const adjacentIndex of [index-1,index+1]){
    const adjacent=documents[adjacentIndex];
    if(adjacent)loadCachedDocumentImage(adjacent).catch(()=>{});
  }
}

function queuePriorityFieldExtraction(document,observation,regionIds){
  const duplicate=state.processingJobs.some(job=>job.target==="FIELD_ONLY"&&job.documentId===document.id&&job.fieldName===observation.field_name&&!['COMPLETED','FAILED'].includes(job.status));
  if(duplicate)return toast("当前字段已经在优先队列中");
  state.processingJobs.unshift({
    id:`${document.id}-FIELD_ONLY-${Date.now()}`,documentId:document.id,patientId:state.patient.id,
    name:`${document.display_name} · ${observation.field_label||observation.field_name}`,
    documentType:document.document_type,target:"FIELD_ONLY",fieldName:observation.field_name,
    observationId:observation.id,regionIds,status:"AI_QUEUED",stage:"优先等待AI",error:null,observationCount:null,
  });
  renderProcessingQueue();runProcessingQueue();
  toast("当前字段已插入AI优先队列；正在运行的任务完成后将首先处理");
}

function captureCurrentReviewDraft(){
  const observation=selectedObservation();
  if(!observation)return;
  state.reviewFieldDrafts[observation.id]={
    value:$("#review-current-value")?.value??observation.current_value??"",
    note:$("#review-note")?.value??"",
  };
}

function captureCurrentRegionDraft(){
  const observation=selectedObservation();
  if(!state.reviewMode||!observation||!state.editingDocumentId||!state.sourceImage)return;
  state.reviewRegionDrafts[observation.id]??={};
  state.reviewRegionDrafts[observation.id][state.editingDocumentId]={
    rois:state.rois.map(region=>({...region})),dirty:state.reviewLocationDirty,
  };
}

function isDerivedReviewField(fieldName){
  const value=String(fieldName||"").trim();
  return [
    "clinical_t_component","clinical_n_component","clinical_m_component",
    "pathological_t_component","pathological_n_component","pathological_m_component",
  ].includes(value)||/_dim[123]_mm$/.test(value);
}

function updateReviewPositioningTools(){
  const tools=$("#review-positioning-tools"),observation=selectedObservation(),docs=state.patient?.documents||[];
  if(!tools)return;
  tools.hidden=!(state.reviewMode&&observation&&docs.length);
  if(tools.hidden)return;
  const select=$("#review-document-select");
  const activeId=state.editingDocumentId||observation.document_id||docs[0].id;
  if(docs.some(doc=>doc.id===activeId))select.value=activeId;
  const index=docs.findIndex(doc=>doc.id===select.value);
  $("#review-document-previous").disabled=index<=0;
  $("#review-document-next").disabled=index<0||index>=docs.length-1;
  const hasImage=Boolean(state.editingDocumentId&&state.sourceImage);
  const activeDocument=docs.find(doc=>doc.id===state.editingDocumentId);
  const derived=isDerivedReviewField(observation.field_name);
  $("#delete-review-position").disabled=!hasImage||state.activeRoiIndex<0||!state.rois[state.activeRoiIndex];
  $("#reextract-review-field").disabled=derived||!hasImage||!activeDocument?.ocr||state.activeRoiIndex<0||!state.rois[state.activeRoiIndex];
  $("#review-positioning-status").textContent=derived
    ? "这是自动整理的只读字段，不能单独重新提取；请找到并重新提取对应的完整TNM或肿块尺寸主字段。"
    : hasImage
    ? `当前复核字段：${observation.field_label||observation.field_name}；可切换图片，已画 ${state.rois.length} 个文本定位。`
    : "请选择患者资料图片，再使用“文本定位”框选证据文字。";
}

async function openSavedDocumentPreview(documentId,observationId=null) {
  captureCurrentReviewDraft();captureCurrentRegionDraft();
  const doc=(state.patient?.documents||[]).find(item=>item.id===documentId);
  if(!doc)throw new Error("找不到该记录对应的脱敏图片");
  const observation=(state.patient?.observations||[]).find(item=>item.id===observationId)||selectedObservation();
  if(observationId===null){state.selectedObservationId=null;renderFieldReview();renderObservations();}
  if(state.editingDocumentId===doc.id&&state.sourceImage){
    state.reviewDocumentId=doc.id;state.reviewObservationId=observationId;
    setReviewWorkspace(observationId!==null,doc,observation);
    loadCurrentFieldLocation(doc,observation);
    state.mode=observationId!==null?"roi":"crop";state.activeRoiIndex=state.rois.length-1;
    $$(".observation").forEach(row=>row.classList.toggle("previewing",row.dataset.observationId===observationId));
    draw();
    preloadAdjacentReviewDocuments(doc.id);
    updateReviewPositioningTools();
    if(observationId!==null)$("#review-evidence-workspace").scrollIntoView({behavior:"smooth",block:"start"});
    return;
  }
  const activeRaw=state.rawQueue[state.activeRawIndex];
  persistActiveRawItem();
  if(activeRaw?.status==="EDITING")activeRaw.status="WAITING";
  state.activeRawIndex=-1;state.rawLoadToken+=1;clearEditor();renderRawQueue();
  const token=state.rawLoadToken,image=await loadCachedDocumentImage(doc);
  if(token!==state.rawLoadToken)return;
  state.sourceImage=image;state.enhancedImage=state.enhancementEnabled?createEnhancedImage(image):null;
  state.mode=observationId!==null?"roi":"crop";state.viewZoom=1;state.reviewDocumentId=doc.id;state.reviewObservationId=observationId;
  state.editingDocumentId=doc.id;
  state.crop={x:0,y:0,width:image.naturalWidth,height:image.naturalHeight};state.cropEditable=false;
  state.redactions=[];
  setReviewWorkspace(observationId!==null,doc,observation);
  loadCurrentFieldLocation(doc,observation);
  state.activeRoiIndex=state.rois.length-1;state.drawing=null;
  $("#document-type").value=doc.document_type;updateRoiTypeOptions();$("#display-name").value=doc.display_name;
  state.editorBaseline=editorRevisionSignature();
  $$('[data-mode]').forEach(button=>button.classList.toggle("active",button.dataset.mode===state.mode));
  setMetadataControlsEnabled(true);enableEditor(true);fitCanvas();draw();$("#canvas-placeholder").hidden=true;
  $("#editor-help").textContent=observationId!==null
    ?`${doc.display_name}：只能框选“${observation?.field_label||observation?.field_name||"当前字段"}”的证据位置。`
    :`${doc.display_name}：可继续裁剪、增加遮盖或调整ROI；发生修改后才能覆盖并重新识别。`;
  $$(".observation").forEach(row=>row.classList.toggle("previewing",row.dataset.observationId===observationId));
  preloadAdjacentReviewDocuments(doc.id);
  updateReviewPositioningTools();
  (observationId!==null?$("#review-evidence-workspace"):$(".import-options")).scrollIntoView({behavior:"smooth",block:"start"});
}

async function switchReviewDocument(documentId){
  const observation=selectedObservation();
  if(!observation||!documentId)return;
  await openSavedDocumentPreview(documentId,observation.id);
}

function clearReviewRegionDraft(observationId,documentId){
  if(!state.reviewRegionDrafts[observationId])return;
  delete state.reviewRegionDrafts[observationId][documentId];
  if(!Object.keys(state.reviewRegionDrafts[observationId]).length)delete state.reviewRegionDrafts[observationId];
}

async function saveCurrentReviewLocation(requireActive=true){
  const observation=selectedObservation();
  const document=(state.patient?.documents||[]).find(item=>item.id===state.editingDocumentId);
  const roi=state.rois[0];
  if(!observation||!document)throw new Error("请先选择复核字段和资料图片");
  if(requireActive&&!roi)throw new Error("请先使用“文本定位”框选当前字段的证据文字");
  if(!roi)return {document,regionIds:[]};
  const candidate=(observation.candidate_values||[]).find(item=>item.id===state.reviewCandidateObservationId);
  const targetId=candidate?.id||observation.id;
  state.reviewCandidateObservationId=targetId;
  const replacedRegionIds=new Set([observation.region_id,candidate?.region_id].filter(Boolean));
  const result=await api(`/api/observations/${targetId}/evidence-location`,{
    method:"PUT",headers:{"Content-Type":"application/json"},
    body:JSON.stringify({document_id:document.id,x:roi.x,y:roi.y,width:roi.width,height:roi.height,operator:"local-user"}),
  });
  for(const doc of state.patient.documents||[])doc.regions=(doc.regions||[]).filter(item=>!replacedRegionIds.has(item.id));
  document.regions.push(result.region);
  observation.document_id=result.document_id;observation.region_id=result.region.id;observation.evidence_status=result.evidence_status;
  if(candidate){candidate.document_id=result.document_id;candidate.region_id=result.region.id;}
  state.rois=[{...result.region,type:result.region.region_type}];state.activeRoiIndex=0;
  state.reviewLocationDirty=false;
  clearReviewRegionDraft(observation.id,document.id);
  state.editorBaseline=editorRevisionSignature();
  draw();updateReviewPositioningTools();renderDocuments();
  return {document,regionIds:[result.region.id],result};
}

$("#review-document-previous").onclick=()=>{
  const docs=state.patient?.documents||[],index=docs.findIndex(doc=>doc.id===$("#review-document-select").value);
  if(index>0)switchReviewDocument(docs[index-1].id).catch(error=>toast(error.message));
};
$("#review-document-next").onclick=()=>{
  const docs=state.patient?.documents||[],index=docs.findIndex(doc=>doc.id===$("#review-document-select").value);
  if(index>=0&&index<docs.length-1)switchReviewDocument(docs[index+1].id).catch(error=>toast(error.message));
};
$("#delete-review-position").onclick=async()=>{
  const observation=selectedObservation();if(!observation)return;
  const candidate=(observation.candidate_values||[]).find(item=>item.id===state.reviewCandidateObservationId);
  const targetId=candidate?.id||observation.id;
  const removedRegionIds=new Set([observation.region_id,candidate?.region_id].filter(Boolean));
  try{
    if(!observation.virtual_missing&&removedRegionIds.size){
      await api(`/api/observations/${targetId}/evidence-location`,{method:"DELETE"});
    }
    for(const doc of state.patient.documents||[])doc.regions=(doc.regions||[]).filter(item=>!removedRegionIds.has(item.id));
    if(removedRegionIds.has(observation.region_id))observation.region_id=null;
    if(candidate&&removedRegionIds.has(candidate.region_id))candidate.region_id=null;
    observation.evidence_status="REJECTED";state.rois=[];state.activeRoiIndex=-1;state.reviewLocationDirty=false;
    clearReviewRegionDraft(observation.id,state.editingDocumentId);draw();updateReviewPositioningTools();renderDocuments();
    toast("错误文本定位已删除；原OCR和字段结果保持不变");
  }catch(error){toast(error.message);}
};
$("#reextract-review-field").onclick=async()=>{
  let observation=selectedObservation();
  if(!observation)return;
  if(isDerivedReviewField(observation.field_name))return toast("自动整理字段不能单独重新提取，请重新提取对应的完整主字段");
  captureCurrentReviewDraft();
  const button=$("#reextract-review-field");button.disabled=true;
  try{
    observation=await materializeVirtualObservation(
      observation,$("#review-current-value").value.trim(),"人工框选定位后重新提取"
    );
    const {document,regionIds}=await saveCurrentReviewLocation();
    if(!document.ocr)throw new Error("当前图片尚未完成整页OCR，请先运行OCR识别");
    queuePriorityFieldExtraction(document,observation,regionIds);
  }catch(error){toast(error.message);}
  finally{updateReviewPositioningTools();}
};

function selectedObservation() {
  return (state.patient?.observations||[]).find(item=>item.id===state.selectedObservationId)||null;
}

function fieldOrderedObservations() {
  return [...(state.patient?.observations||[])]
    .filter(item=>item.status!=="SUPERSEDED")
    .filter(item=>!String(item.field_name||"").startsWith("additional_malignant_lesion:"))
    .sort((left,right)=>{
    const reviewGroup=Number(left.status==="VERIFIED")-Number(right.status==="VERIFIED");
    if(reviewGroup!==0)return reviewGroup;
    const fieldOrder=(Number(left.field_order) || 0)-(Number(right.field_order) || 0);
    if(fieldOrder!==0)return fieldOrder;
    return String(left.created_at||"").localeCompare(String(right.created_at||""))||String(left.id).localeCompare(String(right.id));
    });
}

function orderedObservations() {
  const documentOrder=new Map((state.patient?.documents||[]).map((doc,index)=>[doc.id,index]));
  return fieldOrderedObservations().sort((left,right)=>{
    const reviewGroup=Number(left.status==="VERIFIED")-Number(right.status==="VERIFIED");
    if(reviewGroup!==0)return reviewGroup;
    const sourceOrder=(documentOrder.get(left.document_id)??Number.MAX_SAFE_INTEGER)
      -(documentOrder.get(right.document_id)??Number.MAX_SAFE_INTEGER);
    if(sourceOrder!==0)return sourceOrder;
    return (Number(left.field_order)||0)-(Number(right.field_order)||0);
  });
}

function renderReviewChoices(observation) {
  const container=$("#review-choice-options"),valueField=$("#review-current-value"),valueLabel=$("#review-current-value-label");
  const options=Array.isArray(observation.field_options)?observation.field_options:[];
  container.innerHTML="";
  const useChoices=options.length>0;
  container.hidden=!useChoices;
  valueLabel.hidden=useChoices;
  if(!useChoices)return;
  for(const option of options){
    const button=document.createElement("button");
    button.type="button";button.className="review-choice-option";
    button.textContent=option.label;button.dataset.value=option.value;
    button.classList.toggle("active",String(valueField.value)===String(option.value));
    button.onclick=()=>{
      valueField.value=option.value;
      container.querySelectorAll(".review-choice-option").forEach(item=>item.classList.toggle("active",item===button));
      captureCurrentReviewDraft();
      renderConditionalFollowups(observation);
    };
    container.appendChild(button);
  }
}

function normalizedDependencyValue(value) {
  const text=String(value??"").trim().toUpperCase();
  return ({"是":"YES","否":"NO","阳性":"POSITIVE","阴性":"NEGATIVE","不确定":"UNKNOWN"})[text]||text;
}

function reviewDependencySatisfied(value,dependency) {
  if(!dependency)return false;
  const normalized=normalizedDependencyValue(value);
  if(Object.prototype.hasOwnProperty.call(dependency,"equals")){
    return normalized===normalizedDependencyValue(dependency.equals);
  }
  if(Object.prototype.hasOwnProperty.call(dependency,"contains")){
    const expected=normalizedDependencyValue(dependency.contains);
    return String(value??"").split(/[；;，,|]+/).map(normalizedDependencyValue).includes(expected);
  }
  return true;
}

function conditionalFollowupDrafts() {
  const container=$("#review-conditional-followups");
  if(!container||container.hidden)return [];
  return [...container.querySelectorAll("[data-followup-field]")].map(input=>({
    field_name:input.dataset.followupField,
    value:String(input.value??"").trim(),
    initial_value:String(input.dataset.initialValue??"").trim(),
  }));
}

function renderConditionalFollowups(observation) {
  const container=$("#review-conditional-followups");
  if(!container)return;
  const parentValue=$("#review-current-value")?.value??observation?.current_value??"";
  const definitions=(observation?.conditional_followups||[]).filter(item=>reviewDependencySatisfied(parentValue,item.depends_on));
  container.innerHTML="";
  container.hidden=!definitions.length;
  if(!definitions.length)return;

  const heading=document.createElement("div");
  heading.className="review-conditional-heading";
  heading.innerHTML="<strong>请继续填写后续问题</strong><small>父项改变后新适用的内容，可在这里直接填写；确实未知时可以留空。</small>";
  container.appendChild(heading);
  for(const definition of definitions){
    const existing=(state.patient?.observations||[]).find(item=>item.field_name===definition.field_name);
    const label=document.createElement("label");
    label.textContent=definition.field_label||definition.field_name;
    let input;
    const options=Array.isArray(definition.field_options)?definition.field_options:[];
    if(options.length){
      input=document.createElement("select");
      input.appendChild(new Option("请选择 / 未填写",""));
      for(const option of options)input.appendChild(new Option(option.label,option.value));
    }else{
      input=document.createElement("input");
      input.type=definition.field_type==="integer"||definition.field_type==="number"?"number":"text";
      input.placeholder=String(definition.field_label||"").includes("补充填空")?"请输入具体数值、百分比或说明":"请输入后续内容";
    }
    input.dataset.followupField=definition.field_name;
    input.value=existing?.current_value??"";
    input.dataset.initialValue=input.value;
    label.appendChild(input);
    container.appendChild(label);
  }
}

async function persistConditionalFollowups(drafts,parentObservation) {
  let saved=0;
  for(const draft of drafts){
    if(draft.value===draft.initial_value)continue;
    const existing=(state.patient?.observations||[]).find(item=>item.field_name===draft.field_name);
    if(existing&&!existing.virtual_missing){
      await api(`/api/observations/${existing.id}`,{
        method:"PATCH",headers:{"Content-Type":"application/json"},
        body:JSON.stringify({value:draft.value,operator:"local-user",reason:`${parentObservation.field_label||parentObservation.field_name}改变后补充后续问题`}),
      });
      saved++;
    }else if(draft.value){
      await api(`/api/patients/${state.patient.id}/observations`,{
        method:"POST",headers:{"Content-Type":"application/json"},
        body:JSON.stringify({field_name:draft.field_name,value:draft.value,raw_text:"人工复核父项后补充",confidence:"LOW",source_mode:"RECORDED",operator:"local-user",reason:`${parentObservation.field_label||parentObservation.field_name}改变后补充后续问题`}),
      });
      saved++;
    }
  }
  return saved;
}

function renderFieldReview() {
  const panel=$("#field-review-panel"),observation=selectedObservation();
  const completePanel=$("#review-complete-panel");
  if(!state.patient||!observation){
    panel.hidden=true;
    const observations=(state.patient?.observations||[]).filter(item=>item.status!=="SUPERSEDED");
    completePanel.hidden=!(state.patient&&observations.length&&observations.every(item=>item.status==="VERIFIED"));
    renderConflictEvidence(null);
    updateReviewPositioningTools();
    return;
  }
  completePanel.hidden=true;
  const observations=orderedObservations(),index=observations.findIndex(item=>item.id===observation.id);
  const sameReviewGroup=observations.filter(item=>(item.status==="VERIFIED")===(observation.status==="VERIFIED"));
  const reviewGroupIndex=sameReviewGroup.findIndex(item=>item.id===observation.id);
  panel.hidden=false;
  $("#review-field-name").textContent=observation.field_label||observation.field_name;
  $("#review-field-key").textContent=`字段名：${observation.field_name}`;
  $("#review-ai-value").value=observation.ai_value??"";
  const basisBox=$("#review-inference-basis"),basis=Array.isArray(observation.inference_basis)?observation.inference_basis:[];
  const showTnmBasis=["clinical_stage","pathological_stage"].includes(observation.field_name)&&basis.length>0;
  basisBox.hidden=!showTnmBasis;
  basisBox.innerHTML=showTnmBasis?`<strong>TNM评估依据</strong>${basis.map(item=>`<div><b>${escapeHtml(item.component||"证据")}</b><span>${escapeHtml(item.fact||"")}</span><small>${escapeHtml(item.source_text||"")}</small></div>`).join("")}`:"";
  const draft=state.reviewFieldDrafts[observation.id];
  $("#review-current-value").value=draft?.value??observation.current_value??"";
  renderReviewChoices(observation);
  renderConditionalFollowups(observation);
  $("#review-note").value=draft?.note??"";
  const evidence=observation.raw_text?` · 证据：${observation.raw_text}`:"";
  const candidates=(observation.candidate_values||[]).filter(item=>item.valid).map(item=>`${item.value}（${item.source}）`).join("；");
  const conflict=observation.candidate_conflict?` · 存在候选冲突：${candidates}`:"";
  const rejected=observation.discarded_candidate_count?` · 已排除 ${observation.discarded_candidate_count} 条非法候选`:"";
  const invalidOnly=observation.invalid_only?" · 当前值不符合问卷值域，请人工修改":"";
  $("#review-field-meta").textContent=`${statusText(observation.status)} · ${observation.confidence}${evidence}${conflict}${rejected}${invalidOnly}`;
  $("#review-position").textContent=observation.status==="VERIFIED"
    ? `已审核 ${reviewGroupIndex+1} / ${sameReviewGroup.length}`
    : `待审核 ${reviewGroupIndex+1} / ${sameReviewGroup.length}`;
  $("#previous-field").disabled=index<=0;
  $("#next-field").disabled=index<0||index>=observations.length-1;
  const verified=observation.status==="VERIFIED";
  $("#review-current-value").disabled=false;
  $("#review-note").disabled=false;
  $("#save-field-edit").disabled=false;
  $("#verify-field").disabled=false;
  $("#verify-field").textContent=verified?"再次确认":"人工确认";
  renderConflictEvidence(observation);
  updateReviewPositioningTools();
}

function renderConflictEvidence(observation) {
  const gallery=$("#conflict-evidence-gallery"),container=$("#conflict-evidence-images");
  container.innerHTML="";
  if(!observation?.candidate_conflict){gallery.hidden=true;return;}
  const candidates=[],seen=new Set();
  for(const candidate of observation.candidate_values||[]){
    if(!candidate.valid||!candidate.document_id||seen.has(candidate.document_id))continue;
    seen.add(candidate.document_id);candidates.push(candidate);
  }
  if(candidates.length<2){gallery.hidden=true;return;}
  gallery.hidden=false;
  for(const [candidateIndex,candidate] of candidates.entries()){
    const button=document.createElement("button");button.type="button";button.className="conflict-evidence-card";
    button.dataset.candidateIndex=String(candidateIndex+1);
    button.classList.toggle("active",candidate.id===(state.reviewCandidateObservationId||observation.id));
    const shortcut=candidateIndex<9?`Ctrl+${candidateIndex+1} · `:"",confidence=candidate.confidence?` · ${candidate.confidence}`:"";
    button.innerHTML=`<img src="/api/documents/${encodeURIComponent(candidate.document_id)}/image" alt="${escapeHtml(candidate.source)}"><span><strong>${escapeHtml(candidate.value)}</strong><small>${escapeHtml(shortcut+candidate.source+confidence)}</small>${candidate.raw_text?`<em>${escapeHtml(candidate.raw_text)}</em>`:""}</span>`;
    button.onclick=()=>{
      state.reviewCandidateObservationId=candidate.id;
      $("#review-current-value").value=candidate.value??"";
      renderReviewChoices(observation);
      container.querySelectorAll(".conflict-evidence-card").forEach(item=>item.classList.toggle("active",item===button));
      openSavedDocumentPreview(candidate.document_id,observation.id).catch(error=>toast(error.message));
    };
    container.appendChild(button);
  }
}

async function chooseObservation(observation) {
  captureCurrentReviewDraft();
  state.selectedObservationId=observation.id;
  state.reviewCandidateObservationId=observation.id;
  renderFieldReview();renderObservations();
  if(observation.document_id){
    await openSavedDocumentPreview(observation.document_id,observation.id);
  }else{
    clearEditor();
    updateReviewPositioningTools();
  }
}

async function navigateObservation(offset) {
  const observations=orderedObservations(),current=selectedObservation();
  if(!current)return;
  const index=observations.findIndex(item=>item.id===current.id),target=observations[index+offset];
  if(target)await chooseObservation(target);
}

$("#previous-field").onclick=()=>navigateObservation(-1).catch(error=>toast(error.message));
$("#next-field").onclick=()=>navigateObservation(1).catch(error=>toast(error.message));
$("#review-current-value").addEventListener("input",()=>{
  captureCurrentReviewDraft();
  renderConditionalFollowups(selectedObservation());
});
$("#review-note").addEventListener("input",captureCurrentReviewDraft);

$("#review-document-select").onchange=()=>{
  const observation=selectedObservation();if(!observation)return;
  openSavedDocumentPreview($("#review-document-select").value,observation.id).catch(error=>toast(error.message));
};

$("#review-draw-location").onclick=()=>{
  if(!state.reviewMode||!state.sourceImage)return;
  state.mode="roi";state.rois=[];state.activeRoiIndex=-1;state.drawing=null;state.reviewLocationDirty=true;
  $("#editor-help").textContent="请在图片上拖动框选当前字段的唯一证据位置。";draw();
};

$("#review-clear-location").onclick=()=>{
  if(!state.reviewMode)return;
  state.rois=[];state.activeRoiIndex=-1;state.drawing=null;state.reviewLocationDirty=true;
  $("#editor-help").textContent="当前字段定位已清除；可重新框选。";draw();updateReviewPositioningTools();
};

function nextUnverifiedObservation(afterId) {
  const observations=orderedObservations();
  if(!observations.length)return null;
  const found=observations.findIndex(item=>item.id===afterId);
  if(found<0)return observations.find(item=>item.status!=="VERIFIED")||null;
  const start=found;
  for(let offset=1;offset<=observations.length;offset++){
    const candidate=observations[(start+offset)%observations.length];
    if(candidate.status!=="VERIFIED")return candidate;
  }
  return null;
}

async function persistReviewObservationValue(observation,value,reason) {
  if(observation.virtual_missing){
    return api(`/api/patients/${state.patient.id}/observations`,{
      method:"POST",headers:{"Content-Type":"application/json"},
      body:JSON.stringify({
        field_name:observation.field_name,
        value,
        raw_text:value?"人工手动补充":"人工明确留空",
        confidence:"LOW",
        source_mode:"RECORDED",
        operator:"local-user",
        reason,
      }),
    });
  }
  return api(`/api/observations/${observation.id}`,{
    method:"PATCH",headers:{"Content-Type":"application/json"},
    body:JSON.stringify({value,reason,operator:"local-user"}),
  });
}

async function materializeVirtualObservation(observation,value,reason){
  if(!observation.virtual_missing)return observation;
  const created=await persistReviewObservationValue(observation,value,reason);
  const virtualId=observation.id;
  await refreshCurrentPatient(state.patient.id);
  const materialized=(state.patient.observations||[]).find(item=>item.id===created.id)
    ||(state.patient.observations||[]).find(item=>item.field_name===observation.field_name&&!item.virtual_missing);
  if(!materialized)throw new Error("人工填写字段已保存，但刷新后未找到该字段");
  state.selectedObservationId=materialized.id;state.reviewCandidateObservationId=materialized.id;
  if(state.reviewFieldDrafts[virtualId]){
    state.reviewFieldDrafts[materialized.id]=state.reviewFieldDrafts[virtualId];
    delete state.reviewFieldDrafts[virtualId];
  }
  return materialized;
}

$("#save-field-edit").onclick=async()=>{
  const observation=selectedObservation();if(!observation)return;
  const value=$("#review-current-value").value.trim(),followups=conditionalFollowupDrafts();
  const parentChanged=value!==(observation.current_value??"");
  const followupChanged=followups.some(item=>item.value!==item.initial_value);
  if(!parentChanged&&!followupChanged)return toast("字段值没有变化");
  const reason=$("#review-note").value.trim()||"人工复核修正";
  try{
    if(parentChanged){
      await persistReviewObservationValue(observation,value,reason);
    }
    const followupSaved=await persistConditionalFollowups(followups,observation);
    delete state.reviewFieldDrafts[observation.id];
    await refreshCurrentPatient(state.patient.id);
    toast(followupSaved?`字段修改及 ${followupSaved} 个后续答案已保存`:"字段修改已保存");
  }catch(error){toast(error.message);}
};

$("#verify-field").onclick=async()=>{
  let observation=selectedObservation();if(!observation)return;
  const originalObservationId=observation.id;
  const value=$("#review-current-value").value.trim(),note=$("#review-note").value.trim();
  const followups=conditionalFollowupDrafts();
  const button=$("#verify-field");button.disabled=true;
  try{
    observation=await materializeVirtualObservation(
      observation,value,note||(value?"人工复核填写":"人工确认留空")
    );
    const followupSaved=await persistConditionalFollowups(followups,observation);
    const roi=state.reviewLocationDirty?state.rois[0]:null;
    const evidence_location=roi&&state.reviewDocumentId
      ?{document_id:state.reviewDocumentId,x:roi.x,y:roi.y,width:roi.width,height:roi.height,operator:"local-user"}
      :null;
    const result=await api(`/api/observations/${observation.id}/verify`,{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({value,candidate_id:state.reviewCandidateObservationId,evidence_location,operator:"local-user",note:note||null})});
    applyObservationReviewResult(result);
    delete state.reviewFieldDrafts[originalObservationId];delete state.reviewFieldDrafts[observation.id];
    let next=nextUnverifiedObservation(result.id);
    if(followupSaved){
      await refreshCurrentPatient(state.patient.id);
      next=nextUnverifiedObservation(result.id);
    }
    if(next){await chooseObservation(next);toast(followupSaved?`字段已确认，并保存 ${followupSaved} 个后续答案`:"字段已确认，已进入下一条待审核记录");}
    else{
      await refreshCurrentPatient(state.patient.id);
      state.selectedObservationId=null;clearEditor();renderFieldReview();renderObservations();
      $("#review-complete-panel").scrollIntoView({behavior:"smooth",block:"start"});
      toast("当前患者全部字段已处理完毕");
    }
  }catch(error){toast(error.message);}
  finally{button.disabled=false;}
};

document.addEventListener("keydown",event=>{
  if(!state.reviewMode||!selectedObservation())return;
  if(event.ctrlKey&&!event.altKey&&!event.shiftKey&&event.key==="Enter"){
    event.preventDefault();$("#verify-field").click();return;
  }
  if(event.ctrlKey&&!event.altKey&&!event.shiftKey&&event.key.toLowerCase()==="s"){
    event.preventDefault();$("#save-field-edit").click();return;
  }
  if(event.ctrlKey&&!event.altKey&&!event.shiftKey&&/^[1-9]$/.test(event.key)){
    const candidate=$("#conflict-evidence-images").querySelector(`[data-candidate-index="${event.key}"]`);
    if(candidate){event.preventDefault();candidate.click();}
  }
});

async function showPatientReview() {
  if(!state.patient)return;
  const dataset=await api("/api/data-preview?verified_only=false");
  const row=dataset.rows.find(item=>item.patient_id===state.patient.id);
  if(!row)throw new Error("未找到当前患者数据");
  $("#patient-review-title").textContent=`患者 ${state.patient.patient_code} · 全部问题与答案`;
  const body=$("#patient-review-body");body.innerHTML="";
  for(const column of dataset.columns){
    const tr=document.createElement("tr"),value=row.values[column.key]??"",status=row.statuses[column.key]||"EMPTY";
    tr.innerHTML=`<th><strong>${escapeHtml(column.label)}</strong><small>${escapeHtml(column.key)}</small></th><td>${value===""?'<span class="empty-answer">未填写</span>':escapeHtml(value)}</td><td>${escapeHtml(statusText(status))}</td>`;
    body.appendChild(tr);
  }
  $("#patient-review-dialog").showModal();
}

$("#review-patient-summary").onclick=()=>showPatientReview().catch(error=>toast(error.message));
$("#close-patient-review").onclick=()=>$("#patient-review-dialog").close();
$("#quick-add-patient").onclick=()=>{
  clearRawQueue();state.patient=null;state.selectedObservationId=null;
  $("#patient-workspace").hidden=true;$("#empty-state").hidden=false;updatePatientSidebar();
  loadPatients().then(()=>{$("#patient-code").focus();}).catch(error=>toast(error.message));
};

function renderObservations() {
  const observations=fieldOrderedObservations();$("#observation-count").textContent=`${observations.length} 项`;const list=$("#observation-list");list.innerHTML="";
  if(!observations.length){list.innerHTML='<div class="muted-empty">OCR / AI 抽取接入后，字段会在这里进入人工审核。</div>';return;}
  let currentReviewGroup=null;
  for(const obs of observations){
    const reviewGroup=obs.status==="VERIFIED"?"VERIFIED":"PENDING";
    if(reviewGroup!==currentReviewGroup){
      currentReviewGroup=reviewGroup;
      const heading=document.createElement("div");heading.className=`observation-group ${reviewGroup.toLowerCase()}`;
      const count=observations.filter(item=>(item.status==="VERIFIED"?"VERIFIED":"PENDING")===reviewGroup).length;
      heading.innerHTML=`<strong>${reviewGroup==="VERIFIED"?"已人工审核":"待人工审核"}</strong><span>${count} 项</span>`;
      list.appendChild(heading);
    }
    const row=document.createElement("div");row.className=`observation${state.selectedObservationId===obs.id?" previewing":""}`;
    row.dataset.observationId=obs.id;row.tabIndex=0;row.title=obs.document_id?"点击查看对应图片":"点击审核该字段";
    const merged=obs.candidate_count>1?` · 已合并 ${obs.candidate_count} 条候选`:"";
    const conflict=obs.candidate_conflict?" · 候选冲突待确认":"";
    const displayedValue=obs.current_value===""
      ?(obs.status==="VERIFIED"?"已确认留空":"待人工填写或确认留空")
      :obs.current_value;
    row.innerHTML=`<div><strong>${escapeHtml(obs.field_label||obs.field_name)}：${escapeHtml(displayedValue)}</strong><small class="observation-field-key">字段名：${escapeHtml(obs.field_name)}</small><small>问卷第 ${Number(obs.field_order)+1} 项 · ${statusText(obs.status)} · ${escapeHtml(obs.confidence)} · AI原值 ${escapeHtml(obs.ai_value)}${merged}${conflict}</small></div><span class="review-record-hint">审核 ›</span>`;
    row.onclick=()=>chooseObservation(obs).catch(error=>toast(error.message));
    row.onkeydown=event=>{if(event.key==="Enter"||event.key===" "){event.preventDefault();row.click();}};
    list.appendChild(row);
  }
  renderFieldReview();
}

$("#refresh-models").onclick = async (event) => {
  const button=event?.currentTarget||$("#refresh-models");
  if(button.disabled)return;
  const localBox=$("#local-models"),installedBox=$("#installed-models"),refreshStatus=$("#model-refresh-status");
  const startedAt=performance.now();
  button.disabled=true;button.classList.add("is-loading");button.setAttribute("aria-busy","true");
  button.textContent="正在查询";
  localBox.textContent="正在扫描本地 GGUF…";installedBox.textContent="正在查询可用对话模型…";
  refreshStatus.textContent="正在连接 Ollama · 0.0 秒";
  const ticker=setInterval(()=>{refreshStatus.textContent=`正在查询可用模型 · ${((performance.now()-startedAt)/1000).toFixed(1)} 秒`;},100);
  let installedCount=0,hadError=false;
  const [localResult,installedResult]=await Promise.allSettled([
    api("/api/models/local-files"),
    api("/api/models/installed"),
  ]);
  try {
    if(localResult.status!=="fulfilled")throw localResult.reason;
    const local=localResult.value;localBox.innerHTML=local.length?"":"未发现 GGUF";
    for(const file of local){
      const row=document.createElement("div");row.className="model-row";const suggested=file.filename.replace(/\.gguf$/i,"").replace(/[^A-Za-z0-9._-]/g,"-");
      if(file.imported){
        row.innerHTML=`<span>${escapeHtml(file.filename)}<small> ${(file.size/1073741824).toFixed(2)} GB · ${escapeHtml(file.model_names.join("、"))}</small></span><span class="model-imported">已导入</span>`;
      }else{
        row.innerHTML=`<span>${escapeHtml(file.filename)}<small> ${(file.size/1073741824).toFixed(2)} GB</small></span><span><input value="${escapeHtml(suggested)}" aria-label="Ollama模型名"><button class="tool">导入</button></span>`;
        row.querySelector("button").onclick=async()=>{const modelName=row.querySelector("input").value.trim();if(!modelName)return;try{await api("/api/models/import",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({filename:file.filename,model_name:modelName})});toast("模型已导入 Ollama");$("#refresh-models").click();}catch(error){toast(error.message);}};
      }
      localBox.appendChild(row);
    }
  } catch(error) { hadError=true;localBox.textContent=error.message; }
  try {
    if(installedResult.status!=="fulfilled")throw installedResult.reason;
    const installed=installedResult.value;installedCount=installed.length;installedBox.innerHTML="";
    if(!installed.length){installedBox.textContent="Ollama 中没有可用的对话/抽取模型";$("#current-model-status").textContent="当前模型：未选择";}
    for(const model of installed){
      const aliases=model.aliases?.length?model.aliases:[model.name||model.model];
      const selectedAlias=model.selected_name||aliases[0];
      const row=document.createElement("div");row.className=`model-row${model.selected?" model-selected":""}`;
      const info=document.createElement("span");
      info.innerHTML=`<strong>${escapeHtml(selectedAlias)}</strong>${aliases.length>1?`<small>同一权重的标签：${escapeHtml(aliases.join("、"))}</small>`:""}<small>${escapeHtml(model.digest||"").slice(0,12)}</small>`;
      const button=document.createElement("button");button.className="tool";button.textContent=!model.selectable?"非抽取模型":(model.selected?"当前模型":"设为当前模型");button.disabled=Boolean(model.selected)||!model.selectable;
      button.onclick=async()=>{
        button.disabled=true;button.textContent="正在切换…";
        try{
          await api("/api/settings/ollama-model",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({model:selectedAlias})});
          toast(`已选择模型 ${selectedAlias}`);await Promise.all([loadHealth(),loadOllamaProviderSetting()]);$("#refresh-models").click();
        }catch(error){toast(error.message);button.disabled=false;button.textContent="设为当前模型";}
      };
      row.append(info,button);installedBox.appendChild(row);
    }
    const current=installed.find(model=>model.selected);
    $("#current-model-status").textContent=`当前模型：${current?(current.selected_name||current.name||current.model):"未选择"}`;
  } catch(error) { hadError=true;installedBox.textContent="Ollama 未就绪："+error.message;$("#current-model-status").textContent="当前模型：不可用"; }
  finally{
    clearInterval(ticker);
    const seconds=((performance.now()-startedAt)/1000).toFixed(1);
    refreshStatus.textContent=hadError?`查询结束，部分项目失败 · ${seconds} 秒`:`查询完成 · ${installedCount} 个可用模型 · ${seconds} 秒`;
    button.classList.remove("is-loading");button.removeAttribute("aria-busy");
    button.textContent=hadError?"重新查询":"刷新完成 ✓";
    setTimeout(()=>{button.disabled=false;button.textContent="刷新模型状态";},900);
  }
};

window.addEventListener("resize",()=>{if(state.sourceImage){fitCanvas();draw();}});
Promise.all([loadHealth(),loadPatients(),loadOllamaProviderSetting()]).catch(error=>toast(error.message));
