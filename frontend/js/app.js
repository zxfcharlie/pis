// ---------------- state ----------------
let ME = null;
// cascading filter order: season -> product -> scene -> region
let SELECTED_FILTERS = { season: new Set(), product: new Set(), scene: new Set(), region: new Set() };
let TEMPLATES = [];
let SELECTED_TEMPLATES = new Map(); // id -> {template, count}
let UPLOAD_FILES = [];
let HISTORY_SELECTED = new Set();
let AUTO_SUGGESTED_NAME = "";

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
    await loadFilterOptions();
    await loadTemplates();
    await loadHistory();
    renderSelectedPanel();
    renderGeneratePanel();
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
  $("registerSuccess").classList.add("hidden");
  try {
    const result = await API.register($("regUsername").value, $("regPassword").value);
    if (result.status === "active" && result.access_token) {
      API.setToken(result.access_token);
      await init();
      return;
    }
    // pending approval - don't log in yet
    $("registerSuccess").textContent = result.message || "注册成功，请等待管理员审核";
    $("registerSuccess").classList.remove("hidden");
    $("registerForm").reset();
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

// ---------------- cascading filters: season -> product -> scene -> region ----------------
async function loadFilterOptions() {
  const opts = await API.templateFilters({
    season: [...SELECTED_FILTERS.season],
    product: [...SELECTED_FILTERS.product],
    scene: [...SELECTED_FILTERS.scene],
    region: [...SELECTED_FILTERS.region],
    mine_only: $("mineOnlyChk").checked,
  });

  renderChipGroup("filterSeason", opts.seasons, "season");

  const showProduct = SELECTED_FILTERS.season.size > 0;
  $("groupProduct").classList.toggle("hidden", !showProduct);
  if (showProduct) renderChipGroup("filterProduct", opts.products, "product");

  const showScene = showProduct && SELECTED_FILTERS.product.size > 0;
  $("groupScene").classList.toggle("hidden", !showScene);
  if (showScene) renderChipGroup("filterScene", opts.scenes, "scene");

  const showRegion = showScene && SELECTED_FILTERS.scene.size > 0;
  $("groupRegion").classList.toggle("hidden", !showRegion);
  if (showRegion) renderChipGroup("filterRegion", opts.regions, "region");
}

function renderChipGroup(containerId, values, group) {
  const el = $(containerId);
  el.innerHTML = "";
  values.forEach((v) => {
    const chip = document.createElement("div");
    chip.className = "chip" + (SELECTED_FILTERS[group].has(v) ? " active" : "");
    chip.textContent = v;
    chip.onclick = () => onFilterToggle(group, v);
    el.appendChild(chip);
  });
}

const FILTER_ORDER = ["season", "product", "scene", "region"];

async function onFilterToggle(group, value) {
  if (SELECTED_FILTERS[group].has(value)) SELECTED_FILTERS[group].delete(value);
  else SELECTED_FILTERS[group].add(value);

  // changing an upstream level resets everything downstream of it
  const idx = FILTER_ORDER.indexOf(group);
  FILTER_ORDER.slice(idx + 1).forEach((g) => SELECTED_FILTERS[g].clear());

  SELECTED_TEMPLATES.clear();
  await loadFilterOptions();
  await loadTemplates();
  renderSelectedPanel();
  renderGeneratePanel();
}

$("mineOnlyChk").addEventListener("change", async () => {
  await loadFilterOptions();
  await loadTemplates();
});

$("resetFilterBtn").addEventListener("click", async () => {
  FILTER_ORDER.forEach((g) => SELECTED_FILTERS[g].clear());
  SELECTED_TEMPLATES.clear();
  $("mineOnlyChk").checked = false;
  await loadFilterOptions();
  await loadTemplates();
  renderSelectedPanel();
  renderGeneratePanel();
});

// ---------------- templates (multi-select, grouped by season+product) ----------------
async function loadTemplates() {
  TEMPLATES = await API.listTemplates({
    season: [...SELECTED_FILTERS.season],
    product: [...SELECTED_FILTERS.product],
    scene: [...SELECTED_FILTERS.scene],
    region: [...SELECTED_FILTERS.region],
    mine_only: $("mineOnlyChk").checked,
  });
  $("tplCount").textContent = TEMPLATES.length;
  renderTemplateGroups();
}

function renderTemplateGroups() {
  const container = $("tplGroups");
  container.innerHTML = "";

  const groups = new Map(); // "season||product" -> [templates]
  TEMPLATES.forEach((t) => {
    const key = `${t.season || "未分类季节"}｜${t.product || "未分类产品"}`;
    if (!groups.has(key)) groups.set(key, []);
    groups.get(key).push(t);
  });

  for (const [groupLabel, items] of groups) {
    const section = document.createElement("div");
    section.style.marginBottom = "16px";
    const heading = document.createElement("div");
    heading.className = "muted";
    heading.style.margin = "4px 0 8px";
    heading.style.fontWeight = "600";
    heading.textContent = groupLabel + `（${items.length}）`;
    section.appendChild(heading);

    const grid = document.createElement("div");
    grid.className = "tpl-grid";
    items.forEach((t) => grid.appendChild(renderTplCard(t)));
    section.appendChild(grid);
    container.appendChild(section);
  }
}

function renderTplCard(t) {
  const card = document.createElement("div");
  const isSelected = SELECTED_TEMPLATES.has(t.id);
  card.className = "tpl-card" + (isSelected ? " selected" : "");
  card.innerHTML = `
    <div class="name">
      <input type="checkbox" ${isSelected ? "checked" : ""} style="margin-right:6px;" />
      ${escapeHtml(t.name)}
    </div>
    <div class="tags">
      ${t.is_system ? '<span class="tag system">系统模板</span>' : '<span class="tag">我的模板</span>'}
      ${t.season ? `<span class="tag">${escapeHtml(t.season)}</span>` : ""}
      ${t.product ? `<span class="tag">${escapeHtml(t.product)}</span>` : ""}
      ${t.scene ? `<span class="tag">${escapeHtml(t.scene)}</span>` : ""}
      ${t.region ? `<span class="tag">${escapeHtml(t.region)}</span>` : ""}
    </div>
    <div class="snippet">${escapeHtml(t.subject)}</div>
  `;
  card.onclick = () => toggleTemplateSelection(t);
  return card;
}

function toggleTemplateSelection(t) {
  if (SELECTED_TEMPLATES.has(t.id)) {
    SELECTED_TEMPLATES.delete(t.id);
  } else {
    SELECTED_TEMPLATES.set(t.id, { template: t, count: 1 });
  }
  renderTemplateGroups();
  renderSelectedPanel();
  renderGeneratePanel();
}

// ---------------- 已选套图面板 ----------------
function renderSelectedPanel() {
  const panel = $("selectedPanel");
  const list = $("selectedList");
  if (SELECTED_TEMPLATES.size === 0) {
    panel.classList.add("hidden");
    list.innerHTML = "";
    return;
  }
  panel.classList.remove("hidden");
  list.innerHTML = "";
  for (const [id, entry] of SELECTED_TEMPLATES) {
    const row = document.createElement("div");
    row.className = "row between";
    row.style.padding = "8px 0";
    row.style.borderBottom = "1px solid var(--border)";
    row.innerHTML = `
      <div>${escapeHtml(entry.template.name)}</div>
      <div class="row">
        <label style="font-size:12px;">生成数量
          <input type="number" min="1" max="4" value="${entry.count}" style="width:56px;display:inline-block;margin-left:4px;" />
        </label>
        <button class="btn secondary" style="padding:4px 10px;font-size:12px;">移除</button>
      </div>
    `;
    row.querySelector("input").addEventListener("input", (e) => {
      const v = Math.max(1, Math.min(4, parseInt(e.target.value || "1", 10)));
      entry.count = v;
      updateCostEstimate();
    });
    row.querySelector("button").addEventListener("click", () => {
      SELECTED_TEMPLATES.delete(id);
      renderTemplateGroups();
      renderSelectedPanel();
      renderGeneratePanel();
    });
    list.appendChild(row);
  }
  updateCostEstimate();
}

// ---------------- 生成面板：0 / 1 / 多选 三种状态 ----------------
function renderGeneratePanel() {
  const count = SELECTED_TEMPLATES.size;
  const hint = $("generateHint");
  const singleControls = $("singleTplControls");
  const multiHint = $("multiTplHint");
  const singleCountRow = $("singleCountRow");

  singleCountRow.classList.toggle("hidden", count !== 0);
  multiHint.classList.toggle("hidden", count <= 1);
  singleControls.classList.toggle("hidden", count > 1);

  if (count === 0) {
    hint.textContent = "未选择任何套图模板 —— 可直接自定义全部提示词字段生成一张。";
  } else if (count === 1) {
    const t = [...SELECTED_TEMPLATES.values()][0].template;
    hint.textContent = `已选模板：${t.name}${t.is_system ? "（系统模板，只读）" : ""}`;
  } else {
    hint.textContent = `已选择 ${count} 个套图。`;
  }

  renderFieldsEditor();
  updateCostEstimate();
}

$("useAsIsChk").addEventListener("change", renderFieldsEditor);
$("saveAsTplChk").addEventListener("change", () => {
  const show = $("saveAsTplChk").checked;
  $("saveTplName").classList.toggle("hidden", !show);
  if (show) {
    const suggestion = computeSuggestedName();
    if (!$("saveTplName").value || $("saveTplName").value === AUTO_SUGGESTED_NAME) {
      $("saveTplName").value = suggestion;
    }
    AUTO_SUGGESTED_NAME = suggestion;
  }
});

function computeSuggestedName() {
  let season = "", product = "", scene = "", region = "";
  if (SELECTED_TEMPLATES.size === 1) {
    const t = [...SELECTED_TEMPLATES.values()][0].template;
    season = t.season; product = t.product; scene = t.scene; region = t.region;
  } else {
    season = [...SELECTED_FILTERS.season][0] || "";
    product = [...SELECTED_FILTERS.product][0] || "";
    scene = [...SELECTED_FILTERS.scene][0] || "";
    region = [...SELECTED_FILTERS.region][0] || "";
  }
  return [season, product, scene, region].filter(Boolean).join("-");
}

function renderFieldsEditor() {
  const count = SELECTED_TEMPLATES.size;
  const useAsIsRow = document.getElementById("useAsIsChk").parentElement;

  if (count === 1) {
    useAsIsRow.classList.remove("hidden");
  } else {
    useAsIsRow.classList.add("hidden");
  }

  const useAsIs = count === 1 && $("useAsIsChk").checked;
  const base = count === 1 ? [...SELECTED_TEMPLATES.values()][0].template : {};

  const container = $("fieldsEditor");
  container.innerHTML = "";
  FIELD_DEFS.forEach(([key, label]) => {
    const wrap = document.createElement("div");
    const lbl = document.createElement("label");
    lbl.className = "field-label";
    lbl.textContent = `【${label}】`;
    const ta = document.createElement("textarea");
    ta.id = "field_" + key;
    ta.value = base[key] || "";
    ta.disabled = useAsIs;
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

function totalPlannedCount() {
  if (SELECTED_TEMPLATES.size === 0) {
    return Math.max(1, Math.min(4, parseInt($("genCount").value || "1", 10)));
  }
  let total = 0;
  for (const entry of SELECTED_TEMPLATES.values()) total += entry.count;
  return total;
}

function updateCostEstimate() {
  if (!ME) return;
  const n = totalPlannedCount();
  const cost = (ME.cost_per_image * n).toFixed(2);
  $("costEstimate").textContent = `本次共 ${n} 张，预计花费 ${cost}（每张 ${ME.cost_per_image}）`;
}

// ---------------- generate ----------------
$("generateBtn").addEventListener("click", async () => {
  $("generateError").classList.add("hidden");
  if (UPLOAD_FILES.length < 1) {
    $("generateError").textContent = "请上传1-2张产品图";
    $("generateError").classList.remove("hidden");
    return;
  }

  const imgParams = {
    size: $("imgSize").value,
    quality: $("imgQuality").value,
    output_format: $("imgFormat").value,
    background: $("imgBackground").value,
  };

  const tasks = [];
  if (SELECTED_TEMPLATES.size === 0) {
    tasks.push({ templateId: null, useAsIs: false, n: parseInt($("genCount").value || "1", 10), customFields: true });
  } else if (SELECTED_TEMPLATES.size === 1) {
    const [id, entry] = [...SELECTED_TEMPLATES.entries()][0];
    tasks.push({ templateId: id, useAsIs: $("useAsIsChk").checked, n: entry.count, customFields: !$("useAsIsChk").checked });
  } else {
    for (const [id, entry] of SELECTED_TEMPLATES) {
      tasks.push({ templateId: id, useAsIs: true, n: entry.count, customFields: false });
    }
  }

  $("generateBtn").disabled = true;
  $("generateLoading").classList.remove("hidden");
  const completedJobs = [];
  try {
    for (const task of tasks) {
      const fd = new FormData();
      UPLOAD_FILES.forEach((f) => fd.append("images", f));
      if (task.templateId) fd.append("template_id", task.templateId);
      fd.append("use_template_as_is", task.useAsIs);
      fd.append("n", task.n);
      fd.append("img_size", imgParams.size);
      fd.append("img_quality", imgParams.quality);
      fd.append("img_output_format", imgParams.output_format);
      fd.append("img_background", imgParams.background);

      if (tasks.length === 1) {
        fd.append("save_as_template", $("saveAsTplChk").checked);
        if ($("saveAsTplChk").checked) fd.append("template_name", $("saveTplName").value || "");
      }

      if (task.customFields) {
        FIELD_DEFS.forEach(([key]) => fd.append(key, $("field_" + key).value || ""));
      }

      const job = await API.generate(fd);
      completedJobs.push(job);
    }

    await loadMe();
    await loadHistory();
    await renderResults(completedJobs);

    const failed = completedJobs.filter((j) => j.status === "failed");
    if (failed.length) {
      $("generateError").textContent = `${failed.length} 个生成任务失败：` + failed.map((j) => j.error_message).join("; ");
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
      card.innerHTML = `<img src="${url}" /><div class="meta">第 ${i + 1} 张 · 成本 ${(job.cost / job.output_images.length).toFixed(2)}</div>`;
      grid.appendChild(card);
    }
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
