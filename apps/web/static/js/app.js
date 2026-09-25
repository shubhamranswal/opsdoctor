/**
 * OpsDoctor - Frontend Application Controller
 * Handles tabs, chat streaming, approval actions, and timeline visualization.
 */

// State
let currentSessionId = "session-" + Math.random().toString(36).substring(2, 9);
let isGenerating = false;
let pendingApprovalsCount = 0;

// DOM Elements
document.addEventListener("DOMContentLoaded", () => {
  initTabs();
  initChatInput();
  initQuickPrompts();
  loadSystemStatus();
  loadApprovals();
  loadTimeline();
});

// ---------------- Tab Navigation ----------------
function initTabs() {
  const navBtns = document.querySelectorAll(".nav-btn");
  navBtns.forEach((btn) => {
    btn.addEventListener("click", () => {
      const tabId = btn.getAttribute("data-tab");
      navBtns.forEach((b) => b.classList.remove("active"));
      btn.classList.add("active");

      document.querySelectorAll(".tab-pane").forEach((pane) => {
        pane.classList.remove("active");
        if (pane.id === `${tabId}-pane`) {
          pane.classList.add("active");
        }
      });

      if (tabId === "approvals") loadApprovals();
      if (tabId === "timeline") loadTimeline();
      if (tabId === "systems") loadSystemStatus();
    });
  });
}

// ---------------- Chat & Input Handling (IME Safe) ----------------
function initChatInput() {
  const textarea = document.getElementById("chat-input");
  const sendBtn = document.getElementById("btn-send");

  // Auto-resize textarea
  textarea.addEventListener("input", () => {
    textarea.style.height = "auto";
    textarea.style.height = Math.min(textarea.scrollHeight, 140) + "px";
  });

  // Enter to send (Shift+Enter for newline) with IME protection
  textarea.addEventListener("keydown", (e) => {
    if (e.isComposing || e.keyCode === 229) return; // IME safe per modern web guidance
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

async function handleSendMessage() {
  const textarea = document.getElementById("chat-input");
  const text = textarea.value.trim();
  if (!text || isGenerating) return;

  textarea.value = "";
  textarea.style.height = "auto";
  isGenerating = true;

  // Append user bubble
  appendUserMessage(text);

  // Create empty assistant message with live activity container
  const assistantBubble = createAssistantMessageContainer();
  const feed = document.getElementById("message-feed");
  feed.appendChild(assistantBubble);
  feed.scrollTop = feed.scrollHeight;

  const traceBody = assistantBubble.querySelector(".activity-trace-body");
  const traceContainer = assistantBubble.querySelector(".activity-trace-container");
  const contentCard = assistantBubble.querySelector(".assistant-text-content");
  const evidenceGallery = assistantBubble.querySelector(".evidence-gallery");
  const approvalArea = assistantBubble.querySelector(".approval-area");

  try {
    const res = await fetch("/api/agent/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: jsonStringify({ session_id: currentSessionId, message: text }),
    });

    if (!res.ok) {
      throw new Error(`HTTP error: ${res.status}`);
    }

    const data = await res.json();

    // Render activity steps
    if (data.activities && data.activities.length > 0) {
      traceContainer.style.display = "block";
      traceBody.innerHTML = "";
      data.activities.forEach((act) => {
        const item = document.createElement("div");
        item.className = `trace-item ${act.step_type}`;
        item.innerHTML = `
          <span class="trace-tag">${act.step_type.replace("_", " ")}</span>
          <div style="flex:1">
            <strong style="color:var(--text-primary)">${escapeHtml(act.title)}</strong>
            <div style="color:var(--text-secondary);margin-top:2px;">${escapeHtml(act.description)}</div>
          </div>
        `;
        traceBody.appendChild(item);
      });
    }

    // Render content
    contentCard.innerHTML = renderMarkdown(data.content);

    // Render evidence items
    if (data.evidence && data.evidence.length > 0) {
      evidenceGallery.style.display = "grid";
      evidenceGallery.innerHTML = "";
      data.evidence.forEach((ev) => {
        const card = document.createElement("div");
        card.className = "evidence-card";
        card.innerHTML = `
          <div class="evidence-card-header">
            <span class="system-badge ${ev.system}">${ev.system}</span>
            <small style="color:var(--text-muted);font-size:0.7rem">${ev.timestamp.substring(11, 19)} UTC</small>
          </div>
          <strong style="font-size:0.85rem;color:var(--text-primary)">${escapeHtml(ev.title)}</strong>
          <p style="font-size:0.8rem;color:var(--text-secondary)">${escapeHtml(ev.summary)}</p>
        `;
        evidenceGallery.appendChild(card);
      });
    }

    // Render approvals
    if (data.approvals && data.approvals.length > 0) {
      approvalArea.innerHTML = "";
      data.approvals.forEach((appr) => {
        renderApprovalCard(approvalArea, appr);
      });
      loadApprovals(); // update count badge
    }

  } catch (err) {
    contentCard.innerHTML = `<span style="color:var(--accent-rose)">Error communicating with OpsDoctor: ${escapeHtml(err.message)}</span>`;
  } finally {
    isGenerating = false;
    feed.scrollTop = feed.scrollHeight;
  }
}

function appendUserMessage(text) {
  const feed = document.getElementById("message-feed");
  const bubble = document.createElement("div");
  bubble.className = "message-bubble user";
  bubble.innerHTML = `<div>${escapeHtml(text)}</div>`;
  feed.appendChild(bubble);
  feed.scrollTop = feed.scrollHeight;
}

function createAssistantMessageContainer() {
  const bubble = document.createElement("div");
  bubble.className = "message-bubble assistant";
  bubble.innerHTML = `
    <div class="assistant-content-card">
      <div class="activity-trace-container" style="display:none">
        <div class="activity-trace-header" onclick="this.nextElementSibling.classList.toggle('collapsed')">
          <span>⚡ Agent Activity & Tool Trace</span>
          <span style="font-size:0.7rem">▼</span>
        </div>
        <div class="activity-trace-body"></div>
      </div>
      <div class="assistant-text-content">
        <div style="display:flex;align-items:center;gap:8px;color:var(--accent-cyan);">
          <span class="spinner"></span> OpsDoctor is investigating across connected systems...
        </div>
      </div>
      <div class="evidence-gallery" style="display:none"></div>
      <div class="approval-area"></div>
    </div>
  `;
  return bubble;
}

function renderApprovalCard(container, appr) {
  const card = document.createElement("div");
  card.className = "approval-card";
  card.id = `approval-${appr.id}`;
  card.innerHTML = `
    <div class="approval-card-title">
      <span>🛡️ Action Approval Required: ${escapeHtml(appr.title)}</span>
    </div>
    <p style="font-size:0.85rem;color:var(--text-secondary);">${escapeHtml(appr.explanation)}</p>
    <div style="background:rgba(0,0,0,0.3);padding:0.6rem;border-radius:var(--radius-sm);font-family:var(--font-mono);font-size:0.75rem;color:#cbd5e1;overflow-x:auto;">
      <strong>Target:</strong> ${escapeHtml(appr.system.toUpperCase())} &gt; ${escapeHtml(appr.target)}<br/>
      <strong>Action:</strong> <code>${escapeHtml(appr.action_type)}</code>
    </div>
    <div class="approval-card-actions">
      <button class="btn-approve" onclick="executeApproval('${appr.id}')">✓ Approve & Execute via Swytchcode</button>
      <button class="btn-reject" onclick="rejectApproval('${appr.id}')">✕ Reject</button>
    </div>
  `;
  container.appendChild(card);
}

// ---------------- Approval Execution ----------------
async function executeApproval(approvalId) {
  const card = document.getElementById(`approval-${approvalId}`);
  if (card) {
    card.innerHTML = `<span style="color:var(--accent-cyan)">Executing approved action via Swytchcode...</span>`;
  }

  try {
    const res = await fetch(`/api/approvals/${approvalId}/approve`, { method: "POST" });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || "Execution failed");

    if (card) {
      card.style.borderColor = "var(--accent-emerald)";
      card.innerHTML = `
        <div style="display:flex;align-items:center;gap:8px;color:var(--accent-emerald);font-weight:700">
          <span>✓ Action Executed via Swytchcode</span>
        </div>
        <p style="font-size:0.85rem;color:var(--text-secondary);margin-top:4px;">${escapeHtml(data.message)}</p>
        <small style="color:var(--text-muted);font-family:var(--font-mono)">Executed at ${data.approval.executed_at}</small>
      `;
    }
    loadApprovals();
  } catch (err) {
    if (card) {
      card.innerHTML = `<span style="color:var(--accent-rose)">Failed to execute action: ${escapeHtml(err.message)}</span>`;
    }
  }
}

async function rejectApproval(approvalId) {
  const card = document.getElementById(`approval-${approvalId}`);
  try {
    const res = await fetch(`/api/approvals/${approvalId}/reject`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ reason: "User cancelled in console" }),
    });
    const data = await res.json();
    if (card) {
      card.style.borderColor = "var(--text-muted)";
      card.innerHTML = `<span style="color:var(--text-muted)">✕ Action Rejected by User</span>`;
    }
    loadApprovals();
  } catch (err) {
    alert("Failed to reject: " + err.message);
  }
}

// ---------------- Data Loaders ----------------
async function loadSystemStatus() {
  try {
    const res = await fetch("/api/systems/status");
    const data = await res.json();
    const systems = data.systems || {};

    const container = document.getElementById("system-status-container");
    if (container) {
      container.innerHTML = "";
      Object.entries(systems).forEach(([key, info]) => {
        const pill = document.createElement("div");
        pill.className = "status-pill";
        pill.innerHTML = `
          <span class="status-dot ${info.connected ? "connected" : ""}"></span>
          <span>${info.name}</span>
        `;
        container.appendChild(pill);
      });
    }

    // Detail view in Systems tab
    const detailList = document.getElementById("systems-detail-list");
    if (detailList) {
      detailList.innerHTML = "";
      Object.entries(systems).forEach(([key, info]) => {
        const card = document.createElement("div");
        card.className = "assistant-content-card";
        card.innerHTML = `
          <div style="display:flex;justify-content:space-between;align-items:center;">
            <div style="display:flex;align-items:center;gap:10px;">
              <span class="status-dot ${info.connected ? "connected" : ""}"></span>
              <strong style="font-size:1rem;color:var(--text-primary);">${info.name}</strong>
            </div>
            <span class="system-badge ${key}">${info.type}</span>
          </div>
          <div style="font-size:0.85rem;color:var(--text-secondary);margin-top:6px;">
            ${info.account ? `<div><strong>Account:</strong> ${info.account}</div>` : ""}
            ${info.workspace ? `<div><strong>Workspace:</strong> ${info.workspace}</div>` : ""}
            ${info.site ? `<div><strong>Site:</strong> ${info.site} (Project: ${info.project})</div>` : ""}
            ${info.orders_count ? `<div><strong>Orders Verified:</strong> ${info.orders_count} (${info.failed_captures} capture failures)</div>` : ""}
          </div>
        `;
        detailList.appendChild(card);
      });
    }
  } catch (err) {
    console.error("Failed to load systems status", err);
  }
}

async function loadApprovals() {
  try {
    const res = await fetch("/api/approvals");
    const approvals = await res.json();
    const pending = approvals.filter((a) => a.status === "pending");
    
    // Update badge
    const badge = document.getElementById("approvals-badge");
    if (badge) {
      badge.innerText = pending.length;
      badge.style.display = pending.length > 0 ? "inline-block" : "none";
    }

    const list = document.getElementById("approvals-list");
    if (list) {
      list.innerHTML = "";
      if (approvals.length === 0) {
        list.innerHTML = `<div style="color:var(--text-muted);padding:2rem;text-align:center;">No actions currently pending approval.</div>`;
      } else {
        approvals.forEach((appr) => {
          const item = document.createElement("div");
          item.className = "approval-card";
          item.innerHTML = `
            <div class="approval-card-title">
              <span>${appr.status === "executed" ? "✓" : "🛡️"} ${escapeHtml(appr.title)}</span>
              <span class="system-badge ${appr.system}">${appr.status.toUpperCase()}</span>
            </div>
            <p style="font-size:0.85rem;color:var(--text-secondary);">${escapeHtml(appr.explanation)}</p>
            <div style="background:rgba(0,0,0,0.3);padding:0.6rem;border-radius:var(--radius-sm);font-family:var(--font-mono);font-size:0.75rem;color:#cbd5e1;">
              <strong>Target:</strong> ${escapeHtml(appr.target)} | <strong>Action:</strong> ${escapeHtml(appr.action_type)}
            </div>
            ${appr.status === "pending" ? `
              <div class="approval-card-actions">
                <button class="btn-approve" onclick="executeApproval('${appr.id}')">Approve & Execute via Swytchcode</button>
                <button class="btn-reject" onclick="rejectApproval('${appr.id}')">Reject</button>
              </div>
            ` : `<small style="color:var(--text-muted)">Updated: ${appr.executed_at || appr.created_at}</small>`}
          `;
          list.appendChild(item);
        });
      }
    }
  } catch (err) {
    console.error("Failed to load approvals", err);
  }
}

async function loadTimeline() {
  try {
    const res = await fetch("/api/timeline");
    const events = await res.json();
    const list = document.getElementById("timeline-container");
    if (!list) return;

    list.innerHTML = "";
    events.forEach((evt) => {
      const item = document.createElement("div");
      item.className = "timeline-item";
      
      let icon = "⚡";
      if (evt.system === "slack") icon = "💬";
      if (evt.system === "paypal") icon = "💳";
      if (evt.system === "jira") icon = "🎯";
      if (evt.system === "gmail") icon = "✉️";
      if (evt.system === "notion") icon = "📜";

      item.innerHTML = `
        <div class="timeline-icon-col">${icon}</div>
        <div class="timeline-content-card">
          <div style="display:flex;justify-content:space-between;align-items:center;">
            <div style="display:flex;align-items:center;gap:8px;">
              <span class="system-badge ${evt.system}">${evt.system}</span>
              <strong style="color:var(--text-primary);font-size:0.95rem;">${escapeHtml(evt.title)}</strong>
            </div>
            <span style="font-family:var(--font-mono);font-size:0.75rem;color:var(--accent-cyan);font-weight:600;">${evt.display_time}</span>
          </div>
          <p style="font-size:0.85rem;color:var(--text-secondary);">${escapeHtml(evt.description)}</p>
          <small style="color:var(--text-muted);font-size:0.75rem;">Source: ${escapeHtml(evt.source)}</small>
        </div>
      `;
      list.appendChild(item);
    });
  } catch (err) {
    console.error("Failed to load timeline", err);
  }
}

// ---------------- Helpers ----------------
function escapeHtml(str) {
  if (!str) return "";
  return String(str)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#039;");
}

function jsonStringify(obj) {
  return JSON.stringify(obj);
}

function renderMarkdown(md) {
  if (!md) return "";
  return md
    .replace(/^### (.*$)/gim, '<h3 style="color:var(--text-primary);margin-top:8px;font-size:1.05rem;">$1</h3>')
    .replace(/^#### (.*$)/gim, '<h4 style="color:var(--accent-cyan);margin-top:6px;font-size:0.95rem;">$1</h4>')
    .replace(/\*\*(.*?)\*\*/gim, '<strong style="color:var(--text-primary);">$1</strong>')
    .replace(/\*(.*?)\*/gim, '<em>$1</em>')
    .replace(/`([^`]+)`/gim, '<code style="background:rgba(0,0,0,0.3);padding:2px 6px;border-radius:4px;font-family:var(--font-mono);color:#38bdf8;">$1</code>')
    .replace(/\n\n/gim, '<br/><br/>')
    .replace(/\n/gim, '<br/>');
}
