const $ = (id) => document.getElementById(id);

let ME = null;
let ALL_JOBS = [];
let HISTORY_SELECTED = new Set();
let refreshTimer = null;

const KIND_LABELS = { template: "套图模板", remix: "二创套图", custom: "自定义" };

document.addEventListener("DOMContentLoaded", init);

async function init() {
  if (!API.isLoggedIn()) {
    $("authGate").classList.remove("hidden");
    $("historyView").classList.add("hidden");
    renderNav();
    return;
  }
  try {
    ME = await API.me();
  } catch (e) {
    API.clearToken();
    $("authGate").classList.remove("hidden");
    $("historyView").classList.add("hidden");
    renderNav();
    return;
  }
  renderNav();
  $("authGate").classList.add("hidden");
  $("historyView").classList.remove("hidden");

  $("filterKind").addEventListener("change", loadHistory);
  $("filterProduct").addEventListener("change", renderBatches);
  $("filterDays").addEventListener("change", loadHistory);
  $("refreshBtn").addEventListener("click", loadHistory);

  await loadHistory();
  refreshTimer = setInterval(loadHistory, 30000);
}

function renderNav() {
  const nav = $("navArea");
  nav.innerHTML = "";
  if (!API.isLoggedIn()) return;
  const back = document.createElement("a");
  back.href = "/index.html";
  back.textContent = "返回套图";
  nav.appendChild(back);
  const remix = document.createElement("a");
  remix.href = "/remix.html";
  remix.textContent = "二创套图";
  nav.appendChild(remix);
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

async function loadHistory() {
  $("loadingHint").classList.remove("hidden");
  try {
    const kind = $("filterKind").value;
    const days = $("filterDays").value;
    ALL_JOBS = await API.listGenerations({ page: 1, page_size: 300, kind: kind || undefined, days: days || undefined });
    populateProductFilter();
    await renderBatches();
  } catch (e) {
    console.error("failed to load history:", e);
  } finally {
    $("loadingHint").classList.add("hidden");
  }
}

function populateProductFilter() {
  const products = [...new Set(ALL_JOBS.map((j) => j.product).filter(Boolean))].sort();
  const sel = $("filterProduct");
  const prev = sel.value;
  sel.innerHTML = '<option value="">全部</option>' + products.map((p) => `<option value="${escapeHtml(p)}">${escapeHtml(p)}</option>`).join("");
  if (products.includes(prev)) sel.value = prev;
}

async function renderBatches() {
  const productFilter = $("filterProduct").value;
  const jobs = productFilter ? ALL_JOBS.filter((j) => j.product === productFilter) : ALL_JOBS;

  // group while preserving reverse-chronological order; jobs from the same
  // batch were created back-to-back so they naturally cluster together
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

  $("batchCount").textContent = batches.length;
  const grid = $("historyGrid");

  if (batches.length === 0) {
    grid.innerHTML = '<div class="muted" style="grid-column:1/-1;padding:20px;text-align:center;">没有匹配的生成记录</div>';
    return;
  }

  // building each card is now synchronous (no more fetch+blob before we can
  // even insert an <img> into the DOM) -- the browser loads/parallelizes/
  // caches the actual thumbnail requests itself once the cards are inserted.
  grid.innerHTML = "";
  batches.forEach((batch) => grid.appendChild(renderBatchCard(batch)));
}

function renderBatchCard(batch) {
  const firstJob = batch.jobs[0];
  const totalImages = batch.jobs.reduce((s, j) => s + j.output_images.length, 0);
  const totalCost = batch.jobs.reduce((s, j) => s + j.cost, 0);
  const anyFailed = batch.jobs.some((j) => j.status === "failed");
  const kinds = [...new Set(batch.jobs.map((j) => j.kind))];
  const product = batch.jobs.find((j) => j.product)?.product || "";
  const chosen = HISTORY_SELECTED.has(batch.batch_id);

  const thumbJobs = [];
  for (const job of batch.jobs) {
    for (let i = 0; i < job.output_images.length; i++) {
      thumbJobs.push([job.id, i]);
      if (thumbJobs.length >= 6) break;
    }
    if (thumbJobs.length >= 6) break;
  }
  const thumbsHtml = thumbJobs.length
    ? `<div class="thumb-list">${thumbJobs.map(([jobId, i]) => `<img src="${API.generationImageUrl(jobId, i, { thumb: true })}" loading="lazy" />`).join("")}</div>`
    : '<div class="muted" style="padding:20px;text-align:center;">无图片</div>';

  const card = document.createElement("div");
  card.className = "gen-card";
  card.style.gridColumn = "span 2";
  card.innerHTML = `
    <div style="padding:10px;">${thumbsHtml}</div>
    <div class="meta">
      <label class="row" style="font-size:12px;">
        <input type="checkbox" ${chosen ? "checked" : ""} /> 选择打包（多批一起下载）
      </label>
      <div class="tags" style="margin:4px 0;">
        ${kinds.map((k) => `<span class="tag">${KIND_LABELS[k] || k}</span>`).join("")}
        ${product ? `<span class="tag">${escapeHtml(product)}</span>` : ""}
      </div>
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
  const downloadBtn = card.querySelector('[data-act=download-batch]');
  downloadBtn.addEventListener("click", () => downloadBatches([batch.batch_id], downloadBtn));
  return card;
}

async function downloadBatches(batchIds, triggerBtn) {
  const btns = [triggerBtn, $("downloadSelectedBtn")].filter(Boolean);
  const originalTexts = btns.map((b) => b.textContent);
  btns.forEach((b) => { b.disabled = true; b.textContent = "打包下载中…"; });
  try {
    const token = API.getToken();
    const resp = await fetch("/api/generations/batch-download", {
      method: "POST",
      headers: { "Content-Type": "application/json", Authorization: "Bearer " + token },
      body: JSON.stringify({ batch_ids: batchIds }),
    });
    if (!resp.ok) {
      let msg = "下载失败";
      try { msg = (await resp.json()).detail || msg; } catch (e) {}
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
    btns.forEach((b, i) => { b.disabled = false; b.textContent = originalTexts[i]; });
  }
}

$("downloadSelectedBtn").addEventListener("click", (e) => {
  if (HISTORY_SELECTED.size === 0) {
    alert("请先勾选要下载的批次");
    return;
  }
  downloadBatches([...HISTORY_SELECTED], e.currentTarget);
});

function escapeHtml(s) {
  return (s || "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}
