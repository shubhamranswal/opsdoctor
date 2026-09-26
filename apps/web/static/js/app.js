/**
 * OpsDoctor - Modern SaaS Operations Frontend Controller
 * Manages tabs, conversational workspace, payments hub, action center, and system diagnostics.
 */

// Global State
let currentSessionId = "ops-session-" + Math.random().toString(36).substring(2, 9);
let isGenerating = false;
let pendingApprovalsCount = 0;
let cachedTransactions = [];

document.addEventListener("DOMContentLoaded", () => {
  initSidebarTabs();
  initChatInput();
  initQuickPrompts();
  initGlobalSearch();
  initPaymentsFilters();
  
  // Initial data loading
  loadSystemStatus();
  loadApprovals();
  loadPulseData();
  loadPaymentsData();
});

// ---------------- 1. Sidebar Tab Navigation ----------------
function initSidebarTabs() {
  const navItems = document.querySelectorAll(".sidebar-nav .nav-item");
  navItems.forEach((btn) => {
    btn.addEventListener("click", () => {
      const tabId = btn.getAttribute("data-tab");
      switchTab(tabId);
    });
  });

  const headerBtn = document.getElementById("header-action-center-btn");
  if (headerBtn) {
    headerBtn.addEventListener("click", () => switchTab("approvals"));
  }
}

function switchTab(tabId) {
  const navItems = document.querySelectorAll(".sidebar-nav .nav-item");
  navItems.forEach((b) => {
    if (b.getAttribute("data-tab") === tabId) {
      b.classList.add("active");
    } else {
      b.classList.remove("active");
    }
  });

  const titles = {
    ask: { title: "Ask OpsDoctor", sub: "Autonomous Business Operations Copilot" },
    pulse: { title: "Operations Pulse", sub: "Real-time Telemetry & KPIs" },
    payments: { title: "Payments Hub", sub: "Unified PayPal & Stripe Ledger" },
    investigations: { title: "Investigations", sub: "Cross-System Root Cause Triage" },
    approvals: { title: "Action Center", sub: "Human-in-the-Loop Authorization Queue" },
    systems: { title: "Connected Integrations", sub: "Swytchcode Capabilities & Auth" },
    settings: { title: "Diagnostics & Config", sub: "Runtime Environment & Status" },
  };

  if (titles[tabId]) {
    document.getElementById("current-view-title").innerText = titles[tabId].title;
    document.getElementById("current-view-subtitle").innerText = titles[tabId].sub;
  }

  document.querySelectorAll(".tab-view").forEach((view) => {
    view.classList.remove("active");
    if (view.id === `${tabId}-view`) {
      view.classList.add("active");
    }
  });

  // Lazy load views
  if (tabId === "pulse") loadPulseData();
  if (tabId === "payments") loadPaymentsData();
  if (tabId === "approvals") loadApprovals();
  if (tabId === "systems") loadSystemStatus();
}

// ---------------- 2. Global Search ----------------
function initGlobalSearch() {
  const input = document.getElementById("global-search-input");
  if (!input) return;

  window.addEventListener("keydown", (e) => {
    if ((e.metaKey || e.ctrlKey) && e.key === "k") {
      e.preventDefault();
      input.focus();
    }
  });

  input.addEventListener("keydown", (e) => {
    if (e.key === "Enter" && input.value.trim()) {
      const q = input.value.trim();
      input.value = "";
      switchTab("ask");
      const chatInput = document.getElementById("chat-input");
      if (chatInput) {
        chatInput.value = q;
        handleSendMessage();
      }
    }
  });
}

// ---------------- 3. Chat Input & Messaging ----------------
function initChatInput() {
  const textarea = document.getElementById("chat-input");
  const sendBtn = document.getElementById("btn-send");

  textarea.addEventListener("input", () => {
    textarea.style.height = "auto";
    textarea.style.height = Math.min(textarea.scrollHeight, 140) + "px";
  });

  textarea.addEventListener("keydown", (e) => {
    if (e.isComposing || e.keyCode === 229) return;
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSendMessage();
    }
  });

  sendBtn.addEventListener("click", () => handleSendMessage());
}

function initQuickPrompts() {
  document.querySelectorAll(".prompt-chip").forEach((chip) => {
    chip.addEventListener("click", () => {
      const promptText = chip.getAttribute("data-prompt") || chip.innerText.trim();
      const textarea = document.getElementById("chat-input");
      textarea.value = promptText;
      handleSendMessage();
    });
  });
}

function runInvestigationPrompt() {
  switchTab("ask");
  const textarea = document.getElementById("chat-input");
  textarea.value = "Investigate why checkout payments are failing";
  handleSendMessage();
}

async function handleSendMessage() {
  const textarea = document.getElementById("chat-input");
  const text = textarea.value.trim();
  if (!text || isGenerating) return;

  textarea.value = "";
  textarea.style.height = "auto";
  isGenerating = true;

  appendUserCard(text);

  // Create loading assistant card
  const assistantCard = createAssistantCard();
  const thread = document.getElementById("chat-thread");
  thread.appendChild(assistantCard);
  thread.scrollTop = thread.scrollHeight;

  const contentArea = assistantCard.querySelector(".card-text-area");
  const traceAccordion = assistantCard.querySelector(".trace-accordion");
  const traceDetails = assistantCard.querySelector(".trace-details");
  const approvalArea = assistantCard.querySelector(".card-approval-area");
  const badgeArea = assistantCard.querySelector(".execution-badge-container");

  try {
    const res = await fetch("/api/agent/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ session_id: currentSessionId, message: text }),
    });

    if (!res.ok) throw new Error(`HTTP error ${res.status}`);
    const data = await res.json();

    // Render badge
    const toolsUsed = (data.activities || [])
      .filter((a) => a.step_type === "tool_selection" && a.data?.tool)
      .map((a) => a.data.tool);

    const systemsUsed = [...new Set((data.evidence || []).map((e) => e.system))];
    const badgeText = systemsUsed.length > 0 
      ? `⚡ Inspected ${systemsUsed.map(s => s.toUpperCase()).join(" & ")} via Swytchcode (${toolsUsed.length} tools)`
      : `⚡ OpsDoctor Analysis Complete`;

    badgeArea.innerHTML = `<span class="execution-badge">${badgeText}</span>`;

    // Render text content
    contentArea.innerHTML = formatMarkdown(data.content);

    // Populate Progressive Disclosure Trace Accordion - CONTEXTUAL & COLLAPSED BY DEFAULT
    if (data.activities && data.activities.length > 0) {
      traceAccordion.style.display = "block";
      traceDetails.innerHTML = "";
      traceDetails.style.display = "none"; // Explicitly collapsed by default
      const caret = traceAccordion.querySelector(".trace-caret");
      if (caret) caret.innerText = "▼";

      data.activities.forEach((act) => {
        const item = document.createElement("div");
        item.className = "trace-step-item";
        item.innerHTML = `
          <span class="trace-step-icon">▸</span>
          <div>
            <strong>${escapeHtml(act.title)}</strong>: 
            <span>${escapeHtml(act.description)}</span>
          </div>
        `;
        traceDetails.appendChild(item);
      });
    } else {
      traceAccordion.style.display = "none";
    }

    // Action handling:
    // Clear approval area for this assistant response
    approvalArea.innerHTML = "";

    // Explicit response type check:
    const respType = data.response_type || (data.approvals && data.approvals.length > 0 ? "ACTION_PROPOSAL" : "READ_ONLY");
    const actions = (data.actions && data.actions.length > 0) ? data.actions : (data.approvals || []);

    // Only render action card if this response explicitly proposes an action
    if (respType === "ACTION_PROPOSAL" && actions.length > 0) {
      actions.forEach((act) => {
        approvalArea.appendChild(createApprovalCardElement(act));
      });
    }

    // Refresh action center counters
    loadApprovals();

  } catch (err) {
    contentArea.innerHTML = `<div style="color:var(--rose-500)">⚠️ Error during investigation turn: ${escapeHtml(err.message)}</div>`;
  } finally {
    isGenerating = false;
    thread.scrollTop = thread.scrollHeight;
  }
}

function appendUserCard(text) {
  const thread = document.getElementById("chat-thread");
  const card = document.createElement("div");
  card.className = "message-card user";
  card.innerHTML = `<div class="user-bubble">${escapeHtml(text)}</div>`;
  thread.appendChild(card);
}

function createAssistantCard() {
  const card = document.createElement("div");
  card.className = "message-card assistant";
  card.innerHTML = `
    <div class="card-avatar">🩺</div>
    <div class="card-content">
      <div class="execution-badge-container">
        <span class="execution-badge">⚡ OpsDoctor Reasoning...</span>
      </div>
      <div class="card-text-area markdown-body">
        <div style="color:var(--text-muted);font-style:italic;">Querying connected capabilities...</div>
      </div>
      <div class="card-approval-area"></div>
      <div class="trace-accordion" style="display:none;">
        <div class="trace-summary" onclick="toggleTrace(this)">
          <span>🔍 Inspect Execution Trace &amp; Tool Calls</span>
          <span class="trace-caret">▼</span>
        </div>
        <div class="trace-details" style="display:none;"></div>
      </div>
    </div>
  `;
  return card;
}

function toggleTrace(headerEl) {
  const details = headerEl.nextElementSibling;
  const caret = headerEl.querySelector(".trace-caret");
  if (details.style.display === "none") {
    details.style.display = "flex";
    if (caret) caret.innerText = "▲";
  } else {
    details.style.display = "none";
    if (caret) caret.innerText = "▼";
  }
}

// ---------------- 4. Action Center / Approvals Lifecycle ----------------
async function loadApprovals() {
  try {
    const res = await fetch(`/api/approvals?session_id=${encodeURIComponent(currentSessionId)}`);
    const data = await res.json();
    const reqs = Array.isArray(data) ? data : (data.requests || []);
    const pending = reqs.filter((r) => (r.status || "").toUpperCase() === "PENDING");
    pendingApprovalsCount = pending.length;

    // Update Badges
    const sideBadge = document.getElementById("sidebar-approvals-badge");
    const headBadge = document.getElementById("header-approvals-count");
    if (sideBadge) {
      sideBadge.style.display = pendingApprovalsCount > 0 ? "inline-block" : "none";
      sideBadge.innerText = pendingApprovalsCount;
    }
    if (headBadge) {
      headBadge.style.display = pendingApprovalsCount > 0 ? "inline-block" : "none";
      headBadge.innerText = pendingApprovalsCount;
    }

    const container = document.getElementById("approvals-list-container");
    if (!container) return;

    if (reqs.length === 0) {
      container.innerHTML = `<div class="glass-panel text-center py-6" style="color:var(--text-muted)">No actions currently pending approval. Read-only queries do not generate action cards.</div>`;
      return;
    }

    container.innerHTML = "";
    reqs.forEach((req) => {
      container.appendChild(createApprovalCardElement(req));
    });
  } catch (e) {
    console.error("Failed loading approvals:", e);
  }
}

function createApprovalCardElement(req) {
  const div = document.createElement("div");
  div.className = "action-required-card";
  div.id = `approval-card-${req.id}`;
  div.setAttribute("data-action-id", req.id);
  div.setAttribute("data-system", req.system || "");
  div.setAttribute("data-target", req.target || "");
  div.setAttribute("data-title", req.title || "");

  updateApprovalCardDOM(div, req);
  return div;
}

function updateApprovalCardDOM(div, req) {
  const statusUpper = (req.status || "PENDING").toUpperCase();
  const badgeClass = `status-${statusUpper.toLowerCase()}`;
  const systemName = (req.system || "jira").toUpperCase();
  const targetName = req.target || "action";

  let bodyHtml = "";
  if (statusUpper === "PENDING") {
    bodyHtml = `
      <div class="action-why">
        <strong>Why:</strong> ${escapeHtml(req.explanation || "Action requires human authorization.")}
      </div>
      <div class="action-payload-preview">${escapeHtml(JSON.stringify(req.proposed_payload || {}, null, 2))}</div>
      <div class="action-btn-group">
        <button class="btn-approve" onclick="approveAction('${req.id}')">✓ Approve &amp; Execute</button>
        <button class="btn-reject" onclick="rejectAction('${req.id}')">✕ Reject Action</button>
      </div>
    `;
  } else if (statusUpper === "EXECUTING") {
    bodyHtml = `
      <div class="action-executing-banner">
        <span class="spinner-sm"></span>
        <span>Executing action safely via Swytchcode...</span>
      </div>
    `;
  } else if (statusUpper === "EXECUTED" || statusUpper === "APPROVED") {
    const execId = req.execution_id || (req.execution_result && (req.execution_result.comment_id || req.execution_result.id)) || req.id;
    bodyHtml = `
      <div class="action-completed-banner">
        <div class="banner-title">✓ Action Executed via Swytchcode</div>
        <div class="banner-detail">Execution ID: <code>${escapeHtml(String(execId))}</code> · Target: <strong>${escapeHtml(targetName)}</strong></div>
      </div>
    `;
  } else if (statusUpper === "REJECTED") {
    bodyHtml = `
      <div class="action-rejected-banner">
        ✕ Action was rejected by operator.
      </div>
    `;
  } else if (statusUpper === "FAILED") {
    bodyHtml = `
      <div class="action-failed-banner">
        ⚠️ Execution failed: ${escapeHtml(req.explanation || "Error executing action via Swytchcode.")}
      </div>
    `;
  }

  div.innerHTML = `
    <div class="action-header">
      <span class="action-badge ${badgeClass}">${statusUpper}</span>
      <span class="action-target">${escapeHtml(systemName)} · Target: <strong>${escapeHtml(targetName)}</strong></span>
    </div>
    <div class="action-title">${escapeHtml(req.title || "Proposed Action")}</div>
    ${bodyHtml}
  `;
}

async function approveAction(reqId) {
  const cards = document.querySelectorAll(`[id="approval-card-${reqId}"]`);
  cards.forEach((card) => {
    updateApprovalCardDOM(card, {
      id: reqId,
      status: "EXECUTING",
      system: card.getAttribute("data-system") || "jira",
      target: card.getAttribute("data-target") || "action",
      title: card.getAttribute("data-title") || "Executing Action",
      explanation: "Executing action safely via Swytchcode...",
    });
  });

  try {
    const res = await fetch(`/api/approvals/${reqId}/approve`, { method: "POST" });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || "Approval execution failed");

    const execId = data.execution_id || (data.execution_result && (data.execution_result.comment_id || data.execution_result.id)) || reqId;

    // Transition all cards on page to EXECUTED
    cards.forEach((card) => {
      updateApprovalCardDOM(card, {
        id: reqId,
        status: "EXECUTED",
        system: card.getAttribute("data-system") || "jira",
        target: card.getAttribute("data-target") || "action",
        title: card.getAttribute("data-title") || "Action Executed",
        explanation: data.message || "Executed successfully.",
        execution_result: data.execution_result,
        execution_id: execId,
      });
    });

    showToast(`Action approved & executed successfully! (ID: ${execId})`, "success");
    loadApprovals(); // update badges and Action Center
  } catch (err) {
    cards.forEach((card) => {
      updateApprovalCardDOM(card, {
        id: reqId,
        status: "FAILED",
        system: card.getAttribute("data-system") || "jira",
        target: card.getAttribute("data-target") || "action",
        title: card.getAttribute("data-title") || "Action Failed",
        explanation: err.message,
      });
    });
    showToast(`Execution failed: ${err.message}`, "error");
  }
}

async function rejectAction(reqId) {
  const cards = document.querySelectorAll(`[id="approval-card-${reqId}"]`);
  try {
    const res = await fetch(`/api/approvals/${reqId}/reject`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ reason: "Rejected by operator" }),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || "Rejection failed");

    cards.forEach((card) => {
      updateApprovalCardDOM(card, {
        id: reqId,
        status: "REJECTED",
        system: card.getAttribute("data-system") || "jira",
        target: card.getAttribute("data-target") || "action",
        title: card.getAttribute("data-title") || "Action Rejected",
        explanation: "Rejected by operator.",
      });
    });

    showToast("Action rejected.", "info");
    loadApprovals();
  } catch (err) {
    showToast(`Failed to reject action: ${err.message}`, "error");
  }
}

// ---------------- Toast Notifications (Replacing browser alert) ----------------
function showToast(message, type = "success") {
  let container = document.getElementById("toast-container");
  if (!container) {
    container = document.createElement("div");
    container.id = "toast-container";
    container.className = "toast-container";
    document.body.appendChild(container);
  }
  const toast = document.createElement("div");
  toast.className = `toast toast-${type}`;
  const icon = type === "success" ? "✓" : type === "error" ? "⚠️" : "ℹ️";
  toast.innerHTML = `
    <span class="toast-icon" style="font-weight:700;">${icon}</span>
    <span class="toast-msg">${escapeHtml(message)}</span>
  `;
  container.appendChild(toast);
  setTimeout(() => {
    toast.classList.add("toast-fade");
    setTimeout(() => toast.remove(), 400);
  }, 4000);
}

// ---------------- 5. Operations Pulse Data ----------------
async function loadPulseData() {
  try {
    const [overviewRes, compareRes] = await Promise.all([
      fetch("/api/payments/overview"),
      fetch("/api/payments/compare"),
    ]);
    const ov = await overviewRes.json();
    const comp = await compareRes.json();

    document.getElementById("pulse-total-vol").innerText = `$${ov.total_volume.toLocaleString("en-US", { minimumFractionDigits: 2 })}`;
    document.getElementById("pulse-pending-vol").innerText = `$${ov.total_pending_volume.toLocaleString("en-US", { minimumFractionDigits: 2 })}`;

    const gateContainer = document.getElementById("pulse-gateways-container");
    if (gateContainer && comp.comparison) {
      gateContainer.innerHTML = comp.comparison.map((c) => `
        <div class="glass-card flex-between">
          <div>
            <div style="font-weight:700;font-size:1.05rem;color:#fff">${c.provider.toUpperCase()}</div>
            <div style="font-size:0.8rem;color:var(--text-muted)">${c.total_transactions} txns · $${c.total_volume.toFixed(2)}</div>
          </div>
          <div class="text-right">
            <div style="font-size:1.1rem;font-weight:800;color:${c.failure_rate_percent > 30 ? 'var(--rose-500)' : 'var(--emerald-500)'}">
              ${c.failure_rate_percent}% fail
            </div>
            <div style="font-size:0.75rem;color:var(--text-muted)">${c.failed} failed / ${c.succeeded} ok</div>
          </div>
        </div>
      `).join("");
    }

    const activityBody = document.getElementById("pulse-activity-tbody");
    if (activityBody && ov.recent_transactions) {
      activityBody.innerHTML = ov.recent_transactions.map((t) => `
        <tr>
          <td><code>${escapeHtml(t.id)}</code></td>
          <td><strong style="color:${t.provider === 'stripe' ? '#818cf8' : '#38bdf8'}">${t.provider.toUpperCase()}</strong></td>
          <td>${escapeHtml(t.customer)}</td>
          <td><strong>$${t.amount.toFixed(2)}</strong> ${t.currency}</td>
          <td><span class="status-badge ${t.status}">${t.status}</span></td>
          <td style="color:var(--text-muted);font-size:0.75rem;">${t.created_at ? t.created_at.substring(11, 19) : 'N/A'}</td>
        </tr>
      `).join("");
    }
  } catch (e) {
    console.error("Failed loading pulse:", e);
  }
}

// ---------------- 6. Payments Hub Ledger ----------------
async function loadPaymentsData() {
  try {
    const [txRes, compRes] = await Promise.all([
      fetch("/api/payments/transactions?limit=100"),
      fetch("/api/payments/compare"),
    ]);

    const txData = await txRes.json();
    cachedTransactions = Array.isArray(txData) ? txData : (txData.transactions || []);
    renderPaymentsTable(cachedTransactions);

    // Comparative Analysis Strip
    if (compRes.ok) {
      const compData = await compRes.json();
      renderComparePanel(compData);
    }

    // Update summary pills & counts
    const pendingCount = cachedTransactions.filter((t) => t.status === "pending").length;
    const failedCount = cachedTransactions.filter((t) => t.status === "failed").length;
    const succeededCount = cachedTransactions.filter((t) => t.status === "succeeded").length;
    const totalCount = cachedTransactions.length;

    const pendingPill = document.getElementById("payments-pending-pill");
    if (pendingPill) pendingPill.innerText = `${pendingCount} pending`;

    document.querySelectorAll(".filter-pill").forEach((pill) => {
      const f = pill.getAttribute("data-filter");
      if (f === "all") pill.innerText = `All (${totalCount})`;
      else if (f === "pending") pill.innerText = `Pending (${pendingCount})`;
      else if (f === "failed") pill.innerText = `Failed (${failedCount})`;
      else if (f === "succeeded") pill.innerText = `Succeeded (${succeededCount})`;
    });
  } catch (e) {
    console.error("Failed loading payments:", e);
  }
}

function renderComparePanel(compData) {
  const panel = document.getElementById("payments-compare-panel");
  if (!panel) return;
  if (!compData || !compData.comparison) {
    panel.innerHTML = `<div style="padding:14px;color:var(--text-muted);font-size:0.85rem;">Comparative analytics currently unavailable.</div>`;
    return;
  }

  const highest = compData.highest_failure_rate_provider || "paypal";
  const rows = compData.comparison || [];

  panel.innerHTML = `
    <div style="padding:16px 20px;">
      <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:14px;flex-wrap:wrap;gap:8px;">
        <div style="font-weight:700;font-size:0.95rem;color:#fff;display:flex;align-items:center;gap:8px;">
          <span>⚖️ Gateway Performance & Telemetry Comparison</span>
        </div>
        <span class="status-badge ${highest.toLowerCase() === 'paypal' ? 'failed' : 'pending'}" style="font-size:0.75rem;text-transform:uppercase;">
          Higher Failure Rate: ${escapeHtml(highest)}
        </span>
      </div>
      <div style="display:grid;grid-template-columns:repeat(auto-fit, minmax(280px, 1fr));gap:14px;">
        ${rows.map((r) => `
          <div style="background:rgba(255,255,255,0.03);border:1px solid rgba(255,255,255,0.07);border-radius:10px;padding:14px 18px;">
            <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:10px;">
              <strong style="color:${r.provider === 'stripe' ? '#818cf8' : '#38bdf8'};font-size:1.05rem;">
                ${escapeHtml(r.provider.toUpperCase())}
              </strong>
              <span style="font-size:0.8rem;padding:3px 8px;border-radius:6px;background:${r.failure_rate_percent > 30 ? 'rgba(239,68,68,0.15)' : 'rgba(16,185,129,0.15)'};color:${r.failure_rate_percent > 30 ? 'var(--rose-400)' : 'var(--emerald-400)'};font-weight:700;">
                ${Math.round(r.failure_rate_percent)}% fail rate
              </span>
            </div>
            <div style="display:flex;justify-content:space-between;font-size:0.85rem;color:var(--text-secondary);margin-bottom:5px;">
              <span>Total Volume:</span>
              <strong style="color:#fff">$${(r.total_volume || 0).toLocaleString("en-US", { minimumFractionDigits: 2 })}</strong>
            </div>
            <div style="display:flex;justify-content:space-between;font-size:0.85rem;color:var(--text-secondary);margin-bottom:5px;">
              <span>Succeeded / Failed:</span>
              <span><strong style="color:var(--emerald-400)">${r.succeeded} ok</strong> / <strong style="color:var(--rose-400)">${r.failed} fail</strong></span>
            </div>
            <div style="display:flex;justify-content:space-between;font-size:0.85rem;color:var(--text-secondary);">
              <span>Total Transactions:</span>
              <strong style="color:#fff">${r.total_transactions}</strong>
            </div>
          </div>
        `).join("")}
      </div>
    </div>
  `;
}

function initPaymentsFilters() {
  document.querySelectorAll(".filter-pill").forEach((btn) => {
    btn.addEventListener("click", () => {
      document.querySelectorAll(".filter-pill").forEach((b) => b.classList.remove("active"));
      btn.classList.add("active");
      const filter = btn.getAttribute("data-filter");

      if (filter === "all") {
        renderPaymentsTable(cachedTransactions);
      } else if (filter === "pending" || filter === "failed" || filter === "succeeded") {
        renderPaymentsTable(cachedTransactions.filter((t) => t.status === filter));
      } else if (filter === "paypal" || filter === "stripe") {
        renderPaymentsTable(cachedTransactions.filter((t) => t.provider === filter));
      }
    });
  });
}

function renderPaymentsTable(transactions) {
  const tbody = document.getElementById("payments-tbody");
  if (!tbody) return;

  if (!transactions || transactions.length === 0) {
    tbody.innerHTML = `<tr><td colspan="8" class="text-center py-4" style="color:var(--text-muted)">No transactions matching filter.</td></tr>`;
    return;
  }

  tbody.innerHTML = transactions.map((t) => `
    <tr>
      <td><code style="font-size:0.8rem;background:rgba(255,255,255,0.06);padding:3px 6px;border-radius:4px;">${escapeHtml(t.id)}</code></td>
      <td><strong style="color:${t.provider === 'stripe' ? '#818cf8' : '#38bdf8'}">${t.provider ? t.provider.toUpperCase() : 'N/A'}</strong></td>
      <td>${escapeHtml(t.customer || 'Unknown')}</td>
      <td><strong style="color:#fff">$${(t.amount || 0).toFixed(2)}</strong> ${escapeHtml(t.currency || 'USD')}</td>
      <td><span class="status-badge ${t.status}">${escapeHtml(t.status)}</span></td>
      <td><code style="font-size:0.75rem;color:var(--text-muted)">${escapeHtml(t.flow || 'standard')}</code></td>
      <td>${escapeHtml(t.payment_method || 'card')}</td>
      <td style="color:var(--text-muted);font-size:0.75rem;">${t.created_at ? escapeHtml(t.created_at.substring(0, 19).replace('T', ' ')) : 'N/A'}</td>
    </tr>
  `).join("");
}

// ---------------- 7. Systems & Integrations ----------------
async function loadSystemStatus() {
  try {
    const res = await fetch("/api/systems/status");
    const data = await res.json();
    const container = document.getElementById("integrations-cards-container");
    if (!container) return;

    container.innerHTML = Object.entries(data.systems).map(([key, sys]) => `
      <div class="integration-card">
        <div class="int-top">
          <div class="int-name">${escapeHtml(sys.name)}</div>
          <span class="status-badge ${sys.connected ? 'succeeded' : 'pending'}">
            ${sys.connected ? 'CONNECTED' : (sys.auth_status || 'READY')}
          </span>
        </div>
        <div class="int-desc">
          Account / Project: <code>${escapeHtml(sys.account || sys.project || sys.workspace || sys.site || 'Active')}</code>
        </div>
        <div class="int-caps">
          ${(sys.capabilities || []).map(c => `<span class="cap-tag">${escapeHtml(c)}</span>`).join('')}
        </div>
      </div>
    `).join("");
  } catch (e) {
    console.error("Failed loading systems:", e);
  }
}

// ---------------- Utilities ----------------
function escapeHtml(str) {
  if (!str) return "";
  return String(str)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#039;");
}

function formatMarkdown(text) {
  if (!text) return "";
  let html = escapeHtml(text);

  // Markdown Headings
  html = html.replace(/^### (.*$)/gim, "<h3>$1</h3>");
  html = html.replace(/^#### (.*$)/gim, "<h4>$1</h4>");
  html = html.replace(/^## (.*$)/gim, "<h2>$1</h2>");

  // Bold
  html = html.replace(/\*\*(.*?)\*\*/g, "<strong>$1</strong>");

  // Inline Code
  html = html.replace(/`([^`]+)`/g, "<code>$1</code>");

  // Blockquotes
  html = html.replace(/^> (.*$)/gim, "<blockquote>$1</blockquote>");

  // Lists
  html = html.replace(/^\* (.*$)/gim, "<li>$1</li>");
  html = html.replace(/^([0-9]+\.) (.*$)/gim, "<li><strong>$1</strong> $2</li>");

  // Line breaks
  html = html.replace(/\n\n/g, "<br><br>");

  return html;
}
