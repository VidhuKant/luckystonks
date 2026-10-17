const WATCH = ["RELIANCE", "TCS", "INFY", "WIPRO", "HDFCBANK", "TATAMOTORS", "BHARTIARTL", "ITC", "SBIN"];
let selectedSymbol = "RELIANCE";
let me = null;
let clusterCache = null;
const PEER_LOG_IDS = [0, 1, 2];
const logPeerState = {
  0: { filter: "all", entries: [] },
  1: { filter: "all", entries: [] },
  2: { filter: "all", entries: [] },
};
const logSockets = { 0: null, 1: null, 2: null };

function $(id) {
  return document.getElementById(id);
}

function showToast(msg, isErr = false) {
  const el = document.createElement("div");
  el.className = "toast" + (isErr ? " err" : "");
  el.textContent = msg;
  document.body.appendChild(el);
  setTimeout(() => el.remove(), 5000);
}

async function api(path, opts = {}) {
  const res = await fetch(path, {
    credentials: "include",
    headers: { "Content-Type": "application/json", ...(opts.headers || {}) },
    ...opts,
  });
  if (res.status === 401 && !path.includes("/auth/login")) {
    showLogin();
    throw new Error("session expired");
  }
  const text = await res.text();
  let data = null;
  try {
    data = text ? JSON.parse(text) : null;
  } catch {
    data = { detail: text };
  }
  if (!res.ok) {
    throw new Error(data.detail || data.message || res.statusText);
  }
  return data;
}

function isAdminUser() {
  return me && me.role === "admin";
}

function updateAdminTabVisibility() {
  const tab = $("tab-admin");
  if (!tab) return;
  if (isAdminUser()) tab.classList.remove("hidden");
  else {
    tab.classList.add("hidden");
    if ($("view-admin").classList.contains("active")) setView("trade");
  }
}

function formatUserPill() {
  if (!me) return "NOT LOGGED IN";
  const roleTag = me.role === "admin" ? " · ADMIN" : "";
  return `${me.user_id.toUpperCase()}${roleTag} · PEER ${me.connected_peer} · :${me.connected_port}`;
}

function setView(name) {
  document.querySelectorAll(".view").forEach((v) => v.classList.remove("active"));
  document.querySelectorAll(".nav-tabs button").forEach((b) => b.classList.remove("active"));
  disconnectAllLogWs();
  if (name === "trade") {
    $("view-trade").classList.add("active");
    $("tab-trade").classList.add("active");
  } else if (name === "admin") {
    if (!isAdminUser()) {
      showToast("Admin tab requires admin login", true);
      setView("trade");
      return;
    }
    $("view-admin").classList.add("active");
    $("tab-admin").classList.add("active");
    refreshAdmin();
  } else {
    $("view-ops").classList.add("active");
    $("tab-ops").classList.add("active");
    refreshOps();
    connectAllLogWs();
  }
}

function showLogin() {
  me = null;
  $("trade-main").classList.add("hidden");
  $("login-wrap").classList.remove("hidden");
  $("user-pill").textContent = "NOT LOGGED IN";
  updateAdminTabVisibility();
}

function showTradeMain() {
  $("login-wrap").classList.add("hidden");
  $("trade-main").classList.remove("hidden");
}

async function tryRestoreSession() {
  try {
    me = await api("/api/auth/me");
    $("user-pill").textContent = formatUserPill();
    updateAdminTabVisibility();
    showTradeMain();
    await refreshTrade();
  } catch {
    showLogin();
  }
}

async function doLogin(e) {
  e.preventDefault();
  $("login-error").textContent = "";
  const username = $("login-user").value.trim();
  const password = $("login-pass").value;
  try {
    me = await api("/api/auth/login", {
      method: "POST",
      body: JSON.stringify({ username, password }),
    });
    $("user-pill").textContent = formatUserPill();
    updateAdminTabVisibility();
    showTradeMain();
    await refreshTrade();
  } catch (err) {
    $("login-error").textContent = err.message;
  }
}

async function doLogout() {
  try {
    await api("/api/auth/logout", { method: "POST" });
  } catch {
    /* ignore */
  }
  showLogin();
}

function renderWatchlist() {
  const el = $("watchlist");
  el.innerHTML = "";
  WATCH.forEach((sym) => {
    const div = document.createElement("div");
    div.className = "watch-item" + (sym === selectedSymbol ? " selected" : "");
    div.textContent = sym;
    div.onclick = () => {
      selectedSymbol = sym;
      $("order-symbol").value = sym;
      renderWatchlist();
      loadBook();
    };
    el.appendChild(div);
  });
}

/** gRPC Get returns a list of items; PORTFOLIO/BOOK use a single object in one element. */
function unwrapGetPayload(data) {
  if (Array.isArray(data)) {
    if (data.length === 1 && data[0] && typeof data[0] === "object" && !Array.isArray(data[0])) {
      return data[0];
    }
    return data;
  }
  return data;
}

function tableFromRows(headers, rows) {
  if (!rows || !rows.length) return "<p style='color:#666'>— no data —</p>";
  let html = "<table class='data'><thead><tr>";
  headers.forEach((h) => (html += `<th>${h}</th>`));
  html += "</tr></thead><tbody>";
  rows.forEach((r) => {
    html += "<tr>";
    r.forEach((c, i) => {
      const cls = typeof c === "object" && c.cls ? c.cls : "";
      const val = typeof c === "object" ? c.v : c;
      html += `<td class="${cls}">${val}</td>`;
    });
    html += "</tr>";
  });
  html += "</tbody></table>";
  return html;
}

async function loadPortfolio() {
  const p = unwrapGetPayload(await api("/api/trade/portfolio"));
  const rows = [];
  if (p.cash != null) rows.push([{ v: "CASH" }, { v: p.cash }]);
  const shares = p.shares || {};
  Object.keys(shares)
    .sort()
    .forEach((s) => rows.push([{ v: s }, { v: shares[s] }]));
  $("portfolio-panel").innerHTML = tableFromRows(["Asset", "Qty/Value"], rows);
}

async function loadBook() {
  const sym = selectedSymbol;
  $("book-sym").textContent = sym;
  const payload = unwrapGetPayload(await api(`/api/trade/book?symbol=${encodeURIComponent(sym)}`));
  const book =
    payload[sym] ||
    (payload.bids || payload.asks ? payload : null) ||
    payload[Object.keys(payload || {})[0]] ||
    { bids: [], asks: [] };
  const rows = [];
  (book.asks || [])
    .slice()
    .reverse()
    .forEach((o) =>
      rows.push([
        { v: "ASK", cls: "sell" },
        { v: o.symbol || sym },
        { v: o.price },
        { v: o.remaining_qty ?? o.qty },
      ])
    );
  (book.bids || []).forEach((o) =>
    rows.push([
      { v: "BID", cls: "buy" },
      { v: o.symbol || sym },
      { v: o.price },
      { v: o.remaining_qty ?? o.qty },
    ])
  );
  $("book-panel").innerHTML = tableFromRows(["Side", "Sym", "Px", "Qty"], rows);
}

async function loadTrades() {
  const trades = await api("/api/trade/trades");
  const rows = (trades || []).slice(-30).reverse().map((t) => [
    { v: t.trade_id },
    { v: t.symbol },
    { v: t.price },
    { v: t.qty },
    { v: `${t.buyer_id}/${t.seller_id}` },
  ]);
  $("tape-panel").innerHTML = tableFromRows(["ID", "Sym", "Px", "Qty", "Buy/Sell"], rows);
}

async function loadOrders() {
  const orders = await api("/api/trade/orders");
  const rows = (orders || []).map((o) => [
    { v: o.order_id },
    { v: o.side, cls: o.side === "BUY" ? "buy" : "sell" },
    { v: o.symbol },
    { v: o.price },
    { v: o.remaining_qty ?? o.qty },
    { v: o.status || "OPEN" },
  ]);
  $("orders-mini").innerHTML = tableFromRows(["ID", "Side", "Sym", "Px", "Qty", "St"], rows);
}

async function refreshTrade() {
  if (!me) return;
  await Promise.all([loadPortfolio(), loadBook(), loadTrades(), loadOrders()]);
}

async function submitOrder(e) {
  e.preventDefault();
  const side = $("order-side").value;
  const symbol = $("order-symbol").value.trim().toUpperCase();
  const price = parseInt($("order-price").value, 10);
  const qty = parseInt($("order-qty").value, 10);
  try {
    const res = await api("/api/trade/order", {
      method: "POST",
      body: JSON.stringify({ side, symbol, price, qty }),
    });
    let msg = `ORDER ${res.status}: ${res.detail}`;
    if (res.routed_to_leader) {
      msg += ` · routed follower :${res.connected_port} → leader :${res.leader_port}`;
    }
    showToast(msg);
    await refreshTrade();
  } catch (err) {
    showToast(err.message, true);
  }
}

async function askInsight() {
  const q = $("insight-query").value.trim();
  if (!q) return;
  $("insight-answer").textContent = "Loading…";
  try {
    const res = await api("/api/trade/insight", {
      method: "POST",
      body: JSON.stringify({ query: q }),
    });
    $("insight-answer").textContent = res.answer;
  } catch (err) {
    $("insight-answer").textContent = err.message;
  }
}

async function refreshClusterBadge() {
  try {
    clusterCache = await api("/api/ops/cluster");
    const leader = clusterCache.leader_peer_id;
    const pill = $("cluster-pill");
    if (leader == null) {
      pill.textContent = "CLUSTER · LEADER ELECTING…";
      pill.className = "status-pill";
    } else {
      pill.textContent = `LEADER PEER ${leader} · CLIENT → PEER ${clusterCache.client_trading_port - 50051}`;
      pill.className = "status-pill leader";
    }
  } catch {
    $("cluster-pill").textContent = "OPS OFFLINE";
  }
}

function renderPeerCards(data) {
  const wrap = $("peer-cards");
  wrap.innerHTML = "";
  (data.peers || []).forEach((p) => {
    const card = document.createElement("div");
    card.className = "peer-card";
    if (p.role === "LEADER") card.classList.add("leader");
    if (!p.trading_up || !p.raft_up) card.classList.add("down");
    card.innerHTML = `
      <div class="peer-title">
        <strong>PEER ${p.peer_id}</strong>
        <span class="status-pill ${p.role === "LEADER" ? "leader" : p.role === "FOLLOWER" ? "follower" : "down"}">${p.role}</span>
      </div>
      <div class="metric-row"><span>Trading</span><span class="val">:${p.trading_port} ${p.trading_up ? "UP" : "DOWN"}</span></div>
      <div class="metric-row"><span>Raft</span><span class="val">:${p.raft_port} ${p.raft_up ? "UP" : "DOWN"}</span></div>
      <div class="metric-row"><span>Term / Commit</span><span class="val">${p.term ?? "—"} / ${p.commit_index ?? "—"}</span></div>
      <div class="metric-row"><span>Log / Snap</span><span class="val">${p.log_len ?? "—"} / ${p.snapshot_index ?? 0}</span></div>
      <div class="metric-row"><span>PID</span><span class="val">${p.pid ?? "—"}</span></div>
      <div class="ops-actions">
        <button type="button" data-log="${p.peer_id}">Logs</button>
        <button type="button" class="danger" data-stop="${p.peer_id}">Stop</button>
        <button type="button" data-start="${p.peer_id}">Start</button>
      </div>`;
    wrap.appendChild(card);
  });
  wrap.querySelectorAll("[data-log]").forEach((btn) => {
    btn.onclick = () => {
      const pid = btn.getAttribute("data-log");
      const col = document.querySelector(`.log-column[data-peer="${pid}"]`);
      if (col) col.scrollIntoView({ behavior: "smooth", block: "nearest", inline: "center" });
    };
  });
  wrap.querySelectorAll("[data-stop]").forEach((btn) => {
    btn.onclick = async () => {
      const id = btn.getAttribute("data-stop");
      const clientPeer =
        clusterCache && clusterCache.client_trading_port
          ? clusterCache.client_trading_port - 50051
          : 1;
      if (parseInt(id, 10) === clientPeer) {
        showToast(
          `Note: peer ${id} is the UI client port (:${clusterCache.client_trading_port}). Stop only for failover demo; use Start to bring it back.`,
          true
        );
      }
      try {
        await api(`/api/ops/peers/${id}/stop`, { method: "POST" });
        showToast(`Stopped peer ${id} only (other peers unchanged)`);
        refreshOps();
      } catch (err) {
        showToast(err.message, true);
      }
    };
  });
  wrap.querySelectorAll("[data-start]").forEach((btn) => {
    btn.onclick = async () => {
      const id = btn.getAttribute("data-start");
      try {
        await api(`/api/ops/peers/${id}/start`, { method: "POST" });
        showToast(`Started peer ${id}`);
        setTimeout(refreshOps, 2000);
      } catch (err) {
        showToast(err.message, true);
      }
    };
  });
}

function renderLogLinesForPeer(peerId) {
  const state = logPeerState[peerId];
  const view = $(`log-view-${peerId}`);
  if (!view) return;
  const filtered =
    state.filter === "all"
      ? state.entries
      : state.entries.filter((e) => e.kind === state.filter);
  view.innerHTML = filtered
    .map((e) => `<div class="log-line ${e.kind}">${escapeHtml(e.line)}</div>`)
    .join("");
  view.scrollTop = view.scrollHeight;
}

function escapeHtml(s) {
  return s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}

async function loadLogSnapshot(peerId) {
  const data = await api(`/api/ops/logs/${peerId}?lines=400`);
  logPeerState[peerId].entries = data.entries || [];
  renderLogLinesForPeer(peerId);
}

async function loadAllLogSnapshots() {
  await Promise.all(PEER_LOG_IDS.map((pid) => loadLogSnapshot(pid)));
}

function connectLogWs(peerId) {
  if (logSockets[peerId]) {
    logSockets[peerId].close();
    logSockets[peerId] = null;
  }
  const proto = location.protocol === "https:" ? "wss" : "ws";
  const socket = new WebSocket(`${proto}://${location.host}/ws/logs/${peerId}`);
  logSockets[peerId] = socket;
  socket.onmessage = (ev) => {
    try {
      const msg = JSON.parse(ev.data);
      const state = logPeerState[peerId];
      state.entries.push(msg);
      if (state.entries.length > 600) state.entries.shift();
      if (state.filter === "all" || msg.kind === state.filter) {
        const view = $(`log-view-${peerId}`);
        if (!view) return;
        const div = document.createElement("div");
        div.className = `log-line ${msg.kind}`;
        div.textContent = msg.line;
        view.appendChild(div);
        while (view.childNodes.length > 600) view.removeChild(view.firstChild);
        view.scrollTop = view.scrollHeight;
      }
    } catch {
      /* ignore */
    }
  };
}

function connectAllLogWs() {
  PEER_LOG_IDS.forEach((pid) => connectLogWs(pid));
}

function disconnectAllLogWs() {
  PEER_LOG_IDS.forEach((pid) => {
    if (logSockets[pid]) {
      logSockets[pid].close();
      logSockets[pid] = null;
    }
  });
}

async function refreshOps() {
  try {
    const data = await api("/api/ops/cluster");
    clusterCache = data;
    renderPeerCards(data);
    await loadAllLogSnapshots();
  } catch (err) {
    showToast(`Refresh failed: ${err.message}`, true);
  }
}

async function checkParity() {
  try {
    const res = await api("/api/ops/parity");
    showToast(res.parity ? "TRADES PARITY OK" : "TRADES PARITY MISMATCH", !res.parity);
  } catch (err) {
    showToast(err.message, true);
  }
}

async function loadAdminPortfolios() {
  const rows = [];
  const users = await api("/api/admin/portfolios");
  (users || []).forEach((u) => {
    rows.push([
      { v: u.user_id },
      { v: u.role || "user" },
      { v: u.cash },
      { v: JSON.stringify(u.shares || {}) },
    ]);
  });
  $("admin-portfolios-panel").innerHTML = tableFromRows(["User", "Role", "Cash", "Shares"], rows);
}

async function loadAdminOrderLog() {
  const entries = await api("/api/admin/order-log");
  const rows = (entries || [])
    .slice()
    .reverse()
    .slice(0, 200)
    .map((e) => [
      { v: e.log_id },
      { v: e.user_id },
      { v: e.side, cls: e.side === "BUY" ? "buy" : "sell" },
      { v: e.symbol },
      { v: e.price },
      { v: e.qty },
      { v: e.status },
      { v: e.order_id || "—" },
    ]);
  $("admin-order-log-panel").innerHTML = tableFromRows(
    ["Log", "User", "Side", "Sym", "Px", "Qty", "Status", "Order"],
    rows
  );
}

async function refreshAdmin() {
  if (!isAdminUser()) return;
  try {
    await Promise.all([loadAdminPortfolios(), loadAdminOrderLog()]);
  } catch (err) {
    showToast(`Admin refresh failed: ${err.message}`, true);
  }
}

async function adminResetMarket() {
  const confirm = $("admin-reset-confirm").value.trim();
  if (confirm !== "YES") {
    showToast('Type YES in the confirmation box', true);
    return;
  }
  try {
    const res = await api("/api/admin/reset", { method: "POST", body: "{}" });
    showToast(res.detail || "Market reset OK");
    $("admin-reset-confirm").value = "";
    showLogin();
  } catch (err) {
    showToast(err.message, true);
  }
}

function syncClusterAddrDefaults() {
  const peerId = parseInt($("cluster-peer-id").value, 10) || 0;
  if ($("cluster-action").value === "add") {
    $("cluster-raft-addr").value = `127.0.0.1:${60051 + peerId}`;
    $("cluster-trading-addr").value = `127.0.0.1:${50051 + peerId}`;
  }
}

async function submitClusterChange(e) {
  e.preventDefault();
  $("admin-cluster-result").textContent = "";
  const body = {
    action: $("cluster-action").value,
    peer_id: parseInt($("cluster-peer-id").value, 10),
    raft_addr: $("cluster-raft-addr").value.trim(),
    trading_addr: $("cluster-trading-addr").value.trim(),
  };
  try {
    const res = await api("/api/admin/cluster-change", {
      method: "POST",
      body: JSON.stringify(body),
    });
    $("admin-cluster-result").textContent = `${res.status}: ${res.detail || "ok"}`;
    showToast(res.detail || "Cluster change submitted");
  } catch (err) {
    $("admin-cluster-result").textContent = err.message;
    showToast(err.message, true);
  }
}

function init() {
  renderWatchlist();
  $("order-symbol").value = selectedSymbol;
  $("login-form").addEventListener("submit", doLogin);
  $("logout-btn").addEventListener("click", doLogout);
  $("order-form").addEventListener("submit", submitOrder);
  $("insight-btn").addEventListener("click", askInsight);
  $("tab-trade").onclick = () => setView("trade");
  $("tab-ops").onclick = () => setView("ops");
  $("tab-admin").onclick = () => setView("admin");
  $("refresh-ops").onclick = refreshOps;
  $("refresh-admin").onclick = refreshAdmin;
  $("parity-btn").onclick = checkParity;
  $("admin-reset-btn").onclick = adminResetMarket;
  $("admin-cluster-form").addEventListener("submit", submitClusterChange);
  $("cluster-peer-id").addEventListener("change", syncClusterAddrDefaults);
  $("cluster-action").addEventListener("change", syncClusterAddrDefaults);
  syncClusterAddrDefaults();
  document.querySelectorAll(".log-tabs button").forEach((btn) => {
    btn.onclick = () => {
      const peerId = parseInt(btn.getAttribute("data-peer"), 10);
      const filter = btn.getAttribute("data-filter");
      const column = btn.closest(".log-column");
      if (column) {
        column.querySelectorAll(".log-tabs button").forEach((b) => b.classList.remove("active"));
      }
      btn.classList.add("active");
      logPeerState[peerId].filter = filter;
      renderLogLinesForPeer(peerId);
    };
  });
  tryRestoreSession();
  setInterval(refreshClusterBadge, 2000);
  setInterval(() => {
    if (me && $("view-trade").classList.contains("active")) refreshTrade();
  }, 8000);
  setInterval(() => {
    if ($("view-ops").classList.contains("active")) refreshOps();
  }, 4000);
  setInterval(() => {
    if ($("view-admin").classList.contains("active") && isAdminUser()) refreshAdmin();
  }, 8000);
}

document.addEventListener("DOMContentLoaded", init);
