const $ = (selector) => document.querySelector(selector);
const $$ = (selector) => [...document.querySelectorAll(selector)];

const state = {
  patients: [], patient: null, sourceImage: null,
  mode: "crop", crop: null, redactions: [], rois: [], drawing: null,
};

const canvas = $("#image-canvas");
const ctx = canvas.getContext("2d");

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
  $("#privacy-status").textContent = health.offline_mode
    ? "● 离线模式 · 外部 API 已禁用" : "● 本地服务 · 可配置网络";
}

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
}

async function selectPatient(id) {
  state.patient = await api(`/api/patients/${id}`);
  $("#empty-state").hidden = true; $("#patient-workspace").hidden = false;
  $("#current-patient-code").textContent = state.patient.patient_code;
  $("#current-patient-status").textContent = statusText(state.patient.status);
  renderDocuments(); renderObservations(); await loadPatients();
}

function statusText(status) {
  return ({UNPROCESSED:"未处理",AI_PROCESSED:"AI 已处理",REVIEW_REQUIRED:"待人工确认",VERIFIED:"人工已确认"})[status] || status;
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

$("#raw-file").addEventListener("change", (event) => {
  const file = event.target.files[0]; if (!file) return;
  const url = URL.createObjectURL(file); const image = new Image();
  image.onload = () => {
    URL.revokeObjectURL(url); state.sourceImage = image;
    state.crop = {x:0,y:0,width:image.naturalWidth,height:image.naturalHeight};
    state.redactions = []; state.rois = []; state.drawing = null;
    // Do not persist the raw filename: it may itself contain patient identifiers.
    $("#display-name").value = "";
    enableEditor(true); fitCanvas(); draw();
    $("#canvas-placeholder").hidden = true;
    $("#editor-help").textContent = "拖动框选需要保留的区域；切换到实心遮盖后覆盖姓名、住院号等身份信息。";
  };
  image.onerror = () => { URL.revokeObjectURL(url); toast("无法读取该图片"); };
  image.src = url;
});

function enableEditor(enabled) {
  $$(".tool").forEach(button => button.disabled = !enabled);
  $("#save-sanitized").disabled = !enabled;
}

function fitCanvas() {
  const image = state.sourceImage; if (!image) return;
  const maxWidth = Math.min(1100, $(".canvas-shell").clientWidth - 4);
  const scale = Math.min(1, maxWidth / image.naturalWidth, 780 / image.naturalHeight);
  canvas.width = Math.round(image.naturalWidth * scale);
  canvas.height = Math.round(image.naturalHeight * scale);
}

function scaleX() { return state.sourceImage ? canvas.width / state.sourceImage.naturalWidth : 1; }
function scaleY() { return state.sourceImage ? canvas.height / state.sourceImage.naturalHeight : 1; }
function toSource(point) { return {x:point.x/scaleX(), y:point.y/scaleY()}; }
function normalizedRect(a,b) { return {x:Math.min(a.x,b.x),y:Math.min(a.y,b.y),width:Math.abs(a.x-b.x),height:Math.abs(a.y-b.y)}; }

function draw() {
  if (!state.sourceImage) return;
  ctx.clearRect(0,0,canvas.width,canvas.height);
  ctx.drawImage(state.sourceImage,0,0,canvas.width,canvas.height);
  if (state.crop) {
    const r = displayRect(state.crop); ctx.save(); ctx.fillStyle="rgba(0,0,0,.48)";
    ctx.fillRect(0,0,canvas.width,r.y); ctx.fillRect(0,r.y,r.x,r.height);
    ctx.fillRect(r.x+r.width,r.y,canvas.width-r.x-r.width,r.height);
    ctx.fillRect(0,r.y+r.height,canvas.width,canvas.height-r.y-r.height);
    ctx.strokeStyle="#f4c95d"; ctx.lineWidth=2; ctx.strokeRect(r.x,r.y,r.width,r.height); ctx.restore();
  }
  for (const rect of state.redactions) drawOverlay(rect,"rgba(18,18,18,.9)","#fff","隐私遮盖");
  for (const roi of state.rois) drawOverlay(roi,"rgba(39,147,104,.16)","#31a87a",roi.label);
  if (state.drawing) drawDisplayOverlay(normalizedRect(state.drawing.start,state.drawing.end),"rgba(255,196,68,.16)","#f2bd3e",state.mode);
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

function canvasPoint(event) { const box=canvas.getBoundingClientRect(); return {x:(event.clientX-box.left)*(canvas.width/box.width),y:(event.clientY-box.top)*(canvas.height/box.height)}; }
canvas.addEventListener("pointerdown", (event) => { if (!state.sourceImage) return; canvas.setPointerCapture(event.pointerId); const p=canvasPoint(event); state.drawing={start:p,end:p}; draw(); });
canvas.addEventListener("pointermove", (event) => { if (!state.drawing) return; state.drawing.end=canvasPoint(event); draw(); });
canvas.addEventListener("pointerup", () => {
  if (!state.drawing) return; const display = normalizedRect(state.drawing.start,state.drawing.end); state.drawing=null;
  if (display.width < 6 || display.height < 6) { draw(); return; }
  const rect = normalizedRect(toSource({x:display.x,y:display.y}),toSource({x:display.x+display.width,y:display.y+display.height}));
  if (state.mode === "crop") state.crop=rect;
  if (state.mode === "redact") state.redactions.push(rect);
  if (state.mode === "roi") state.rois.push({...rect,type:$("#roi-type").value,label:$("#roi-type").selectedOptions[0].text});
  draw();
});

$$('[data-mode]').forEach(button => button.onclick = () => {
  state.mode=button.dataset.mode; $$('[data-mode]').forEach(item=>item.classList.toggle("active",item===button));
  $("#editor-help").textContent = ({crop:"拖动框选最终保留范围。",redact:"拖动实心覆盖患者身份信息；保存后像素不可恢复。",roi:"可框选多个信息区域，帮助 OCR、AI 抽取和证据定位。"})[state.mode];
});
$("#undo").onclick = () => { if (state.mode==="redact") state.redactions.pop(); else if(state.mode==="roi") state.rois.pop(); else state.crop={x:0,y:0,width:state.sourceImage.naturalWidth,height:state.sourceImage.naturalHeight}; draw(); };
$("#reset-editor").onclick = () => { if (!state.sourceImage) return; state.crop={x:0,y:0,width:state.sourceImage.naturalWidth,height:state.sourceImage.naturalHeight}; state.redactions=[];state.rois=[];draw(); };

function buildSanitizedBlob() {
  return new Promise((resolve,reject) => {
    const crop=state.crop; const output=document.createElement("canvas"); output.width=Math.round(crop.width);output.height=Math.round(crop.height);
    const out=output.getContext("2d",{alpha:false}); out.fillStyle="#fff";out.fillRect(0,0,output.width,output.height);
    out.drawImage(state.sourceImage,crop.x,crop.y,crop.width,crop.height,0,0,output.width,output.height);
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
  if (!confirm("请确认患者姓名、住院号、身份证号、手机号等均已实心遮盖。系统只会保存当前脱敏结果。")) return;
  const button=$("#save-sanitized"); button.disabled=true; button.textContent="正在保存…";
  try {
    const blob=await buildSanitizedBlob(); const crop=state.crop;
    const regions=state.rois.map(r=>{
      const x=Math.max(r.x,crop.x),y=Math.max(r.y,crop.y),right=Math.min(r.x+r.width,crop.x+crop.width),bottom=Math.min(r.y+r.height,crop.y+crop.height);
      return {region_type:r.type,label:r.label,x:x-crop.x,y:y-crop.y,width:right-x,height:bottom-y};
    }).filter(r=>r.width>0&&r.height>0);
    const metadata={source_width:state.sourceImage.naturalWidth,source_height:state.sourceImage.naturalHeight,crop,redaction_count:state.redactions.length,client_reencoded:true};
    const form=new FormData(); form.append("image",blob,"sanitized.png"); form.append("display_name",$("#display-name").value||"脱敏图片"); form.append("document_type",$("#document-type").value); form.append("sanitization",JSON.stringify(metadata)); form.append("regions",JSON.stringify(regions));
    await api(`/api/patients/${state.patient.id}/documents`,{method:"POST",body:form});
    // Release every browser reference to the raw source immediately after successful import.
    state.sourceImage=null;state.crop=null;state.redactions=[];state.rois=[];state.drawing=null;
    $("#raw-file").value="";ctx.clearRect(0,0,canvas.width,canvas.height);canvas.width=0;canvas.height=0;$("#canvas-placeholder").hidden=false;enableEditor(false);
    toast("已保存脱敏主图，原图内存引用已释放"); await selectPatient(state.patient.id);
  } catch(error) { toast(error.message); }
  finally { button.disabled=!state.sourceImage;button.textContent="确认脱敏并保存"; }
};

function renderDocuments() {
  const docs=state.patient?.documents||[]; $("#doc-count").textContent=`${docs.length} 张`; const list=$("#document-list");list.innerHTML="";
  if(!docs.length){list.innerHTML='<div class="muted-empty">尚无脱敏图片</div>';return;}
  for(const doc of docs){const card=document.createElement("article");card.className="document-card";card.innerHTML=`<img src="/api/documents/${doc.id}/image" alt="脱敏病历"><div><strong title="${escapeHtml(doc.display_name)}">${escapeHtml(doc.display_name)}</strong><small>${escapeHtml(doc.document_type)} · ${doc.regions.length} ROI</small></div>`;list.appendChild(card);}
}

function renderObservations() {
  const observations=state.patient?.observations||[];$("#observation-count").textContent=`${observations.length} 项`;const list=$("#observation-list");list.innerHTML="";
  if(!observations.length){list.innerHTML='<div class="muted-empty">OCR / AI 抽取接入后，字段会在这里进入人工审核。</div>';return;}
  for(const obs of observations){
    const row=document.createElement("div");row.className="observation";
    row.innerHTML=`<div><strong>${escapeHtml(obs.field_name)}：${escapeHtml(obs.current_value)}</strong><small>${statusText(obs.status)} · ${escapeHtml(obs.confidence)} · AI原值 ${escapeHtml(obs.ai_value)}</small></div>${obs.status!=="VERIFIED"?'<div class="observation-actions"><button class="edit-observation">修改</button><button class="verify">人工确认</button></div>':''}`;
    const edit=row.querySelector(".edit-observation");
    if(edit) edit.onclick=async()=>{const value=prompt(`修改 ${obs.field_name}（AI 原值：${obs.ai_value??"空"}）`,obs.current_value??"");if(value===null)return;const reason=prompt("修改原因（建议填写）","人工复核修正");await api(`/api/observations/${obs.id}`,{method:"PATCH",headers:{"Content-Type":"application/json"},body:JSON.stringify({value,reason,operator:"local-user"})});await selectPatient(state.patient.id);};
    const verify=row.querySelector(".verify");
    if(verify) verify.onclick=async()=>{await api(`/api/observations/${obs.id}/verify`,{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({operator:"local-user"})});await selectPatient(state.patient.id);};
    list.appendChild(row);
  }
}

$("#refresh-models").onclick = async () => {
  const localBox=$("#local-models"),installedBox=$("#installed-models");
  try {
    const local=await api("/api/models/local-files");localBox.innerHTML=local.length?"":"未发现 GGUF";
    for(const file of local){
      const row=document.createElement("div");row.className="model-row";const suggested=file.filename.replace(/\.gguf$/i,"").replace(/[^A-Za-z0-9._-]/g,"-");
      row.innerHTML=`<span>${escapeHtml(file.filename)}<small> ${(file.size/1073741824).toFixed(2)} GB</small></span><span><input value="${escapeHtml(suggested)}" aria-label="Ollama模型名"><button class="tool">导入</button></span>`;
      row.querySelector("button").onclick=async()=>{const modelName=row.querySelector("input").value.trim();if(!modelName)return;try{await api("/api/models/import",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({filename:file.filename,model_name:modelName})});toast("模型已导入 Ollama");$("#refresh-models").click();}catch(error){toast(error.message);}};
      localBox.appendChild(row);
    }
  } catch(error) { localBox.textContent=error.message; }
  try {
    const installed=await api("/api/models/installed");installedBox.innerHTML=installed.length?installed.map(model=>`<div class="model-row"><span>${escapeHtml(model.name||model.model)}</span><small>${escapeHtml(model.digest||"").slice(0,12)}</small></div>`).join(""):"Ollama 中尚无模型";
  } catch(error) { installedBox.textContent="Ollama 未就绪："+error.message; }
};

window.addEventListener("resize",()=>{if(state.sourceImage){fitCanvas();draw();}});
Promise.all([loadHealth(),loadPatients()]).catch(error=>toast(error.message));
