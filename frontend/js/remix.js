// ---------------- state ----------------
let ME = null;
let PRODUCT_OPTIONS = [];
let SELECTED_PRODUCTS = new Set();
let TEMPLATES = [];
let SELECTED_TEMPLATE = null;
let EDITING_TEMPLATE_ID = null; // null = creating new
let UPLOAD_FILES = [];
let HISTORY_SELECTED = new Set();

const $ = (id) => document.getElementById(id);

document.addEventListener("DOMContentLoaded", init);

async function init() {
  if (!API.isLoggedIn()) {
    $("authGate").classList.remove("hidden");
    $("remixView").classList.add("hidden");
    renderNav();
    return;
  }

  try {
    await loadMe();
  } catch (e) {
    console.error("loadMe failed, treating as logged out:", e);
    API.clearToken();
    $("authGate").classList.remove("hidden");
    $("remixView").classList.add("hidden");
    renderNav();
    return;
  }

  renderNav();
  $("authGate").classList.add("hidden");
  $("remixView").classList.remove("hidden");

  try {
    await loadFilters();
    await loadTemplates();
    await loadHistory();
  } catch (e) {
    console.error("failed to load remix page data:", e);
  }
}

function renderNav() {
  const nav = $("navArea");
  nav.innerHTML = "";
  if (!API.isLoggedIn()) return;
  const back = document.createElement("a");
  back.href = "/index.html";
  back.textContent = "返回套图";
  nav.appendChild(back);
  if (ME && ME.is_admin) {
    const a = document.createElement("a");
    a.href = "/admin.html";
    a.textContent = "管理后台";
    nav.appendChild(a);
  }
  const btn = document.createElement("button");
  btn.className = "nav-btn";
  btn.textContent = "退出登录";
  btn.onclick = () => { API.clearToken(); window.location.href = "/index.html"; };
  nav.appendChild(btn);
}

async function loadMe() {
  ME = await API.me();
  $("meUsername").textContent = ME.username;
  renderQuota();
}

function renderQuota() {
  $("quotaUsed").textContent = ME.used_today.toFixed(2);
  $("quotaTotal").textContent = ME.daily_quota.toFixed(2);
  const pct = ME.daily_quota > 0 ? Math.min(100, (ME.used_today / ME.daily_quota) * 100) : 0;
  const bar = $("quotaBar");
  bar.style.width = pct + "%";
  bar.className = pct >= 100 ? "over" : pct >= 80 ? "warn" : "";
  updateCostEstimate();
}

// ---------------- filters ----------------
async function loadFilters() {
  const opts = await API.remixFilters({ mine_only: $("mineOnlyChk").checked });
  PRODUCT_OPTIONS = opts.products || [];
  const el = $("filterProduct");
  el.innerHTML = "";
  PRODUCT_OPTIONS.forEach((v) => {
    const chip = document.createElement("div");
    chip.className = "chip" + (SELECTED_PRODUCTS.has(v) ? " active" : "");
    chip.textContent = v;
    chip.onclick = async () => {
      if (SELECTED_PRODUCTS.has(v)) SELECTED_PRODUCTS.delete(v);
      else SELECTED_PRODUCTS.add(v);
      await loadTemplates();
      await loadFilters();
    };
    el.appendChild(chip);
  });
}

$("mineOnlyChk").addEventListener("change", async () => {
  await loadFilters();
  await loadTemplates();
});

// ---------------- templates ----------------
async function loadTemplates() {
  TEMPLATES = await API.listRemixTemplates({
    product: [...SELECTED_PRODUCTS],
    mine_only: $("mineOnlyChk").checked,
  });
  $("tplCount").textContent = TEMPLATES.length;
  const grid = $("tplGrid");
  grid.innerHTML = "";
  for (const t of TEMPLATES) {
    const card = document.createElement("div");
    card.className = "tpl-card" + (SELECTED_TEMPLATE && SELECTED_TEMPLATE.id === t.id ? " selected" : "");
    const bgUrl = await bgImageBlobUrl(t.id);
    card.innerHTML = `
      <img src="${bgUrl}" style="width:100%;height:120px;object-fit:cover;border-radius:6px;margin-bottom:8px;" />
      <div class="name">${escapeHtml(t.name)}</div>
      <div class="tags">
        ${t.is_system ? '<span class="tag system">系统模板</span>' : '<span class="tag">我的模板</span>'}
        ${t.product ? `<span class="tag">${escapeHtml(t.product)}</span>` : ""}
      </div>
      <div class="snippet">${escapeHtml(t.prompt)}</div>
      ${t.editable ? '<button class="btn secondary" data-act="edit" style="margin-top:8px;padding:4px 10px;font-size:12px;">编辑</button>' : ""}
    `;
    card.addEventListener("click", (e) => {
      if (e.target.closest('[data-act=edit]')) return;
      selectTemplate(t);
    });
    const editBtn = card.querySelector('[data-act=edit]');
    if (editBtn) editBtn.addEventListener("click", (e) => { e.stopPropagation(); openEditor(t); });
    grid.appendChild(card);
  }
}

async function bgImageBlobUrl(templateId) {
  const token = API.getToken();
  const resp = await fetch(API.remixBackgroundImageUrl(templateId), { headers: { Authorization: "Bearer " + token } });
  if (!resp.ok) return "";
  const blob = await resp.blob();
  return URL.createObjectURL(blob);
}

function selectTemplate(t) {
  SELECTED_TEMPLATE = t;
  loadTemplates();
  $("generatePanel").classList.remove("hidden");
  $("genTplName").textContent = t.name;
  $("genTplProduct").textContent = t.product || "";
  $("genPrompt").value = t.prompt;
  bgImageBlobUrl(t.id).then((url) => { $("genBgPreview").src = url; });
  $("generatePanel").scrollIntoView({ behavior: "smooth", block: "nearest" });
  updateCostEstimate();
}

// ---------------- editor (create / edit template) ----------------
$("newTemplateBtn").addEventListener("click", () => openEditor(null));
$("cancelEditBtn").addEventListener("click", () => $("editorPanel").classList.add("hidden"));

function openEditor(t) {
  $("editorError").classList.add("hidden");
  EDITING_TEMPLATE_ID = t ? t.id : null;
  $("editorTitle").textContent = t ? "编辑二创模板" : "新建二创模板";
  $("editName").value = t ? t.name : "";
  $("editProduct").value = t ? t.product : "";
  $("editPrompt").value = t ? t.prompt : "把上传的产品（图2）放到图1中";
  $("editBgFile").value = "";
  $("deleteTemplateBtn").classList.toggle("hidden", !t);
  $("asSystemRow").classList.toggle("hidden", !(ME && ME.is_admin));
  $("editAsSystem").checked = !!(t && t.is_system);
  if (t) {
    $("editBgPreviewWrap").classList.remove("hidden");
    bgImageBlobUrl(t.id).then((url) => { $("editBgPreview").src = url; });
  } else {
    $("editBgPreviewWrap").classList.add("hidden");
  }
  $("editorPanel").classList.remove("hidden");
  $("editorPanel").scrollIntoView({ behavior: "smooth", block: "nearest" });
}

$("saveTemplateBtn").addEventListener("click", async () => {
  $("editorError").classList.add("hidden");
  const name = $("editName").value.trim();
  const product = $("editProduct").value.trim();
  const prompt = $("editPrompt").value.trim();
  const file = $("editBgFile").files[0];
  if (!name) {
    $("editorError").textContent = "请填写模板名称";
    $("editorError").classList.remove("hidden");
    return;
  }
  if (!EDITING_TEMPLATE_ID && !file) {
    $("editorError").textContent = "新建模板必须上传图1（背景图）";
    $("editorError").classList.remove("hidden");
    return;
  }
  const fd = new FormData();
  fd.append("name", name);
  fd.append("product", product);
  fd.append("prompt", prompt);
  if (!EDITING_TEMPLATE_ID) fd.append("as_system", $("editAsSystem").checked);
  if (file) fd.append("background_image", file);

  try {
    if (EDITING_TEMPLATE_ID) {
      await API.updateRemixTemplate(EDITING_TEMPLATE_ID, fd);
    } else {
      await API.createRemixTemplate(fd);
    }
    $("editorPanel").classList.add("hidden");
    await loadFilters();
    await loadTemplates();
  } catch (err) {
    $("editorError").textContent = err.message;
    $("editorError").classList.remove("hidden");
  }
});

$("deleteTemplateBtn").addEventListener("click", async () => {
  if (!EDITING_TEMPLATE_ID) return;
  if (!confirm("确定删除这个二创模板吗？")) return;
  try {
    await API.deleteRemixTemplate(EDITING_TEMPLATE_ID);
    $("editorPanel").classList.add("hidden");
    if (SELECTED_TEMPLATE && SELECTED_TEMPLATE.id === EDITING_TEMPLATE_ID) {
      SELECTED_TEMPLATE = null;
      $("generatePanel").classList.add("hidden");
    }
    await loadFilters();
    await loadTemplates();
  } catch (err) {
    $("editorError").textContent = err.message;
    $("editorError").classList.remove("hidden");
  }
});

// ---------------- batch product image upload ----------------
$("productImages").addEventListener("change", (e) => {
  const files = Array.from(e.target.files).slice(0, 20);
  UPLOAD_FILES = files;
  const preview = $("productPreview");
  preview.innerHTML = "";
  files.forEach((f) => {
    const img = document.createElement("img");
    img.src = URL.createObjectURL(f);
    preview.appendChild(img);
  });
  updateCostEstimate();
});

function updateCostEstimate() {
  if (!ME) return;
  const n = UPLOAD_FILES.length || 0;
  const cost = (ME.cost_per_image * n).toFixed(2);
  $("costEstimate").textContent = n ? `本次共 ${n} 张，预计花费 ${cost}（每张 ${ME.cost_per_image}）` : "";
}

// ---------------- generate ----------------
$("generateBtn").addEventListener("click", async () => {
  $("generateError").classList.add("hidden");
  if (!SELECTED_TEMPLATE) {
    $("generateError").textContent = "请先选择一个二创套图模板";
    $("generateError").classList.remove("hidden");
    return;
  }
  if (UPLOAD_FILES.length < 1) {
    $("generateError").textContent = "请上传至少1张产品图";
    $("generateError").classList.remove("hidden");
    return;
  }

  const fd = new FormData();
  fd.append("remix_template_id", SELECTED_TEMPLATE.id);
  UPLOAD_FILES.forEach((f) => fd.append("images", f));
  fd.append("prompt_override", $("genPrompt").value || "");
  fd.append("img_size", $("imgSize").value);
  fd.append("img_quality", $("imgQuality").value);
  fd.append("img_output_format", $("imgFormat").value);
  fd.append("img_background", $("imgBackground").value);

  $("generateBtn").disabled = true;
  $("generateLoading").classList.remove("hidden");
  try {
    const jobs = await API.generateRemix(fd);
    await loadMe();
    await loadHistory();
    await renderResults(jobs);
    const failed = jobs.filter((j) => j.status === "failed");
    if (failed.length) {
      $("generateError").textContent = `${failed.length} 张生成失败：` + failed.map((j) => j.error_message).join("; ");
      $("generateError").classList.remove("hidden");
    }
  } catch (err) {
    $("generateError").textContent = err.message;
    $("generateError").classList.remove("hidden");
  } finally {
    $("generateBtn").disabled = false;
    $("generateLoading").classList.add("hidden");
  }
});

async function renderResults(jobs) {
  $("resultPanel").classList.remove("hidden");
  const grid = $("resultGrid");
  grid.innerHTML = "";
  for (const job of jobs) {
    for (let i = 0; i < job.output_images.length; i++) {
      const url = await imageBlobUrl(job.id, i);
      const card = document.createElement("div");
      card.className = "gen-card";
      card.innerHTML = `<img src="${url}" /><div class="meta">成本 ${job.cost.toFixed(2)}</div>`;
      grid.appendChild(card);
    }
  }
  $("resultPanel").scrollIntoView({ behavior: "smooth", block: "nearest" });
}

async function imageBlobUrl(jobId, index) {
  const token = API.getToken();
  const resp = await fetch(`/api/generations/${jobId}/image/${index}`, { headers: { Authorization: "Bearer " + token } });
  if (!resp.ok) return "";
  const blob = await resp.blob();
  return URL.createObjectURL(blob);
}

// ---------------- history (二创生成记录, grouped by batch) ----------------
async function loadHistory() {
  const jobs = (await API.listGenerations(1)).filter((j) => j.remix_template_id);

  const batches = [];
  const byId = new Map();
  for (const job of jobs) {
    if (!byId.has(job.batch_id)) {
      const b = { batch_id: job.batch_id, jobs: [] };
      byId.set(job.batch_id, b);
      batches.push(b);
    }
    byId.get(job.batch_id).jobs.push(job);
  }

  const grid = $("historyGrid");
  grid.innerHTML = "";
  for (const batch of batches) {
    const firstJob = batch.jobs[0];
    const totalImages = batch.jobs.reduce((s, j) => s + j.output_images.length, 0);
    const totalCost = batch.jobs.reduce((s, j) => s + j.cost, 0);
    const anyFailed = batch.jobs.some((j) => j.status === "failed");
    const chosen = HISTORY_SELECTED.has(batch.batch_id);

    const thumbUrls = [];
    for (const job of batch.jobs) {
      for (let i = 0; i < job.output_images.length; i++) {
        thumbUrls.push(await imageBlobUrl(job.id, i));
        if (thumbUrls.length >= 8) break;
      }
      if (thumbUrls.length >= 8) break;
    }
    const thumbsHtml = thumbUrls.length
      ? `<div class="thumb-list">${thumbUrls.map((u) => `<img src="${u}" />`).join("")}</div>`
      : '<div class="muted" style="padding:20px;text-align:center;">无图片</div>';

    const card = document.createElement("div");
    card.className = "gen-card";
    card.style.gridColumn = "span 2";
    card.innerHTML = `
      <div style="padding:10px;">${thumbsHtml}</div>
      <div class="meta">
        <label class="row" style="font-size:12px;">
          <input type="checkbox" data-batch="${batch.batch_id}" ${chosen ? "checked" : ""} /> 选择打包（多批一起下载）
        </label>
        <div>${new Date(firstJob.created_at + "Z").toLocaleString()}</div>
        <div>状态：${anyFailed ? "部分失败" : "成功"} · 共 ${totalImages} 张 · ¥${totalCost.toFixed(2)}</div>
        <div class="muted">${new Date(firstJob.expire_at + "Z").toLocaleDateString()} 到期</div>
        <button class="btn secondary" data-act="download-batch" style="margin-top:6px;padding:4px 10px;font-size:12px;">下载本批次</button>
      </div>
    `;
    card.querySelector("input[type=checkbox]").addEventListener("change", (e) => {
      if (e.target.checked) HISTORY_SELECTED.add(batch.batch_id);
      else HISTORY_SELECTED.delete(batch.batch_id);
    });
    card.querySelector('[data-act=download-batch]').addEventListener("click", () => downloadBatches([batch.batch_id]));
    grid.appendChild(card);
  }
}

async function downloadBatches(batchIds) {
  const token = API.getToken();
  const resp = await fetch("/api/generations/batch-download", {
    method: "POST",
    headers: { "Content-Type": "application/json", Authorization: "Bearer " + token },
    body: JSON.stringify({ batch_ids: batchIds }),
  });
  if (!resp.ok) { alert("下载失败"); return; }
  const blob = await resp.blob();
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = "generations.zip";
  a.click();
  URL.revokeObjectURL(url);
}

$("downloadSelectedBtn").addEventListener("click", () => {
  if (HISTORY_SELECTED.size === 0) {
    alert("请先勾选要下载的批次");
    return;
  }
  downloadBatches([...HISTORY_SELECTED]);
});

// ---------------- utils ----------------
function escapeHtml(s) {
  return (s || "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}
