const WATCH = ["RELIANCE", "TCS", "INFY", "WIPRO", "HDFCBANK", "TATAMOTORS", "BHARTIARTL", "ITC", "SBIN"];
let selectedSymbol = "RELIANCE";
let me = null;
let clusterCache = null;
let PEER_LOG_IDS = [];
const logPeerState = {};
const logSockets = {};

function dash(v) {
  return v === null || v === undefined || v === "" ? "—" : v;
}

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

function ensureOpsLogColumns(size) {
  const grid = $("ops-logs-grid");
  if (!grid) return;
  const ids = Array.from({ length: size }, (_, i) => i);
  const same =
    PEER_LOG_IDS.length === ids.length && PEER_LOG_IDS.every((v, i) => v === ids[i]);
  if (same && grid.children.length === size) return;
  disconnectAllLogWs();
  opsLogsBootstrapped = false;
  PEER_LOG_IDS = ids;
  ids.forEach((pid) => {
    if (!logPeerState[pid]) logPeerState[pid] = { filter: "all", entries: [] };
    logSockets[pid] = null;
  });
  Object.keys(logPeerState).forEach((k) => {
    if (!ids.includes(Number(k))) delete logPeerState[k];
  });
  grid.innerHTML = ids
    .map(
      (pid) => `
    <div class="panel log-column" data-peer="${pid}">
      <div class="panel-head">Cluster logs · peer ${pid}</div>
      <div class="log-tabs">
        <button type="button" class="active" data-peer="${pid}" data-filter="all">All</button>
        <button type="button" data-peer="${pid}" data-filter="election">Elections</button>
        <button type="button" data-peer="${pid}" data-filter="general">General</button>
      </div>
      <div class="log-view" id="log-view-${pid}"></div>
    </div>`
    )
    .join("");
  grid.querySelectorAll(".log-tabs button").forEach((btn) => {
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
}

async function refreshClusterBadge() {
  try {
    clusterCache = await api("/api/ops/cluster");
    ensureOpsLogColumns(clusterCache.cluster_size || (clusterCache.peers || []).length || 5);
    const leader = clusterCache.leader_peer_id;
    const pill = $("cluster-pill");
    const meta = $("ops-cluster-meta");
    if (meta) {
      meta.textContent = `CLUSTER_SIZE=${clusterCache.cluster_size} · quorum ${clusterCache.quorum} · paper metrics · failover demo`;
    }
    if (leader == null) {
      pill.textContent = `CLUSTER×${clusterCache.cluster_size} · LEADER ELECTING…`;
      pill.className = "status-pill";
    } else {
      pill.textContent = `LEADER PEER ${leader} · N=${clusterCache.cluster_size} · CLIENT → :${clusterCache.client_trading_port}`;
      pill.className = "status-pill leader";
    }
  } catch {
    $("cluster-pill").textContent = "OPS OFFLINE";
  }
}

let timerTickHandle = null;
let timerSoftRefreshHandle = null;
let timerSoftRefreshInFlight = false;
let timerSoftRefreshQueued = false;

function formatTimerSeconds(sec) {
  if (sec == null || Number.isNaN(sec)) return "—";
  const s = Math.max(0, sec);
  return s.toFixed(1) + "s";
}

function timerSnapshotFromPeer(p, fetchedAt) {
  const raft = p.raft || {};
  if (!(p.trading_up && p.raft_up)) {
    return { mode: "down", deadline: null, remaining: null, total: 0, meta: "", label: "Election timer" };
  }
  if (p.role === "LEADER") {
    const total = Number(raft.heartbeatIntervalSec) || 0.5;
    let remaining = raft.heartbeatRemainingSec;
    let deadline = raft.heartbeatDeadlineAt != null ? Number(raft.heartbeatDeadlineAt) : NaN;
    if (!Number.isFinite(deadline) && remaining != null) {
      deadline = fetchedAt + Math.max(0, Number(remaining) || 0);
    }
    if (remaining == null && Number.isFinite(deadline)) {
      remaining = deadline - fetchedAt;
    }
    remaining = Math.max(0, Number(remaining) || 0);
    if (!Number.isFinite(deadline)) deadline = fetchedAt + remaining;
    return {
      mode: "heartbeat",
      deadline,
      remaining,
      total,
      meta: `every ${formatTimerSeconds(total)}`,
      label: "Heartbeat",
    };
  }
  const drawn = Number(raft.electionTimeoutSec);
  const lo = raft.electionTimeoutMin ?? 3;
  const hi = raft.electionTimeoutMax ?? 5;
  const total = Number.isFinite(drawn) && drawn > 0 ? drawn : hi;
  let remaining = raft.electionRemainingSec;
  let deadline = raft.electionDeadlineAt != null ? Number(raft.electionDeadlineAt) : NaN;
  if (!Number.isFinite(deadline) && remaining != null) {
    deadline = fetchedAt + Math.max(0, Number(remaining) || 0);
  }
  if (remaining == null && Number.isFinite(deadline)) {
    remaining = deadline - fetchedAt;
  }
  remaining = Math.max(0, Number(remaining) || 0);
  if (!Number.isFinite(deadline)) deadline = fetchedAt + remaining;
  return {
    mode: "election",
    deadline,
    remaining,
    total,
    meta: `drawn ${formatTimerSeconds(drawn)} · range ${lo}–${hi}s`,
    label: "Election timeout",
  };
}

function timerRemainingFromEl(el, now) {
  // Prefer absolute wall deadline so slow API fetches don't skew the countdown.
  const deadline = parseFloat(el.getAttribute("data-deadline"));
  if (Number.isFinite(deadline)) return deadline - now;
  const rem0 = parseFloat(el.getAttribute("data-remaining"));
  const fetchedAt = parseFloat(el.getAttribute("data-fetched-at"));
  if (Number.isFinite(rem0) && Number.isFinite(fetchedAt)) {
    return rem0 - (now - fetchedAt);
  }
  return NaN;
}

function applyTimerEl(el, snap, fetchedAt) {
  if (!el || !snap || snap.mode === "down") return;
  el.setAttribute("data-mode", snap.mode);
  el.setAttribute("data-deadline", String(snap.deadline));
  el.setAttribute("data-remaining", String(snap.remaining));
  el.setAttribute("data-fetched-at", String(fetchedAt));
  el.setAttribute("data-total", String(snap.total));
  el.classList.toggle("leader", snap.mode === "heartbeat");
  const meta = el.querySelector(".peer-timer-meta");
  if (meta) meta.textContent = snap.meta;
  const label = el.querySelector(".peer-timer-label");
  if (label) label.textContent = snap.label;
}

function patchPeerTimersFromCluster(data) {
  const fetchedAt = Date.now() / 1000;
  let patched = 0;
  (data.peers || []).forEach((p) => {
    const card = document.querySelector(`.peer-card[data-peer-id="${p.peer_id}"]`);
    if (!card) return;
    const el = card.querySelector(".peer-timer");
    if (!el || el.classList.contains("down")) return;
    const snap = timerSnapshotFromPeer(p, fetchedAt);
    if (snap.mode === "down") return;
    // Role/mode mismatch (leader↔follower) needs a full card rebuild.
    const curMode = el.getAttribute("data-mode");
    if (curMode && curMode !== snap.mode) return;
    applyTimerEl(el, snap, fetchedAt);
    patched += 1;
  });
  if (patched) tickPeerTimers();
  return patched;
}

function scheduleTimerSoftRefresh() {
  if (timerSoftRefreshHandle || timerSoftRefreshInFlight) {
    timerSoftRefreshQueued = true;
    return;
  }
  if (!$("view-ops") || !$("view-ops").classList.contains("active")) return;
  timerSoftRefreshHandle = setTimeout(async () => {
    timerSoftRefreshHandle = null;
    if (timerSoftRefreshInFlight) {
      timerSoftRefreshQueued = true;
      return;
    }
    timerSoftRefreshInFlight = true;
    timerSoftRefreshQueued = false;
    try {
      const data = await api("/api/ops/cluster");
      clusterCache = data;
      // Patch deadlines in place — full rebuild only on role/UP changes.
      if (peerCardsNeedRebuild(data)) renderPeerCards(data);
      else patchPeerTimersFromCluster(data);
    } catch {
      /* ignore transient */
    } finally {
      timerSoftRefreshInFlight = false;
      if (timerSoftRefreshQueued) scheduleTimerSoftRefresh();
    }
  }, 250);
}

function tickPeerTimers() {
  const now = Date.now() / 1000;
  let needRefresh = false;
  document.querySelectorAll(".peer-timer[data-mode]").forEach((el) => {
    if (el.classList.contains("down")) return;
    const total = parseFloat(el.getAttribute("data-total") || "0");
    const mode = el.getAttribute("data-mode") || "election";
    let remaining = timerRemainingFromEl(el, now);
    if (!Number.isFinite(remaining)) return;

    const valueEl = el.querySelector(".peer-timer-value");
    const fillEl = el.querySelector(".peer-timer-fill");

    if (remaining <= 0) {
      needRefresh = true;
      if (valueEl) {
        valueEl.textContent = mode === "heartbeat" ? "sending…" : "sync…";
      }
      if (fillEl && total > 0) {
        fillEl.style.width = "100%";
        fillEl.classList.remove("empty", "urgent");
        fillEl.classList.add("syncing");
      }
      el.classList.remove("expired");
      el.classList.add("syncing");
      return;
    }

    el.classList.remove("syncing", "expired");
    if (valueEl) valueEl.textContent = formatTimerSeconds(remaining);
    if (fillEl && total > 0) {
      const pct = Math.max(0, Math.min(100, (remaining / total) * 100));
      fillEl.style.width = pct + "%";
      fillEl.classList.remove("empty", "syncing");
      fillEl.classList.toggle("urgent", remaining < 1.0);
    }
  });
  if (needRefresh) scheduleTimerSoftRefresh();
}

function startPeerTimerTicks() {
  if (timerTickHandle) return;
  timerTickHandle = setInterval(tickPeerTimers, 100);
}

function renderTimerPanel(p, raft) {
  const fetchedAt = Date.now() / 1000;
  const snap = timerSnapshotFromPeer(p, fetchedAt);
  if (snap.mode === "down") {
    return `<div class="peer-timer down"><div class="peer-timer-label">Election timer</div><div class="peer-timer-value">OFFLINE</div></div>`;
  }
  const cls = snap.mode === "heartbeat" ? "peer-timer leader" : "peer-timer";
  const pct = snap.total ? Math.min(100, (snap.remaining / snap.total) * 100) : 0;
  return `
    <div class="${cls}" data-mode="${snap.mode}" data-deadline="${snap.deadline}" data-remaining="${snap.remaining}" data-fetched-at="${fetchedAt}" data-total="${snap.total}">
      <div class="peer-timer-head">
        <span class="peer-timer-label">${snap.label}</span>
        <span class="peer-timer-meta">${snap.meta}</span>
      </div>
      <div class="peer-timer-value">${formatTimerSeconds(snap.remaining)}</div>
      <div class="peer-timer-bar"><div class="peer-timer-fill" style="width:${pct}%"></div></div>
    </div>`;
}

function renderFollowerTables(raft) {
  if (!raft || (!raft.nextIndex && !raft.matchIndex)) return "";
  const next = raft.nextIndex || {};
  const match = raft.matchIndex || {};
  const keys = Array.from(
    new Set([...Object.keys(next), ...Object.keys(match)])
  ).sort((a, b) => Number(a) - Number(b));
  if (!keys.length) return "";
  const rows = keys
    .map(
      (k) =>
        `<tr><td>peer ${k}</td><td class="val">${dash(next[k])}</td><td class="val">${dash(match[k])}</td></tr>`
    )
    .join("");
  return `
    <div class="peer-section-label">Leader tracking (Fig. 2)</div>
    <table class="follower-table">
      <thead><tr><th>Follower</th><th>nextIndex</th><th>matchIndex</th></tr></thead>
      <tbody>${rows}</tbody>
    </table>`;
}

function peerCardsNeedRebuild(data) {
  const wrap = $("peer-cards");
  if (!wrap) return true;
  const peers = data.peers || [];
  const existing = [...wrap.querySelectorAll(".peer-card[data-peer-id]")];
  if (existing.length !== peers.length) return true;
  for (let i = 0; i < peers.length; i++) {
    const p = peers[i];
    const card = existing[i];
    if (!card || card.getAttribute("data-peer-id") !== String(p.peer_id)) return true;
    if (card.getAttribute("data-role") !== String(p.role || "")) return true;
    const up = !!(p.trading_up && p.raft_up);
    if (card.classList.contains("down") === up) return true;
  }
  return false;
}

function patchPeerCardsMetrics(data) {
  (data.peers || []).forEach((p) => {
    const card = document.querySelector(`.peer-card[data-peer-id="${p.peer_id}"]`);
    if (!card) return;
    const raft = p.raft || {};
    const up = !!(p.trading_up && p.raft_up);
    const setVal = (label, text) => {
      const rows = card.querySelectorAll(".metric-row");
      for (const row of rows) {
        const span = row.querySelector(":scope > span:first-child");
        if (span && span.textContent === label) {
          const val = row.querySelector(".val");
          if (val) val.textContent = text;
          return;
        }
      }
    };
    setVal("Trading", `:${p.trading_port} ${p.trading_up ? "UP" : "DOWN"}`);
    setVal("Raft RPC", `:${p.raft_port} ${p.raft_up ? "UP" : "DOWN"}`);
    setVal("currentTerm", String(dash(raft.currentTerm ?? p.term)));
    setVal("votedFor", String(dash(raft.votedFor)));
    setVal("commitIndex", String(dash(raft.commitIndex ?? p.commit_index)));
    setVal("lastApplied", String(dash(raft.lastApplied)));
    setVal("lastLogIndex", String(dash(raft.lastLogIndex)));
    setVal("lastLogTerm", String(dash(raft.lastLogTerm)));
    setVal("logLen", String(dash(raft.logLen ?? p.log_len)));
    setVal("snapshotIdx", String(dash(raft.snapshotLastIncludedIndex ?? p.snapshot_index)));
    setVal("PID", String(dash(p.pid)));
    const stopBtn = card.querySelector("[data-stop]");
    const startBtn = card.querySelector("[data-start]");
    if (stopBtn) stopBtn.disabled = !up;
    if (startBtn) startBtn.disabled = up;
    if (p.role === "LEADER") {
      const actions = card.querySelector(".ops-actions");
      const html = renderFollowerTables(raft);
      card.querySelectorAll(".peer-section-label").forEach((el) => {
        if (el.textContent.includes("Leader tracking")) {
          const table = el.nextElementSibling;
          el.remove();
          if (table && table.classList.contains("follower-table")) table.remove();
        }
      });
      card.querySelectorAll(".follower-table").forEach((el) => el.remove());
      if (html && actions) {
        const tmp = document.createElement("div");
        tmp.innerHTML = html;
        while (tmp.firstChild) actions.parentNode.insertBefore(tmp.firstChild, actions);
      }
    }
  });
  patchPeerTimersFromCluster(data);
}

function renderPeerCards(data) {
  const wrap = $("peer-cards");
  wrap.innerHTML = "";
  (data.peers || []).forEach((p) => {
    const raft = p.raft || {};
    const up = !!(p.trading_up && p.raft_up);
    const card = document.createElement("div");
    card.className = "peer-card";
    card.setAttribute("data-peer-id", String(p.peer_id));
    card.setAttribute("data-role", String(p.role || ""));
    if (p.role === "LEADER") card.classList.add("leader");
    if (!up) card.classList.add("down");
    const roleClass =
      p.role === "LEADER"
        ? "leader"
        : p.role === "FOLLOWER"
          ? "follower"
          : p.role === "CANDIDATE"
            ? "follower"
            : "down";
    const stopDisabled = up ? "" : "disabled";
    const startDisabled = up ? "disabled" : "";
    card.innerHTML = `
      <div class="peer-title">
        <strong>PEER ${p.peer_id}</strong>
        <span class="status-pill ${roleClass}">${p.role}</span>
      </div>
      ${renderTimerPanel(p, raft)}
      <div class="metric-grid">
        <div class="metric-row"><span>Trading</span><span class="val">:${p.trading_port} ${p.trading_up ? "UP" : "DOWN"}</span></div>
        <div class="metric-row"><span>Raft RPC</span><span class="val">:${p.raft_port} ${p.raft_up ? "UP" : "DOWN"}</span></div>
        <div class="metric-row"><span>currentTerm</span><span class="val">${dash(raft.currentTerm ?? p.term)}</span></div>
        <div class="metric-row"><span>votedFor</span><span class="val">${dash(raft.votedFor)}</span></div>
        <div class="metric-row"><span>commitIndex</span><span class="val">${dash(raft.commitIndex ?? p.commit_index)}</span></div>
        <div class="metric-row"><span>lastApplied</span><span class="val">${dash(raft.lastApplied)}</span></div>
        <div class="metric-row"><span>lastLogIndex</span><span class="val">${dash(raft.lastLogIndex)}</span></div>
        <div class="metric-row"><span>lastLogTerm</span><span class="val">${dash(raft.lastLogTerm)}</span></div>
        <div class="metric-row"><span>logLen</span><span class="val">${dash(raft.logLen ?? p.log_len)}</span></div>
        <div class="metric-row"><span>snapshotIdx</span><span class="val">${dash(raft.snapshotLastIncludedIndex ?? p.snapshot_index)}</span></div>
        <div class="metric-row span-2"><span>PID</span><span class="val">${dash(p.pid)}</span></div>
      </div>
      ${p.role === "LEADER" ? renderFollowerTables(raft) : ""}
      <div class="ops-actions">
        <button type="button" data-log="${p.peer_id}">Logs</button>
        <button type="button" class="danger" data-stop="${p.peer_id}" ${stopDisabled}>Stop</button>
        <button type="button" data-start="${p.peer_id}" ${startDisabled}>Start</button>
      </div>`;
    wrap.appendChild(card);
  });
  startPeerTimerTicks();
  tickPeerTimers();
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
  const existing = logSockets[peerId];
  if (existing && (existing.readyState === WebSocket.OPEN || existing.readyState === WebSocket.CONNECTING)) {
    return;
  }
  if (existing) {
    try {
      existing.close();
    } catch {
      /* ignore */
    }
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

let opsLogsBootstrapped = false;

async function refreshOps() {
  try {
    const data = await api("/api/ops/cluster");
    clusterCache = data;
    ensureOpsLogColumns(data.cluster_size || (data.peers || []).length || 5);
    const meta = $("ops-cluster-meta");
    if (meta) {
      meta.textContent = `CLUSTER_SIZE=${data.cluster_size} · quorum ${data.quorum} · paper metrics · failover demo`;
    }
    if (peerCardsNeedRebuild(data)) {
      renderPeerCards(data);
    } else {
      patchPeerCardsMetrics(data);
    }
    // Bootstrap logs once; live updates come from WebSockets. Re-fetching +
    // reconnecting every 1s flooded the server and froze the Ops tab.
    if (!opsLogsBootstrapped) {
      await loadAllLogSnapshots();
      opsLogsBootstrapped = true;
    }
    if ($("view-ops").classList.contains("active")) connectAllLogWs();
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
  const size = (clusterCache && clusterCache.cluster_size) || 5;
  if (!$("cluster-peer-id").dataset.touched) {
    $("cluster-peer-id").value = String(size);
  }
}

function setDefaultClusterPeerId() {
  const size = (clusterCache && clusterCache.cluster_size) || 5;
  if ($("cluster-peer-id") && !$("cluster-peer-id").dataset.touched) {
    $("cluster-peer-id").value = String(size);
    syncClusterAddrDefaults();
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
  $("cluster-peer-id").addEventListener("change", () => {
    $("cluster-peer-id").dataset.touched = "1";
    syncClusterAddrDefaults();
  });
  $("cluster-action").addEventListener("change", syncClusterAddrDefaults);
  syncClusterAddrDefaults();
  tryRestoreSession();
  refreshClusterBadge().then(() => setDefaultClusterPeerId());
  setInterval(refreshClusterBadge, 2000);
  setInterval(() => {
    if (me && $("view-trade").classList.contains("active")) refreshTrade();
  }, 8000);
  setInterval(() => {
    if ($("view-ops").classList.contains("active")) refreshOps();
  }, 1000);
  startPeerTimerTicks();
  setInterval(() => {
    if ($("view-admin").classList.contains("active") && isAdminUser()) refreshAdmin();
  }, 8000);
}

document.addEventListener("DOMContentLoaded", init);
