const API = (() => {
  const TOKEN_KEY = "pis_token";

  function getToken() {
    return localStorage.getItem(TOKEN_KEY);
  }
  function setToken(t) {
    localStorage.setItem(TOKEN_KEY, t);
  }
  function clearToken() {
    localStorage.removeItem(TOKEN_KEY);
  }
  function isLoggedIn() {
    return !!getToken();
  }

  async function request(path, { method = "GET", body, isForm = false, headers = {} } = {}) {
    const token = getToken();
    const finalHeaders = { ...headers };
    if (token) finalHeaders["Authorization"] = "Bearer " + token;
    let finalBody = body;
    if (body && !isForm) {
      finalHeaders["Content-Type"] = "application/json";
      finalBody = JSON.stringify(body);
    }
    const resp = await fetch(path, { method, headers: finalHeaders, body: finalBody });
    if (resp.status === 401) {
      clearToken();
      renderAuthState();
      throw new Error("登录已过期，请重新登录");
    }
    let data = null;
    const ct = resp.headers.get("content-type") || "";
    if (ct.includes("application/json")) {
      data = await resp.json();
    }
    if (!resp.ok) {
      const msg = (data && (data.detail || data.message)) || `请求失败 (${resp.status})`;
      throw new Error(typeof msg === "string" ? msg : JSON.stringify(msg));
    }
    return data !== null ? data : resp;
  }

  return {
    getToken, setToken, clearToken, isLoggedIn,
    register: (username, password) => request("/api/auth/register", { method: "POST", body: { username, password } }),
    // NOTE: /api/auth/register now returns {status:"active"|"pending", message, access_token?}
    login: (username, password) => request("/api/auth/login", { method: "POST", body: { username, password } }),
    me: () => request("/api/auth/me"),
    regenerateRelayKey: () => request("/api/auth/relay-key/regenerate", { method: "POST" }),

    templateFilters: (params = {}) => {
      const qs = new URLSearchParams();
      for (const key of ["season", "scene", "product", "region"]) {
        (params[key] || []).forEach((v) => qs.append(key, v));
      }
      if (params.mine_only) qs.append("mine_only", "true");
      return request("/api/templates/filters?" + qs.toString());
    },
    listTemplates: (params) => {
      const qs = new URLSearchParams();
      for (const key of ["season", "scene", "product", "region"]) {
        (params[key] || []).forEach((v) => qs.append(key, v));
      }
      if (params.mine_only) qs.append("mine_only", "true");
      return request("/api/templates?" + qs.toString());
    },
    getTemplate: (id) => request(`/api/templates/${id}`),
    createTemplate: (payload, asSystem = false) =>
      request(`/api/templates?as_system=${asSystem}`, { method: "POST", body: payload }),
    updateTemplate: (id, payload) => request(`/api/templates/${id}`, { method: "PUT", body: payload }),
    deleteTemplate: (id) => request(`/api/templates/${id}`, { method: "DELETE" }),

    generate: (formData) => request("/api/generate", { method: "POST", body: formData, isForm: true }),
    remixGenerateOne: (formData) => request("/api/generate/remix", { method: "POST", body: formData, isForm: true }),
    listGenerations: (params = {}) => {
      const qs = new URLSearchParams();
      qs.append("page", params.page || 1);
      qs.append("page_size", params.page_size || 20);
      if (params.kind) qs.append("kind", params.kind);
      if (params.days) qs.append("days", params.days);
      return request("/api/generations?" + qs.toString());
    },
    batchDownload: (batchIds) => request("/api/generations/batch-download", { method: "POST", body: { batch_ids: batchIds } }),

    // ---- 二创套图模板 ----
    remixFilters: (params = {}) => {
      const qs = new URLSearchParams();
      if (params.mine_only) qs.append("mine_only", "true");
      return request("/api/remix-templates/filters?" + qs.toString());
    },
    listRemixTemplates: (params = {}) => {
      const qs = new URLSearchParams();
      (params.product || []).forEach((v) => qs.append("product", v));
      if (params.mine_only) qs.append("mine_only", "true");
      return request("/api/remix-templates?" + qs.toString());
    },
    getRemixTemplate: (id) => request(`/api/remix-templates/${id}`),
    remixBackgroundImageUrl: (id) => `/api/remix-templates/${id}/background-image`,
    createRemixTemplate: (formData) => request("/api/remix-templates", { method: "POST", body: formData, isForm: true }),
    updateRemixTemplate: (id, formData) => request(`/api/remix-templates/${id}`, { method: "PUT", body: formData, isForm: true }),
    deleteRemixTemplate: (id) => request(`/api/remix-templates/${id}`, { method: "DELETE" }),

    adminListUsers: () => request("/api/admin/users"),
    adminUpdateUser: (id, payload) => request(`/api/admin/users/${id}`, { method: "PUT", body: payload }),
    adminApproveUser: (id) => request(`/api/admin/users/${id}/approve`, { method: "POST" }),
    adminDeleteUser: (id) => request(`/api/admin/users/${id}`, { method: "DELETE" }),
    adminAllTemplates: (params = {}) => {
      const qs = new URLSearchParams();
      (params.season || []).forEach((v) => qs.append("season", v));
      (params.product || []).forEach((v) => qs.append("product", v));
      if (params.owner) qs.append("owner", params.owner);
      return request("/api/admin/templates?" + qs.toString());
    },
    adminAllRemixTemplates: () => request("/api/admin/remix-templates"),
    adminGetConfig: () => request("/api/admin/config"),
    adminUpdateConfig: (payload) => request("/api/admin/config", { method: "PUT", body: payload }),
    adminStats: () => request("/api/admin/stats"),

    adminListProviders: () => request("/api/admin/providers"),
    adminCreateProvider: (payload) => request("/api/admin/providers", { method: "POST", body: payload }),
    adminUpdateProvider: (id, payload) => request(`/api/admin/providers/${id}`, { method: "PUT", body: payload }),
    adminActivateProvider: (id) => request(`/api/admin/providers/${id}/activate`, { method: "POST" }),
    adminDeleteProvider: (id) => request(`/api/admin/providers/${id}`, { method: "DELETE" }),
    adminProviderModels: (id) => request(`/api/admin/providers/${id}/models`),

    adminAllProducts: () => request("/api/admin/products"),
    adminGetUserProductAccess: (userId) => request(`/api/admin/users/${userId}/product-access`),
    adminSetUserProductAccess: (userId, products) =>
      request(`/api/admin/users/${userId}/product-access`, { method: "PUT", body: { products } }),
  };
})();

function renderAuthState() {
  // overridden by page-level scripts
}
