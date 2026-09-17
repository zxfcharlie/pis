// ---------------- state ----------------
let ME = null;
let FILTER_OPTIONS = { seasons: [], scenes: [], products: [], regions: [] };
let SELECTED_FILTERS = { season: new Set(), scene: new Set(), product: new Set(), region: new Set() };
let TEMPLATES = [];
let SELECTED_TEMPLATE = null;
let UPLOAD_FILES = [];
let HISTORY_SELECTED = new Set();

const FIELD_DEFS = [
  ["subject", "主体"],
  ["style", "风格"],
  ["photography", "摄影"],
  ["atmosphere", "氛围"],
  ["background", "背景"],
  ["light", "光线"],
  ["negative", "负面"],
  ["parameters", "参数"],
];

const $ = (id) => document.getElementById(id);

// ---------------- boot ----------------
document.addEventListener("DOMContentLoaded", init);

async function init() {
  renderNav();
  if (!API.isLoggedIn()) {
    showAuth();
    return;
  }
  try {
    await loadMe();
    showApp();
    await Promise.all([loadFilters(), loadTemplates(), loadHistory()]);
    renderFieldsEditor();
  } catch (e) {
    console.error(e);
    showAuth();
  }
}

function renderAuthState() {
  init();
}

function showAuth() {
  $("authView").classList.remove("hidden");
  $("appView").classList.add("hidden");
}
function showApp() {
  $("authView").classList.add("hidden");
  $("appView").classList.remove("hidden");
}

function renderNav() {
  const nav = $("navArea");
  nav.innerHTML = "";
  if (API.isLoggedIn()) {
    if (ME && ME.is_admin) {
      const a = document.createElement("a");
      a.href = "/admin.html";
      a.textContent = "管理后台";
      nav.appendChild(a);
    }
    const btn = document.createElement("button");
    btn.className = "nav-btn";
    btn.textContent = "退出登录";
    btn.onclick = () => { API.clearToken(); ME = null; init(); };
    nav.appendChild(btn);
  }
}

// ---------------- auth ----------------
document.querySelectorAll(".tab-btn").forEach((btn) => {
  btn.addEventListener("click", () => {
    document.querySelectorAll(".tab-btn").forEach((b) => b.classList.remove("active"));
    btn.classList.add("active");
    const tab = btn.dataset.tab;
    $("loginForm").classList.toggle("hidden", tab !== "login");
    $("registerForm").classList.toggle("hidden", tab !== "register");
  });
});

$("loginForm").addEventListener("submit", async (e) => {
  e.preventDefault();
  $("loginError").classList.add("hidden");
  try {
    const { access_token } = await API.login($("loginUsername").value, $("loginPassword").value);
    API.setToken(access_token);
    await init();
  } catch (err) {
    $("loginError").textContent = err.message;
    $("loginError").classList.remove("hidden");
  }
});

$("registerForm").addEventListener("submit", async (e) => {
  e.preventDefault();
  $("registerError").classList.add("hidden");
  try {
    const { access_token } = await API.register($("regUsername").value, $("regPassword").value);
    API.setToken(access_token);
    await init();
  } catch (err) {
    $("registerError").textContent = err.message;
    $("registerError").classList.remove("hidden");
  }
});

// ---------------- me / quota ----------------
async function loadMe() {
  ME = await API.me();
  renderNav();
  $("meUsername").textContent = ME.username;
  $("meAdminBadge").classList.toggle("hidden", !ME.is_admin);
  $("relayKey").textContent = ME.relay_key;
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

$("regenKeyBtn").addEventListener("click", async () => {
  ME = await API.regenerateRelayKey();
  $("relayKey").textContent = ME.relay_key;
});

// ---------------- filters ----------------
async function loadFilters() {
  FILTER_OPTIONS = await API.templateFilters();
  renderChipGroup("filterSeason", FILTER_OPTIONS.seasons, "season");
  renderChipGroup("filterScene", FILTER_OPTIONS.scenes, "scene");
  renderChipGroup("filterProduct", FILTER_OPTIONS.products, "product");
  renderChipGroup("filterRegion", FILTER_OPTIONS.regions, "region");
}

function renderChipGroup(containerId, values, group) {
  const el = $(containerId);
  el.innerHTML = "";
  values.forEach((v) => {
    const chip = document.createElement("div");
    chip.className = "chip" + (SELECTED_FILTERS[group].has(v) ? " active" : "");
    chip.textContent = v;
    chip.onclick = () => {
      if (SELECTED_FILTERS[group].has(v)) SELECTED_FILTERS[group].delete(v);
      else SELECTED_FILTERS[group].add(v);
      chip.classList.toggle("active");
      loadTemplates();
    };
    el.appendChild(chip);
  });
}

$("mineOnlyChk").addEventListener("change", loadTemplates);

// ---------------- templates ----------------
async function loadTemplates() {
  TEMPLATES = await API.listTemplates({
    season: [...SELECTED_FILTERS.season],
    scene: [...SELECTED_FILTERS.scene],
    product: [...SELECTED_FILTERS.product],
    region: [...SELECTED_FILTERS.region],
    mine_only: $("mineOnlyChk").checked,
  });
  $("tplCount").textContent = TEMPLATES.length;
  const grid = $("tplGrid");
  grid.innerHTML = "";
  TEMPLATES.forEach((t) => {
    const card = document.createElement("div");
    card.className = "tpl-card" + (SELECTED_TEMPLATE && SELECTED_TEMPLATE.id === t.id ? " selected" : "");
    card.innerHTML = `
      <div class="name">${escapeHtml(t.name)}</div>
      <div class="tags">
        ${t.is_system ? '<span class="tag system">系统模板</span>' : '<span class="tag">我的模板</span>'}
        ${t.season ? `<span class="tag">${escapeHtml(t.season)}</span>` : ""}
        ${t.scene ? `<span class="tag">${escapeHtml(t.scene)}</span>` : ""}
        ${t.product ? `<span class="tag">${escapeHtml(t.product)}</span>` : ""}
        ${t.region ? `<span class="tag">${escapeHtml(t.region)}</span>` : ""}
      </div>
      <div class="snippet">${escapeHtml(t.subject)}</div>
    `;
    card.onclick = () => selectTemplate(t);
    grid.appendChild(card);
  });
}

function selectTemplate(t) {
  SELECTED_TEMPLATE = t;
  $("useAsIsChk").checked = true;
  $("selectedTplName").textContent = "已选模板：" + t.name + (t.is_system ? "（系统模板，只读）" : "");
  loadTemplates();
  renderFieldsEditor();
  updateCostEstimate();
}

// ---------------- fields editor ----------------
$("useAsIsChk").addEventListener("change", renderFieldsEditor);
$("saveAsTplChk").addEventListener("change", () => {
  $("saveTplName").classList.toggle("hidden", !$("saveAsTplChk").checked);
});

function renderFieldsEditor() {
  const useAsIs = $("useAsIsChk").checked;
  const container = $("fieldsEditor");
  container.innerHTML = "";
  const base = SELECTED_TEMPLATE || {};

  FIELD_DEFS.forEach(([key, label]) => {
    const wrap = document.createElement("div");
    const lbl = document.createElement("label");
    lbl.className = "field-label";
    lbl.textContent = `【${label}】`;
    const ta = document.createElement("textarea");
    ta.id = "field_" + key;
    ta.value = base[key] || "";
    ta.disabled = useAsIs && !!SELECTED_TEMPLATE;
    wrap.appendChild(lbl);
    wrap.appendChild(ta);
    container.appendChild(wrap);
  });
}

// ---------------- image upload ----------------
$("imageInput").addEventListener("change", (e) => {
  const files = Array.from(e.target.files).slice(0, 2);
  UPLOAD_FILES = files;
  const preview = $("imagePreview");
  preview.innerHTML = "";
  files.forEach((f) => {
    const img = document.createElement("img");
    img.src = URL.createObjectURL(f);
    preview.appendChild(img);
  });
});

$("genCount").addEventListener("input", updateCostEstimate);

function updateCostEstimate() {
  if (!ME) return;
  const n = Math.max(1, Math.min(4, parseInt($("genCount").value || "1", 10)));
  const cost = (ME.cost_per_image * n).toFixed(2);
  $("costEstimate").textContent = `预计花费 ${cost}（每张 ${ME.cost_per_image}）`;
}

// ---------------- generate ----------------
$("generateBtn").addEventListener("click", async () => {
  $("generateError").classList.add("hidden");
  if (UPLOAD_FILES.length < 1) {
    $("generateError").textContent = "请上传1-2张产品图";
    $("generateError").classList.remove("hidden");
    return;
  }

  const fd = new FormData();
  UPLOAD_FILES.forEach((f) => fd.append("images", f));
  if (SELECTED_TEMPLATE) fd.append("template_id", SELECTED_TEMPLATE.id);
  fd.append("use_template_as_is", $("useAsIsChk").checked);
  fd.append("n", $("genCount").value || "1");
  fd.append("save_as_template", $("saveAsTplChk").checked);
  if ($("saveAsTplChk").checked) fd.append("template_name", $("saveTplName").value || "");

  if (!$("useAsIsChk").checked) {
    FIELD_DEFS.forEach(([key]) => fd.append(key, $("field_" + key).value || ""));
  }

  $("generateBtn").disabled = true;
  $("generateLoading").classList.remove("hidden");
  try {
    const job = await API.generate(fd);
    await loadMe();
    await loadHistory();
    await renderResult(job);
    if (job.status === "failed") {
      $("generateError").textContent = "生成失败：" + job.error_message;
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

async function renderResult(job) {
  $("resultPanel").classList.remove("hidden");
  const grid = $("resultGrid");
  grid.innerHTML = "";
  for (let i = 0; i < job.output_images.length; i++) {
    const url = await imageBlobUrl(job.id, i);
    const card = document.createElement("div");
    card.className = "gen-card";
    card.innerHTML = `<img src="${url}" /><div class="meta">第 ${i + 1} 张 · 成本 ${(job.cost / job.output_images.length).toFixed(2)}</div>`;
    grid.appendChild(card);
  }
  $("resultPanel").scrollIntoView({ behavior: "smooth", block: "nearest" });
}

async function imageBlobUrl(jobId, index) {
  const token = API.getToken();
  const resp = await fetch(`/api/generations/${jobId}/image/${index}`, {
    headers: { Authorization: "Bearer " + token },
  });
  if (!resp.ok) return "";
  const blob = await resp.blob();
  return URL.createObjectURL(blob);
}

// ---------------- history ----------------
async function loadHistory() {
  const jobs = await API.listGenerations(1);
  const grid = $("historyGrid");
  grid.innerHTML = "";
  for (const job of jobs) {
    const card = document.createElement("div");
    card.className = "gen-card";
    const chosen = HISTORY_SELECTED.has(job.id);
    let imgHtml = '<div class="muted" style="padding:20px;text-align:center;">无图片</div>';
    if (job.output_images.length) {
      const url = await imageBlobUrl(job.id, 0);
      imgHtml = `<img src="${url}" />`;
    }
    card.innerHTML = `
      ${imgHtml}
      <div class="meta">
        <label class="row" style="font-size:12px;">
          <input type="checkbox" data-job="${job.id}" ${chosen ? "checked" : ""} /> 选择打包
        </label>
        <div>${new Date(job.created_at + "Z").toLocaleString()}</div>
        <div>状态：${job.status === "success" ? "成功" : job.status === "failed" ? "失败" : "处理中"} · ${job.image_count}张 · ¥${job.cost.toFixed(2)}</div>
        <div class="muted">${new Date(job.expire_at + "Z").toLocaleDateString()} 到期</div>
      </div>
    `;
    card.querySelector("input[type=checkbox]").addEventListener("change", (e) => {
      if (e.target.checked) HISTORY_SELECTED.add(job.id);
      else HISTORY_SELECTED.delete(job.id);
    });
    grid.appendChild(card);
  }
}

$("downloadSelectedBtn").addEventListener("click", async () => {
  if (HISTORY_SELECTED.size === 0) {
    alert("请先勾选要下载的生成记录");
    return;
  }
  const token = API.getToken();
  const resp = await fetch("/api/generations/batch-download", {
    method: "POST",
    headers: { "Content-Type": "application/json", Authorization: "Bearer " + token },
    body: JSON.stringify({ ids: [...HISTORY_SELECTED] }),
  });
  if (!resp.ok) {
    alert("下载失败");
    return;
  }
  const blob = await resp.blob();
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = "generations.zip";
  a.click();
  URL.revokeObjectURL(url);
});

// ---------------- utils ----------------
function escapeHtml(s) {
  return (s || "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}
