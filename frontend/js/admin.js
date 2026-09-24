const $ = (id) => document.getElementById(id);

let ALL_USERS = [];
let ALL_PRODUCTS = [];
let CURRENT_TEMPLATES = [];
let EDITING_TEMPLATE_ID = null;

const TPL_FIELD_DEFS = [
  ["subject", "主体"], ["style", "风格"], ["photography", "摄影"], ["atmosphere", "氛围"],
  ["background", "背景"], ["light", "光线"], ["negative", "负面"], ["parameters", "参数"],
];

document.addEventListener("DOMContentLoaded", init);

async function init() {
  if (!API.isLoggedIn()) {
    window.location.href = "/index.html";
    return;
  }
  $("logoutBtn").addEventListener("click", () => { API.clearToken(); window.location.href = "/index.html"; });

  let me;
  try {
    me = await API.me();
  } catch (e) {
    window.location.href = "/index.html";
    return;
  }
  if (!me.is_admin) {
    $("deniedView").classList.remove("hidden");
    return;
  }
  $("adminView").classList.remove("hidden");

  try {
    await Promise.all([loadStats(), loadConfig(), loadProviders(), loadUsers(), loadProducts(), loadTemplates(), loadRemixTemplatesAdmin()]);
  } catch (e) {
    console.error("failed to load some admin panel data:", e);
  }
}

async function loadStats() {
  const s = await API.adminStats();
  const row = $("statsRow");
  row.innerHTML = `
    <div><div class="muted">用户总数</div><div style="font-size:22px;">${s.total_users}</div></div>
    <div><div class="muted">累计生成</div><div style="font-size:22px;">${s.total_generations}</div></div>
    <div><div class="muted">累计成本</div><div style="font-size:22px;">¥${s.total_cost.toFixed(2)}</div></div>
    <div><div class="muted">今日生成</div><div style="font-size:22px;">${s.today_generations}</div></div>
    <div><div class="muted">今日成本</div><div style="font-size:22px;">¥${s.today_cost.toFixed(2)}</div></div>
  `;
}

async function loadConfig() {
  const cfg = await API.adminGetConfig();
  $("cfgCost").value = cfg.default_cost_per_image;
  $("cfgQuota").value = cfg.default_daily_quota;
}

$("saveCfgBtn").addEventListener("click", async () => {
  await API.adminUpdateConfig({
    default_cost_per_image: parseFloat($("cfgCost").value),
    default_daily_quota: parseFloat($("cfgQuota").value),
  });
  $("cfgSaved").classList.remove("hidden");
  setTimeout(() => $("cfgSaved").classList.add("hidden"), 2000);
});

// ---------------- providers ----------------
const PROVIDER_KIND_LABELS = { sync_edit: "同步编辑接口", toapis_async: "ToAPIs 异步任务" };

function maskKey(key) {
  if (!key) return "-";
  if (key.length <= 8) return key;
  return key.slice(0, 6) + "…" + key.slice(-4);
}

async function loadProviders() {
  $("providerError").classList.add("hidden");
  const providers = await API.adminListProviders();
  const body = $("providersBody");
  body.innerHTML = "";
  if (providers.length === 0) {
    body.innerHTML = '<tr><td colspan="7" class="muted">还没有配置任何供应商，在下面添加一个。</td></tr>';
    return;
  }
  providers.forEach((p) => {
    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td>${escapeHtml(p.name)}</td>
      <td>${PROVIDER_KIND_LABELS[p.kind] || escapeHtml(p.kind)}</td>
      <td style="max-width:200px;word-break:break-all;">${escapeHtml(p.base_url)}</td>
      <td><code class="key">${escapeHtml(maskKey(p.api_key))}</code></td>
      <td>
        <input type="text" data-field="image_model" value="${escapeHtml(p.image_model)}" style="width:110px;" />
        <button class="btn secondary" data-act="refresh-models" style="padding:2px 6px;font-size:11px;" title="从这个供应商拉取真实模型列表">刷新</button>
        <div class="muted" data-role="models-list" style="font-size:11px;max-width:160px;"></div>
      </td>
      <td>${p.is_active ? '<span class="tag system">当前使用</span>' : '<span class="tag">未启用</span>'}</td>
      <td>
        ${p.is_active ? "" : '<button class="btn secondary" data-act="activate" style="padding:4px 8px;font-size:12px;">设为当前使用</button>'}
        <button class="btn secondary" data-act="save-model" style="padding:4px 8px;font-size:12px;">保存模型</button>
        <button class="btn secondary" data-act="delete" style="padding:4px 8px;font-size:12px;">删除</button>
      </td>
    `;
    const activateBtn = tr.querySelector('[data-act=activate]');
    if (activateBtn) {
      activateBtn.addEventListener("click", async () => {
        await API.adminActivateProvider(p.id);
        await loadProviders();
      });
    }
    tr.querySelector('[data-act=save-model]').addEventListener("click", async () => {
      const image_model = tr.querySelector('[data-field=image_model]').value.trim() || "gpt-image-2";
      await API.adminUpdateProvider(p.id, { image_model });
      await loadProviders();
    });
    tr.querySelector('[data-act=refresh-models]').addEventListener("click", async () => {
      const listEl = tr.querySelector('[data-role=models-list]');
      listEl.textContent = "加载中…";
      try {
        const result = await API.adminProviderModels(p.id);
        const ids = (result.data || []).map((m) => m.id).slice(0, 30);
        listEl.textContent = ids.length ? ids.join("、") : "（供应商没有返回模型）";
      } catch (err) {
        listEl.textContent = "获取失败：" + err.message;
      }
    });
    tr.querySelector('[data-act=delete]').addEventListener("click", async () => {
      if (!confirm(`确定删除供应商 "${p.name}" 吗？`)) return;
      await API.adminDeleteProvider(p.id);
      await loadProviders();
    });
    body.appendChild(tr);
  });
}

$("addProviderBtn").addEventListener("click", async () => {
  $("providerError").classList.add("hidden");
  const name = $("newProviderName").value.trim();
  const baseUrl = $("newProviderBaseUrl").value.trim();
  const apiKey = $("newProviderApiKey").value.trim();
  const imageModel = $("newProviderModel").value.trim() || "gpt-image-2";
  if (!name || !baseUrl || !apiKey) {
    $("providerError").textContent = "名称、Base URL、密钥都必须填写";
    $("providerError").classList.remove("hidden");
    return;
  }
  try {
    await API.adminCreateProvider({
      name,
      kind: $("newProviderKind").value,
      base_url: baseUrl,
      api_key: apiKey,
      image_model: imageModel,
    });
    $("newProviderName").value = "";
    $("newProviderBaseUrl").value = "";
    $("newProviderApiKey").value = "";
    await loadProviders();
  } catch (err) {
    $("providerError").textContent = err.message;
    $("providerError").classList.remove("hidden");
  }
});

// ---------------- users (+ pending approval) ----------------
async function loadUsers() {
  const users = await API.adminListUsers();
  ALL_USERS = users;

  const pending = users.filter((u) => !u.is_approved);
  $("pendingCount").textContent = pending.length;
  $("pendingEmpty").classList.toggle("hidden", pending.length > 0);
  const pendingBody = $("pendingBody");
  pendingBody.innerHTML = "";
  pending.forEach((u) => {
    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td>${escapeHtml(u.username)}</td>
      <td>${new Date(u.created_at + "Z").toLocaleString()}</td>
      <td>
        <button class="btn" style="padding:4px 10px;font-size:12px;" data-act="approve">通过</button>
        <button class="btn secondary" style="padding:4px 10px;font-size:12px;" data-act="reject">拒绝并删除</button>
      </td>
    `;
    tr.querySelector('[data-act=approve]').addEventListener("click", async () => {
      await API.adminApproveUser(u.id);
      await loadUsers();
      await loadStats();
    });
    tr.querySelector('[data-act=reject]').addEventListener("click", async () => {
      if (!confirm(`确定拒绝并删除账号 "${u.username}" 吗？`)) return;
      await API.adminDeleteUser(u.id);
      await loadUsers();
      await loadStats();
    });
    pendingBody.appendChild(tr);
  });

  const body = $("usersBody");
  body.innerHTML = "";
  users.forEach((u) => {
    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td>${escapeHtml(u.username)}</td>
      <td>${u.is_approved ? '<span class="tag" style="background:#dcfce7;color:#166534;">已通过</span>' : '<span class="tag" style="background:#fef3c7;color:#92400e;">待审核</span>'}</td>
      <td><input type="checkbox" data-field="is_admin" ${u.is_admin ? "checked" : ""} /></td>
      <td><input type="number" step="1" data-field="daily_quota" value="${u.daily_quota}" /></td>
      <td><input type="number" step="0.01" data-field="cost_per_image" value="${u.cost_per_image}" /></td>
      <td>${u.used_today.toFixed(2)}</td>
      <td>${u.total_generated}</td>
      <td>¥${u.total_cost.toFixed(2)}</td>
      <td>${new Date(u.created_at + "Z").toLocaleDateString()}</td>
      <td><button class="btn secondary" style="padding:4px 10px;font-size:12px;">保存</button></td>
    `;
    tr.querySelector("button").addEventListener("click", async () => {
      const payload = {
        is_admin: tr.querySelector('[data-field=is_admin]').checked,
        daily_quota: parseFloat(tr.querySelector('[data-field=daily_quota]').value),
        cost_per_image: parseFloat(tr.querySelector('[data-field=cost_per_image]').value),
      };
      await API.adminUpdateUser(u.id, payload);
      await loadUsers();
      await loadStats();
    });
    body.appendChild(tr);
  });

  const sel = $("paUserSelect");
  const prevValue = sel.value;
  sel.innerHTML = "";
  users.forEach((u) => {
    const opt = document.createElement("option");
    opt.value = u.id;
    opt.textContent = u.username;
    sel.appendChild(opt);
  });
  if (prevValue) sel.value = prevValue;
}

// ---------------- product permissions ----------------
async function loadProducts() {
  const result = await API.adminAllProducts();
  ALL_PRODUCTS = result.products || [];
}

async function renderProductChips(checkedSet) {
  const el = $("paProductChips");
  el.innerHTML = "";
  if (ALL_PRODUCTS.length === 0) {
    el.innerHTML = '<span class="muted">还没有任何产品（先在套图模板/二创模板里建一些）</span>';
    return;
  }
  ALL_PRODUCTS.forEach((p) => {
    const chip = document.createElement("div");
    chip.className = "chip" + (checkedSet.has(p) ? " active" : "");
    chip.textContent = p;
    chip.dataset.product = p;
    chip.onclick = () => chip.classList.toggle("active");
    el.appendChild(chip);
  });
}

$("paLoadBtn").addEventListener("click", async () => {
  const userId = $("paUserSelect").value;
  if (!userId) return;
  const access = await API.adminGetUserProductAccess(userId);
  await renderProductChips(new Set(access.products));
});

$("paSaveBtn").addEventListener("click", async () => {
  const userId = $("paUserSelect").value;
  if (!userId) return;
  const products = [...document.querySelectorAll('#paProductChips .chip.active')].map((c) => c.dataset.product);
  await API.adminSetUserProductAccess(userId, products);
  $("paSaved").classList.remove("hidden");
  setTimeout(() => $("paSaved").classList.add("hidden"), 2000);
});

// ---------------- templates (filters + usage stats + inline edit) ----------------
function populateSelectOptions(selectEl, values, placeholder) {
  const prev = selectEl.value;
  selectEl.innerHTML = `<option value="">${placeholder}</option>`;
  values.forEach((v) => {
    const opt = document.createElement("option");
    opt.value = v;
    opt.textContent = v;
    selectEl.appendChild(opt);
  });
  if (values.includes(prev)) selectEl.value = prev;
}

async function loadTemplates() {
  const seasonFilter = $("tplFilterSeason").value;
  const productFilter = $("tplFilterProduct").value;
  const ownerFilter = $("tplFilterOwner").value;

  const templates = await API.adminAllTemplates({
    season: seasonFilter ? [seasonFilter] : [],
    product: productFilter ? [productFilter] : [],
    owner: ownerFilter || undefined,
  });
  CURRENT_TEMPLATES = templates;

  if (!seasonFilter) {
    const seasons = [...new Set(templates.map((t) => t.season).filter(Boolean))];
    populateSelectOptions($("tplFilterSeason"), seasons, "全部");
  }
  if (!productFilter) {
    const products = [...new Set(templates.map((t) => t.product).filter(Boolean))];
    populateSelectOptions($("tplFilterProduct"), products, "全部");
  }
  // owner dropdown: system + every username seen among custom templates
  const ownerSel = $("tplFilterOwner");
  const prevOwner = ownerSel.value;
  const usernames = [...new Set(templates.filter((t) => !t.is_system && t.owner_username).map((t) => t.owner_username))];
  ownerSel.innerHTML = '<option value="">全部</option><option value="system">系统</option>' +
    usernames.map((u) => `<option value="${escapeHtml(u)}">${escapeHtml(u)}</option>`).join("");
  if (prevOwner) ownerSel.value = prevOwner;

  const body = $("templatesBody");
  body.innerHTML = "";
  templates.forEach((t) => {
    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td>${escapeHtml(t.name)}</td>
      <td>${t.is_system ? "系统" : "用户 " + escapeHtml(t.owner_username || ("#" + t.owner_id))}</td>
      <td>${escapeHtml(t.season)}</td>
      <td>${escapeHtml(t.scene)}</td>
      <td>${escapeHtml(t.product)}</td>
      <td>${escapeHtml(t.region)}</td>
      <td>${t.usage_7d}</td>
      <td>${t.usage_30d}</td>
      <td><button class="btn secondary" data-act="edit" style="padding:4px 10px;font-size:12px;">编辑</button></td>
    `;
    tr.querySelector('[data-act=edit]').addEventListener("click", () => openTemplateEditor(t));
    body.appendChild(tr);
  });
}

$("tplFilterSeason").addEventListener("change", loadTemplates);
$("tplFilterProduct").addEventListener("change", loadTemplates);
$("tplFilterOwner").addEventListener("change", loadTemplates);

function openTemplateEditor(t) {
  $("tplEditorError").classList.add("hidden");
  EDITING_TEMPLATE_ID = t.id;
  $("tplEditName").value = t.name;
  $("tplEditSeason").value = t.season;
  $("tplEditScene").value = t.scene;
  $("tplEditProduct").value = t.product;
  $("tplEditRegion").value = t.region;

  const container = $("tplEditFields");
  container.innerHTML = "";
  TPL_FIELD_DEFS.forEach(([key, label]) => {
    const wrap = document.createElement("div");
    const lbl = document.createElement("label");
    lbl.className = "field-label";
    lbl.textContent = `【${label}】`;
    const ta = document.createElement("textarea");
    ta.id = "tplEditField_" + key;
    ta.value = t[key] || "";
    wrap.appendChild(lbl);
    wrap.appendChild(ta);
    container.appendChild(wrap);
  });

  $("tplEditorPanel").classList.remove("hidden");
  $("tplEditorPanel").scrollIntoView({ behavior: "smooth", block: "nearest" });
}

$("tplCancelBtn").addEventListener("click", () => $("tplEditorPanel").classList.add("hidden"));

$("tplSaveBtn").addEventListener("click", async () => {
  if (!EDITING_TEMPLATE_ID) return;
  $("tplEditorError").classList.add("hidden");
  const payload = {
    name: $("tplEditName").value,
    season: $("tplEditSeason").value,
    scene: $("tplEditScene").value,
    product: $("tplEditProduct").value,
    region: $("tplEditRegion").value,
  };
  TPL_FIELD_DEFS.forEach(([key]) => { payload[key] = $("tplEditField_" + key).value; });
  try {
    await API.updateTemplate(EDITING_TEMPLATE_ID, payload);
    $("tplEditorPanel").classList.add("hidden");
    await loadTemplates();
  } catch (err) {
    $("tplEditorError").textContent = err.message;
    $("tplEditorError").classList.remove("hidden");
  }
});

// ---------------- remix templates (read-only overview; edit happens on /remix.html) ----------------
async function loadRemixTemplatesAdmin() {
  const templates = await API.adminAllRemixTemplates();
  const body = $("remixTemplatesBody");
  body.innerHTML = "";
  templates.forEach((t) => {
    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td>${escapeHtml(t.name)}</td>
      <td>${t.is_system ? "系统" : "用户 #" + t.owner_id}</td>
      <td>${escapeHtml(t.product)}</td>
      <td style="max-width:320px;">${escapeHtml(t.prompt)}</td>
    `;
    body.appendChild(tr);
  });
}

function escapeHtml(s) {
  return (s || "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}
