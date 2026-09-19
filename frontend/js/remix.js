// ---------------- state ----------------
let ME = null;
let PRODUCT_OPTIONS = [];
let SELECTED_PRODUCTS = new Set();
let TEMPLATES = [];
let SELECTED_TEMPLATE = null;
let EDITING_TEMPLATE_ID = null; // null = creating new
let UPLOAD_FILES = [];
let LAST_BATCH_ID = null;

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
  const hist = document.createElement("a");
  hist.href = "/history.html";
  hist.textContent = "生成历史";
  nav.appendChild(hist);
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
  if (PRODUCT_OPTIONS.length === 0) {
    el.innerHTML = '<span class="muted" style="font-size:12px;">暂无产品筛选项</span>';
  }
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
  const grid = $("tplGrid");
  grid.innerHTML = '<div class="muted">加载中…</div>';

  TEMPLATES = await API.listRemixTemplates({
    product: [...SELECTED_PRODUCTS],
    mine_only: $("mineOnlyChk").checked,
  });
  $("tplCount").textContent = TEMPLATES.length;

  if (TEMPLATES.length === 0) {
    grid.innerHTML = `<div class="muted" style="grid-column:1/-1;padding:20px;text-align:center;">
      还没有任何二创套图模板${SELECTED_PRODUCTS.size ? "（当前筛选条件下没有匹配的）" : ""}，点左侧"+ 新建二创模板"创建一个。
    </div>`;
    return;
  }

  // fetch every card's 图1 thumbnail in parallel instead of one-at-a-time -- this
  // was the main source of slow loading when there were more than a couple templates.
  const bgUrls = await Promise.all(TEMPLATES.map((t) => bgImageBlobUrl(t.id)));

  grid.innerHTML = "";
  TEMPLATES.forEach((t, idx) => {
    const isSelected = SELECTED_TEMPLATE && SELECTED_TEMPLATE.id === t.id;
    const card = document.createElement("div");
    card.className = "tpl-card" + (isSelected ? " selected" : "");
    card.innerHTML = `
      <div style="position:relative;">
        <img src="${bgUrls[idx]}" style="width:100%;height:120px;object-fit:cover;border-radius:6px;margin-bottom:8px;" />
        ${isSelected ? '<span class="tag system" style="position:absolute;top:6px;right:6px;">✓ 已选择</span>' : ""}
      </div>
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
  });
}

async function bgImageBlobUrl(templateId) {
  const token = API.getToken();
  try {
    const resp = await fetch(API.remixBackgroundImageUrl(templateId), { headers: { Authorization: "Bearer " + token } });
    if (!resp.ok) return "";
    const blob = await resp.blob();
    return URL.createObjectURL(blob);
  } catch (e) {
    return "";
  }
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

  const btn = $("saveTemplateBtn");
  btn.disabled = true;
  const originalText = btn.textContent;
  btn.textContent = "保存中…";
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
  } finally {
    btn.disabled = false;
    btn.textContent = originalText;
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

// ---------------- generate: one call per uploaded photo, so we get a real progress bar ----------------
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

  const batchId = (window.crypto && crypto.randomUUID) ? crypto.randomUUID() : ("b" + Date.now() + Math.random().toString(16).slice(2));
  LAST_BATCH_ID = batchId;

  const total = UPLOAD_FILES.length;
  let done = 0;
  const updateProgress = () => {
    const pct = total ? Math.round((done / total) * 100) : 0;
    $("genProgressFill").style.width = pct + "%";
    $("generateLoading").textContent = `正在生成 ${done}/${total} 张…`;
  };

  $("generateBtn").disabled = true;
  $("generateBtn").textContent = "生成中…";
  $("generateLoading").classList.remove("hidden");
  $("genProgressBar").classList.remove("hidden");
  updateProgress();

  const results = [];
  try {
    for (const file of UPLOAD_FILES) {
      const fd = new FormData();
      fd.append("remix_template_id", SELECTED_TEMPLATE.id);
      fd.append("image", file);
      fd.append("batch_id", batchId);
      fd.append("prompt_override", $("genPrompt").value || "");
      fd.append("img_size", $("imgSize").value);
      fd.append("img_quality", $("imgQuality").value);
      fd.append("img_output_format", $("imgFormat").value);
      fd.append("img_background", $("imgBackground").value);

      const job = await API.remixGenerateOne(fd);
      results.push(job);
      done++;
      updateProgress();
      // show results incrementally so the user sees progress, not just a spinner
      await renderResults(results);
    }

    await loadMe();
    const failed = results.filter((j) => j.status === "failed");
    if (failed.length) {
      $("generateError").textContent = `${failed.length} 张生成失败：` + failed.map((j) => j.error_message).join("; ");
      $("generateError").classList.remove("hidden");
    }
  } catch (err) {
    $("generateError").textContent = err.message;
    $("generateError").classList.remove("hidden");
  } finally {
    $("generateBtn").disabled = false;
    $("generateBtn").textContent = "开始批量生成";
    $("generateLoading").classList.add("hidden");
    $("genProgressBar").classList.add("hidden");
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
    if (job.status === "failed") {
      const card = document.createElement("div");
      card.className = "gen-card";
      card.innerHTML = `<div class="muted" style="padding:20px;text-align:center;">生成失败</div><div class="meta">${escapeHtml(job.error_message)}</div>`;
      grid.appendChild(card);
    }
  }
}

async function imageBlobUrl(jobId, index) {
  const token = API.getToken();
  const resp = await fetch(`/api/generations/${jobId}/image/${index}`, { headers: { Authorization: "Bearer " + token } });
  if (!resp.ok) return "";
  const blob = await resp.blob();
  return URL.createObjectURL(blob);
}

$("downloadThisBatchBtn").addEventListener("click", async (e) => {
  if (!LAST_BATCH_ID) return;
  const btn = e.currentTarget;
  const originalText = btn.textContent;
  btn.disabled = true;
  btn.textContent = "打包下载中…";
  try {
    const token = API.getToken();
    const resp = await fetch("/api/generations/batch-download", {
      method: "POST",
      headers: { "Content-Type": "application/json", Authorization: "Bearer " + token },
      body: JSON.stringify({ batch_ids: [LAST_BATCH_ID] }),
    });
    if (!resp.ok) {
      let msg = "下载失败";
      try { msg = (await resp.json()).detail || msg; } catch (err) {}
      alert(msg);
      return;
    }
    const blob = await resp.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = "generations.zip";
    a.click();
    URL.revokeObjectURL(url);
  } catch (err) {
    alert("下载失败：" + err.message);
  } finally {
    btn.disabled = false;
    btn.textContent = originalText;
  }
});

// ---------------- utils ----------------
function escapeHtml(s) {
  return (s || "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}
