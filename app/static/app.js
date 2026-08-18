const $ = (selector) => document.querySelector(selector);
const $$ = (selector) => [...document.querySelectorAll(selector)];

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
  selectedObservationId: null,
  dataPreview: null,
};

const documentTypeLabels = {
  OTHER:"其他", MEDICAL_RECORD_COVER:"病案首页", ADMISSION:"入院记录", DISCHARGE:"出院记录",
  SURGERY:"手术记录", ULTRASOUND:"超声", MRI:"MRI", MAMMOGRAPHY:"钼靶",
  BIOPSY_PATHOLOGY:"穿刺病理", SURGICAL_PATHOLOGY:"术后病理", IHC:"免疫组化", TREATMENT:"治疗记录",
};

const commonRoiTypes = [["OTHER","其他信息"]];
const roiTypesByDocument = {
  OTHER: commonRoiTypes,
  MEDICAL_RECORD_COVER: [["cover_identity","病案号与出生日期"],["cover_contact","联系方式"],["cover_occupation","职业"],["cover_body_measurements","身高与体重"],...commonRoiTypes],
  ADMISSION: [["admission_identity","病案号、性别与职业"],["chronic_and_other_cancer_history","既往史、慢性病与其他癌种"],["prior_breast_history","乳腺癌及既往乳腺手术史"],["reproductive_history","婚育史"],["menstrual_history","月经与绝经史"],["family_history","家族史"],["lifestyle_history","吸烟与饮酒史"],["presentation_disease","偏侧性、来院转移与转移部位"],...commonRoiTypes],
  DISCHARGE: [["discharge_diagnosis","出院诊断、偏侧性与确诊日期"],["tnm_stage","TNM、临床分期与病理分期"],["pathology_summary","穿刺及术后病理摘要"],["ihc_summary","免疫组化摘要"],["fish_summary","FISH结果"],["surgery_summary","手术摘要"],["treatment_summary","治疗经过与方案"],["followup_plan","出院用药与随访计划"],...commonRoiTypes],
  SURGERY: [["surgery_date","手术日期"],["breast_surgery","乳房手术方式"],["axillary_surgery","腋窝手术方式"],["reconstruction","是否重建及重建方式"],["operative_findings","术中所见"],...commonRoiTypes],
  ULTRASOUND: [["imaging_date_phase","检查日期与治疗阶段"],["malignant_lesion_size","恶性肿块大小"],["malignant_lesion_location","恶性肿块位置及距乳头/皮肤距离"],["regional_nodes","区域淋巴结情况"],["ultrasound_birads","BI-RADS分级"],["post_neoadj_response","新辅助后肿块及淋巴结缓解"],...commonRoiTypes],
  MRI: [["imaging_date_phase","检查日期与治疗阶段"],["malignant_lesion_size","恶性肿块大小"],["malignant_lesion_location","恶性肿块位置及距乳头/皮肤距离"],["regional_nodes","区域淋巴结情况"],["mri_birads","BI-RADS分级"],["post_neoadj_response","新辅助后肿块及淋巴结缓解"],...commonRoiTypes],
  MAMMOGRAPHY: [["imaging_date_phase","检查日期与治疗阶段"],["lesion_number_and_size","恶性肿块单发/多发及大小"],["malignant_lesion_location","恶性肿块位置及距乳头/皮肤距离"],["mammography_birads","BI-RADS分级"],["calcification","钙化情况"],["regional_nodes","区域淋巴结情况"],["other_mammography","其他钼靶结果"],...commonRoiTypes],
  BIOPSY_PATHOLOGY: [["specimen_and_date","标本部位与报告日期"],["primary_pathology","原发灶病理类型与分级"],["primary_ihc","原发灶ER/PR/HER2/Ki-67及其他IHC"],["node_pathology","淋巴结病理类型与分级"],["node_ihc","淋巴结ER/PR/HER2/Ki-67及其他IHC"],["metastasis_pathology","转移灶病理类型与分级"],["metastasis_ihc","转移灶ER/PR/HER2/Ki-67及其他IHC"],["biopsy_fish","FISH结果"],...commonRoiTypes],
  SURGICAL_PATHOLOGY: [["specimen_and_date","标本部位与报告日期"],["postop_tumor_pathology","术后肿块类型、分级与大小"],["postop_tumor_ihc","术后肿块ER/PR/HER2/Ki-67及其他IHC"],["postop_nodes","术后淋巴结数量与转移情况"],["postop_node_ihc","术后淋巴结ER/PR/HER2/Ki-67及其他IHC"],["surgical_fish","FISH结果"],["pathological_stage","pTNM/ypTNM及病理分期"],["neoadj_pathology_response","pCR、MP与RCB评估"],...commonRoiTypes],
  IHC: [["specimen_and_date","标本部位与报告日期"],["ihc_panel","ER/PR/HER2/Ki-67面板"],["other_ihc","其他免疫组化"],["fish_result","FISH结果"],["molecular_subtype","分子分型"],...commonRoiTypes],
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

async function api(path, options = {}) {
  const response = await fetch(path, options);
  if (!response.ok) {
    let message = `请求失败 (${response.status})`;
    try { message = (await response.json()).detail || message; } catch (_) {}
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

async function loadPatients() {
  state.patients = await api("/api/patients");
  const list = $("#patient-list"); list.innerHTML = "";
  for (const patient of state.patients) {
    const button = document.createElement("button");
    button.className = `patient-item ${state.patient?.id === patient.id ? "active" : ""}`;
    button.innerHTML = `<strong>${escapeHtml(patient.patient_code)}</strong><small>${patient.document_count} 张脱敏图 · ${statusText(patient.status)}</small>`;
    button.onclick = () => selectPatient(patient.id);
    list.appendChild(button);
  }
  updatePatientSidebar();
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
      else if(!["EMPTY","UNAVAILABLE"].includes(status))td.classList.add("status-pending");
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
  try{await loadDataPreview();}catch(error){toast(error.message);}
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
  if(switching){clearEditor();state.selectedObservationId=null;}
  state.patient = await api(`/api/patients/${id}`);
  $("#empty-state").hidden = true; $("#patient-workspace").hidden = false;
  $("#current-patient-code").textContent = state.patient.patient_code;
  $("#current-patient-status").textContent = statusText(state.patient.status);
  renderDocuments(); renderObservations(); updatePatientSidebar(); await loadPatients();
}

async function refreshCurrentPatient(patientId) {
  if (!state.patient || state.patient.id !== patientId) return;
  state.patient = await api(`/api/patients/${patientId}`);
  $("#current-patient-status").textContent = statusText(state.patient.status);
  renderDocuments(); renderObservations(); updatePatientSidebar(); await loadPatients();
}

function leavePatient() {
  const pending=state.rawQueue.some(item=>item.file&&item.status!=="SAVED");
  if(pending&&!confirm("仍有未保存的导入图片，退出患者将清空当前待处理队列。确定退出吗？"))return false;
  clearRawQueue();state.patient=null;state.selectedObservationId=null;
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
  return ({UNPROCESSED:"未处理",AI_PROCESSED:"AI 已处理",REVIEW_REQUIRED:"待人工确认",VERIFIED:"人工已确认",EMPTY:"未填写",UNAVAILABLE:"不可用"})[status] || status;
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
    ["BIOPSY_PATHOLOGY",/穿刺|活检/],["IHC",/免疫组化|ihc/],["TREATMENT",/化疗|放疗|内分泌|靶向|治疗/],
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
  for (const rect of state.redactions) drawOverlay(rect,"rgba(18,18,18,.9)","#fff","隐私遮盖");
  state.rois.forEach((roi,index)=>{
    drawOverlay(roi,"rgba(39,147,104,.16)","#31a87a",roi.label);
    if(state.mode==="roi"&&state.activeRoiIndex===index)drawResizeHandles(displayRect(roi),"#31a87a");
  });
  if (state.drawing) drawDisplayOverlay(normalizedRect(state.drawing.start,state.drawing.end),"rgba(255,196,68,.16)","#f2bd3e",state.mode);
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
  if(state.roiResize){state.roiResize=null;draw();return;}
  if (!state.drawing) return; const display = normalizedRect(state.drawing.start,state.drawing.end); state.drawing=null;
  if (display.width < 6 || display.height < 6) { draw(); return; }
  const rect = normalizedRect(toSource({x:display.x,y:display.y}),toSource({x:display.x+display.width,y:display.y+display.height}));
  if (state.mode === "crop") { state.crop=rect; state.cropEditable=true; $("#editor-help").textContent="拖动黄色边线或八个控制点，可继续微调裁剪范围。"; }
  if (state.mode === "redact") state.redactions.push(rect);
  if (state.mode === "roi") { state.rois.push({...rect,type:$("#roi-type").value,label:$("#roi-type").selectedOptions[0].text}); state.activeRoiIndex=state.rois.length-1; $("#editor-help").textContent="点击任意ROI进行选择，拖动绿色边线或控制点微调。"; }
  draw();
});
canvas.addEventListener("pointercancel", () => { state.drawing=null;state.cropResize=null;state.roiResize=null;draw(); });

$$('[data-mode]').forEach(button => button.onclick = () => {
  state.mode=button.dataset.mode; $$('[data-mode]').forEach(item=>item.classList.toggle("active",item===button));
  if(state.mode==="roi"&&state.activeRoiIndex<0&&state.rois.length)state.activeRoiIndex=state.rois.length-1;
  $("#editor-help").textContent = ({crop:state.cropEditable?"拖动黄色边线或八个控制点微调裁剪范围。":"拖动框选最终保留范围。",redact:"拖动选择需要实心遮盖的区域。",roi:state.rois.length?"点击任意ROI进行选择，拖动绿色边线或控制点微调。":"框选信息区域；建立后可拖动边线和控制点微调。"})[state.mode];
  draw();
});
$("#undo").onclick = () => { if (state.mode==="redact") state.redactions.pop(); else if(state.mode==="roi") {state.rois.pop();state.activeRoiIndex=state.rois.length-1;} else {state.crop={x:0,y:0,width:state.sourceImage.naturalWidth,height:state.sourceImage.naturalHeight};state.cropEditable=false;$("#editor-help").textContent="拖动框选最终保留范围。";} draw(); };
$("#reset-editor").onclick = () => { if (!state.sourceImage) return; state.crop={x:0,y:0,width:state.sourceImage.naturalWidth,height:state.sourceImage.naturalHeight}; state.cropEditable=false;state.cropResize=null;state.redactions=[];state.rois=[];state.activeRoiIndex=-1;state.roiResize=null;$("#editor-help").textContent="拖动框选最终保留范围。";draw(); };

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
        const extraction=await api(`/api/documents/${job.documentId}/extract`,{method:"POST"});
        job.observationCount=extraction.observation_count||0;job.status="COMPLETED";
        job.tokenRate=extraction.performance?.token_rate||job.tokenRate;
        job.stage=job.target==="AI_ONLY"?"AI提取已完成":"OCR与AI均已完成";
      }catch(error){
        job.failedStage="AI";job.status="FAILED";job.stage="AI失败";job.error=error.message;
      }
      renderProcessingQueue();
      try{await refreshCurrentPatient(job.patientId);}catch(error){job.error=`结果刷新失败：${error.message}`;renderProcessingQueue();}
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
    card.querySelector("img").onclick=()=>openSavedDocumentPreview(doc.id).catch(error=>toast(error.message));
    card.querySelector(".run-ocr").onclick=()=>{const active=state.processingJobs.some(job=>job.documentId===doc.id&&!["COMPLETED","FAILED"].includes(job.status));if(active)return toast("该图片已有后台任务");queueDocuments([doc],"OCR_ONLY");toast("OCR任务已加入后台队列");};
    card.querySelector(".run-ai").onclick=()=>{const active=state.processingJobs.some(job=>job.documentId===doc.id&&!["COMPLETED","FAILED"].includes(job.status));if(active)return toast("该图片已有后台任务");queueDocuments([doc],"AI_ONLY");toast("AI任务已加入后台队列");};
    card.querySelector(".delete-document").onclick=async()=>{if(!confirm(`确定删除“${doc.display_name}”吗？\n该图片的ROI、OCR和AI抽取字段也会删除，审计记录会保留。`))return;try{await api(`/api/documents/${doc.id}`,{method:"DELETE"});toast("脱敏图片已删除");await selectPatient(state.patient.id);}catch(error){toast(error.message);}};
    list.appendChild(card);
  }
}

async function openSavedDocumentPreview(documentId,observationId=null) {
  const doc=(state.patient?.documents||[]).find(item=>item.id===documentId);
  if(!doc)throw new Error("找不到该记录对应的脱敏图片");
  if(observationId===null){state.selectedObservationId=null;renderFieldReview();renderObservations();}
  const activeRaw=state.rawQueue[state.activeRawIndex];
  persistActiveRawItem();
  if(activeRaw?.status==="EDITING")activeRaw.status="WAITING";
  state.activeRawIndex=-1;state.rawLoadToken+=1;clearEditor();renderRawQueue();
  const token=state.rawLoadToken,image=new Image();
  await new Promise((resolve,reject)=>{
    image.onload=resolve;
    image.onerror=()=>reject(new Error(`无法打开 ${doc.display_name}`));
    image.src=`/api/documents/${doc.id}/image?v=${encodeURIComponent(doc.sha256||doc.id)}`;
  });
  if(token!==state.rawLoadToken)return;
  state.sourceImage=image;state.enhancedImage=state.enhancementEnabled?createEnhancedImage(image):null;
  state.mode="crop";state.viewZoom=1;state.reviewDocumentId=doc.id;state.reviewObservationId=observationId;
  state.editingDocumentId=doc.id;
  state.crop={x:0,y:0,width:image.naturalWidth,height:image.naturalHeight};state.cropEditable=false;
  state.redactions=[];
  state.rois=(doc.regions||[]).map(region=>({
    x:Number(region.x),y:Number(region.y),width:Number(region.width),height:Number(region.height),
    type:region.region_type,label:region.label,
  }));
  state.activeRoiIndex=state.rois.length-1;state.drawing=null;
  $("#document-type").value=doc.document_type;updateRoiTypeOptions();$("#display-name").value=doc.display_name;
  state.editorBaseline=editorRevisionSignature();
  $$('[data-mode]').forEach(button=>button.classList.toggle("active",button.dataset.mode==="crop"));
  setMetadataControlsEnabled(true);enableEditor(true);fitCanvas();draw();$("#canvas-placeholder").hidden=true;
  $("#editor-help").textContent=`${doc.display_name}：可继续裁剪、增加遮盖或调整ROI；发生修改后才能覆盖并重新识别。`;
  $$(".observation").forEach(row=>row.classList.toggle("previewing",row.dataset.observationId===observationId));
  $(".import-options").scrollIntoView({behavior:"smooth",block:"start"});
}

function selectedObservation() {
  return (state.patient?.observations||[]).find(item=>item.id===state.selectedObservationId)||null;
}

function orderedObservations() {
  return [...(state.patient?.observations||[])].sort((left,right)=>{
    const reviewGroup=Number(left.status==="VERIFIED")-Number(right.status==="VERIFIED");
    if(reviewGroup!==0)return reviewGroup;
    const fieldOrder=(Number(left.field_order) || 0)-(Number(right.field_order) || 0);
    if(fieldOrder!==0)return fieldOrder;
    return String(left.created_at||"").localeCompare(String(right.created_at||""))||String(left.id).localeCompare(String(right.id));
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
    };
    container.appendChild(button);
  }
}

function renderFieldReview() {
  const panel=$("#field-review-panel"),observation=selectedObservation();
  const completePanel=$("#review-complete-panel");
  if(!state.patient||!observation){
    panel.hidden=true;
    const observations=state.patient?.observations||[];
    completePanel.hidden=!(state.patient&&observations.length&&observations.every(item=>item.status==="VERIFIED"));
    renderConflictEvidence(null);
    return;
  }
  completePanel.hidden=true;
  const observations=orderedObservations(),index=observations.findIndex(item=>item.id===observation.id);
  panel.hidden=false;
  $("#review-field-name").textContent=observation.field_label||observation.field_name;
  $("#review-field-key").textContent=`字段名：${observation.field_name}`;
  $("#review-ai-value").value=observation.ai_value??"";
  const basisBox=$("#review-inference-basis"),basis=Array.isArray(observation.inference_basis)?observation.inference_basis:[];
  basisBox.hidden=!basis.length;
  basisBox.innerHTML=basis.length?`<strong>依据</strong>${basis.map(item=>`
    <div class="review-basis-item">
      <div class="review-basis-summary">
        <b>${escapeHtml(item.component||"依据")}</b>
        <span>${escapeHtml(item.fact||"")}</span>
      </div>
      ${item.source_text?`<small>${escapeHtml(item.source_text)}</small>`:""}
    </div>`).join("")}`:"";
  $("#review-current-value").value=observation.current_value??"";
  renderReviewChoices(observation);
  $("#review-note").value="";
  const evidence=observation.raw_text?` · 证据：${observation.raw_text}`:"";
  const candidates=(observation.candidate_values||[]).filter(item=>item.valid).map(item=>`${item.value}（${item.source}）`).join("；");
  const conflict=observation.candidate_conflict?` · 存在候选冲突：${candidates}`:"";
  const rejected=observation.discarded_candidate_count?` · 已排除 ${observation.discarded_candidate_count} 条非法候选`:"";
  const invalidOnly=observation.invalid_only?" · 当前值不符合问卷值域，请人工修改":"";
  $("#review-field-meta").textContent=`${statusText(observation.status)} · ${observation.confidence}${evidence}${conflict}${rejected}${invalidOnly}`;
  $("#review-position").textContent=`${index+1} / ${observations.length}`;
  $("#previous-field").disabled=index<=0;
  $("#next-field").disabled=index<0||index>=observations.length-1;
  const verified=observation.status==="VERIFIED";
  $("#review-current-value").disabled=false;
  $("#review-note").disabled=false;
  $("#save-field-edit").disabled=false;
  $("#verify-field").disabled=false;
  $("#verify-field").textContent=verified?"再次确认":"人工确认";
  renderConflictEvidence(observation);
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
  for(const candidate of candidates){
    const button=document.createElement("button");button.type="button";button.className="conflict-evidence-card";
    button.innerHTML=`<img src="/api/documents/${encodeURIComponent(candidate.document_id)}/image" alt="${escapeHtml(candidate.source)}"><span><strong>${escapeHtml(candidate.value)}</strong><small>${escapeHtml(candidate.source)}</small></span>`;
    button.onclick=()=>openSavedDocumentPreview(candidate.document_id,observation.id).catch(error=>toast(error.message));
    container.appendChild(button);
  }
}

async function chooseObservation(observation) {
  state.selectedObservationId=observation.id;
  renderFieldReview();renderObservations();
  await openSavedDocumentPreview(observation.document_id,observation.id);
}

async function navigateObservation(offset) {
  const observations=orderedObservations(),current=selectedObservation();
  if(!current)return;
  const index=observations.findIndex(item=>item.id===current.id),target=observations[index+offset];
  if(target)await chooseObservation(target);
}

$("#previous-field").onclick=()=>navigateObservation(-1).catch(error=>toast(error.message));
$("#next-field").onclick=()=>navigateObservation(1).catch(error=>toast(error.message));

function nextUnverifiedObservation(afterId) {
  const observations=orderedObservations();
  if(!observations.length)return null;
  const start=Math.max(0,observations.findIndex(item=>item.id===afterId));
  for(let offset=1;offset<=observations.length;offset++){
    const candidate=observations[(start+offset)%observations.length];
    if(candidate.status!=="VERIFIED")return candidate;
  }
  return null;
}

$("#save-field-edit").onclick=async()=>{
  const observation=selectedObservation();if(!observation)return;
  const value=$("#review-current-value").value.trim();
  if(value===(observation.current_value??""))return toast("字段值没有变化");
  const reason=$("#review-note").value.trim()||"人工复核修正";
  try{
    await api(`/api/observations/${observation.id}`,{method:"PATCH",headers:{"Content-Type":"application/json"},body:JSON.stringify({value,reason,operator:"local-user"})});
    await refreshCurrentPatient(state.patient.id);toast("字段修改已保存");
  }catch(error){toast(error.message);}
};

$("#verify-field").onclick=async()=>{
  const observation=selectedObservation();if(!observation)return;
  const confirmedId=observation.id;
  const value=$("#review-current-value").value.trim(),note=$("#review-note").value.trim();
  try{
    if(value!==(observation.current_value??"")){
      await api(`/api/observations/${observation.id}`,{method:"PATCH",headers:{"Content-Type":"application/json"},body:JSON.stringify({value,reason:note||"人工复核修正",operator:"local-user"})});
    }
    await api(`/api/observations/${observation.id}/verify`,{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({operator:"local-user",note:note||null})});
    await refreshCurrentPatient(state.patient.id);
    const next=nextUnverifiedObservation(confirmedId);
    if(next){await chooseObservation(next);toast("字段已确认，已进入下一条待审核记录");}
    else{
      state.selectedObservationId=null;clearEditor();renderFieldReview();renderObservations();
      $("#review-complete-panel").scrollIntoView({behavior:"smooth",block:"start"});
      toast("当前患者全部字段已处理完毕");
    }
  }catch(error){toast(error.message);}
};

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
  const observations=orderedObservations();$("#observation-count").textContent=`${observations.length} 项`;const list=$("#observation-list");list.innerHTML="";
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
    row.dataset.observationId=obs.id;row.tabIndex=0;row.title="点击查看对应图片";
    const merged=obs.candidate_count>1?` · 已合并 ${obs.candidate_count} 条候选`:"";
    const conflict=obs.candidate_conflict?" · 候选冲突待确认":"";
    row.innerHTML=`<div><strong>${escapeHtml(obs.field_label||obs.field_name)}：${escapeHtml(obs.current_value)}</strong><small class="observation-field-key">字段名：${escapeHtml(obs.field_name)}</small><small>问卷第 ${Number(obs.field_order)+1} 项 · ${statusText(obs.status)} · ${escapeHtml(obs.confidence)} · AI原值 ${escapeHtml(obs.ai_value)}${merged}${conflict}</small></div><span class="review-record-hint">审核 ›</span>`;
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
