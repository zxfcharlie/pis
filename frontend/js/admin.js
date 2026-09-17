const $ = (id) => document.getElementById(id);

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

  await Promise.all([loadStats(), loadConfig(), loadUsers(), loadTemplates()]);
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

async function loadUsers() {
  const users = await API.adminListUsers();
  const body = $("usersBody");
  body.innerHTML = "";
  users.forEach((u) => {
    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td>${escapeHtml(u.username)}</td>
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
}

async function loadTemplates() {
  const templates = await API.adminAllTemplates();
  const body = $("templatesBody");
  body.innerHTML = "";
  templates.forEach((t) => {
    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td>${escapeHtml(t.name)}</td>
      <td>${t.is_system ? "系统" : "用户 #" + t.owner_id}</td>
      <td>${escapeHtml(t.season)}</td>
      <td>${escapeHtml(t.scene)}</td>
      <td>${escapeHtml(t.product)}</td>
      <td>${escapeHtml(t.region)}</td>
    `;
    body.appendChild(tr);
  });
}

function escapeHtml(s) {
  return (s || "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}
