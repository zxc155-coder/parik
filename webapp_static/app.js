/* zabolotAI Web App client. Pure ES5+ modules-free for max compatibility on
 * Telegram in-app webview engines (older Android/iOS WebView). */
(function () {
  "use strict";

  /* ───── Telegram WebApp setup ───── */
  const tg = window.Telegram && window.Telegram.WebApp ? window.Telegram.WebApp : null;
  if (tg) {
    try {
      tg.ready();
      tg.expand();
      if (tg.MainButton) tg.MainButton.hide();
      if (tg.colorScheme) {
        document.body.setAttribute("data-tg-theme", tg.colorScheme);
      }
      if (typeof tg.onEvent === "function") {
        tg.onEvent("themeChanged", function () {
          if (tg.colorScheme) document.body.setAttribute("data-tg-theme", tg.colorScheme);
        });
      }
    } catch (_) {
      /* ignore */
    }
  }

  /* ───── DOM refs ───── */
  const messagesEl = document.getElementById("messages");
  const welcomeEl = document.getElementById("welcome");
  const form = document.getElementById("composer");
  const input = document.getElementById("input");
  const sendBtn = document.getElementById("send-btn");
  const fileInput = document.getElementById("file-input");
  const previewEl = document.getElementById("preview");
  const previewImg = document.getElementById("preview-img");
  const previewRemoveBtn = document.getElementById("preview-remove");
  const resetBtn = document.getElementById("reset-btn");
  const modelPill = document.getElementById("model-pill");
  const modelPillLabel = document.getElementById("model-pill-label");
  const modelSheet = document.getElementById("model-sheet");
  const modelList = document.getElementById("model-list");
  const modelEmpty = document.getElementById("model-empty");
  const modelCount = document.getElementById("model-count");
  const modelSearch = document.getElementById("model-search");
  const modelTabs = document.getElementById("model-tabs");
  const quickActions = document.getElementById("quick-actions");
  const scrollBottomBtn = document.getElementById("scroll-bottom");

  /* ───── State ───── */
  const HISTORY_MAX = 16;
  const STORAGE_KEY = "zabolotai.model";
  let history = [];
  let attachedImage = null; // { dataUrl, mime, base64 }
  let availableModels = [];
  let currentModelId = null;
  let modelFilter = "all";
  let modelQuery = "";

  /* ───── Helpers ───── */
  function autoresize() {
    input.style.height = "auto";
    input.style.height = Math.min(input.scrollHeight, 140) + "px";
  }
  input.addEventListener("input", autoresize);
  input.addEventListener("keydown", function (e) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      form.requestSubmit();
    }
  });

  function clearWelcome() {
    if (welcomeEl && welcomeEl.parentNode) {
      welcomeEl.parentNode.removeChild(welcomeEl);
    }
  }

  function escapeHtml(s) {
    return String(s)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;");
  }

  // Lightweight markdown-ish: ```code blocks```, `inline code`, **bold**, *italic*.
  function renderText(s) {
    let html = escapeHtml(s);
    html = html.replace(/```([\s\S]*?)```/g, function (_, code) {
      return "<pre><code>" + code + "</code></pre>";
    });
    html = html.replace(/`([^`\n]+)`/g, "<code>$1</code>");
    html = html.replace(/\*\*([^*\n]+)\*\*/g, "<b>$1</b>");
    html = html.replace(/(^|\W)\*([^*\n]+)\*(?=\W|$)/g, "$1<i>$2</i>");
    return html;
  }

  function scrollToBottom() {
    requestAnimationFrame(function () {
      messagesEl.scrollTop = messagesEl.scrollHeight;
    });
  }

  function isNearBottom() {
    return messagesEl.scrollHeight - messagesEl.scrollTop - messagesEl.clientHeight < 80;
  }

  function updateScrollButton() {
    if (!scrollBottomBtn) return;
    scrollBottomBtn.hidden = isNearBottom();
  }

  if (messagesEl) {
    messagesEl.addEventListener("scroll", updateScrollButton, { passive: true });
  }
  if (scrollBottomBtn) {
    scrollBottomBtn.addEventListener("click", function () {
      messagesEl.scrollTop = messagesEl.scrollHeight;
    });
  }

  async function copyToClipboard(text) {
    try {
      if (navigator.clipboard && navigator.clipboard.writeText) {
        await navigator.clipboard.writeText(text);
        return true;
      }
    } catch (_) {}
    try {
      const ta = document.createElement("textarea");
      ta.value = text;
      ta.setAttribute("readonly", "");
      ta.style.position = "absolute";
      ta.style.left = "-9999px";
      document.body.appendChild(ta);
      ta.select();
      document.execCommand("copy");
      document.body.removeChild(ta);
      return true;
    } catch (_) {
      return false;
    }
  }

  function appendMessage(role, text, options) {
    clearWelcome();
    options = options || {};

    const row = document.createElement("div");
    row.className = "message-row " + role;

    const avatar = document.createElement("div");
    avatar.className = "avatar " + (role === "user" ? "user" : "bot");
    avatar.textContent = role === "user" ? "Я" : "zA";

    const bubble = document.createElement("div");
    bubble.className = "bubble " + (role === "error" ? "bot" : role);

    if (options.imageDataUrl) {
      const img = document.createElement("img");
      img.className = "attached";
      img.src = options.imageDataUrl;
      bubble.appendChild(img);
    }
    if (text) {
      const span = document.createElement("span");
      span.innerHTML = renderText(text);
      bubble.appendChild(span);
    }
    if (options.typing) {
      bubble.classList.add("typing");
      bubble.innerHTML = "<span></span><span></span><span></span>";
      row.id = "typing-row";
    }

    if (role !== "error") row.appendChild(avatar);

    // Copy button on bot bubbles (skip typing / error / empty).
    if (role === "bot" && text && !options.typing) {
      const actions = document.createElement("div");
      actions.className = "msg-actions";
      const copyBtn = document.createElement("button");
      copyBtn.type = "button";
      copyBtn.className = "msg-action";
      copyBtn.title = "Скопировать";
      copyBtn.setAttribute("aria-label", "Скопировать ответ");
      copyBtn.innerHTML =
        '<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="9" y="9" width="13" height="13" rx="2" ry="2"></rect><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"></path></svg>';
      copyBtn.addEventListener("click", async function () {
        const ok = await copyToClipboard(text);
        if (ok) {
          copyBtn.classList.add("copied");
          copyBtn.innerHTML = "✓";
          setTimeout(function () {
            copyBtn.classList.remove("copied");
            copyBtn.innerHTML =
              '<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="9" y="9" width="13" height="13" rx="2" ry="2"></rect><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"></path></svg>';
          }, 1400);
          if (tg && tg.HapticFeedback && tg.HapticFeedback.selectionChanged) {
            try { tg.HapticFeedback.selectionChanged(); } catch (_) {}
          }
        }
      });
      actions.appendChild(copyBtn);
      const wrap = document.createElement("div");
      wrap.className = "bubble-wrap";
      wrap.appendChild(bubble);
      wrap.appendChild(actions);
      row.appendChild(wrap);
    } else {
      row.appendChild(bubble);
    }

    messagesEl.appendChild(row);
    scrollToBottom();
    updateScrollButton();
    return row;
  }

  function removeTyping() {
    const t = document.getElementById("typing-row");
    if (t && t.parentNode) t.parentNode.removeChild(t);
  }

  function fileToBase64(file) {
    return new Promise(function (resolve, reject) {
      const reader = new FileReader();
      reader.onload = function () {
        const result = String(reader.result || "");
        const idx = result.indexOf(",");
        resolve({
          dataUrl: result,
          mime: file.type || "image/jpeg",
          base64: idx >= 0 ? result.slice(idx + 1) : result,
        });
      };
      reader.onerror = function () {
        reject(reader.error || new Error("read error"));
      };
      reader.readAsDataURL(file);
    });
  }

  /* ───── File attachment ───── */
  fileInput.addEventListener("change", async function () {
    const file = fileInput.files && fileInput.files[0];
    if (!file) return;
    if (!file.type.startsWith("image/")) {
      alert("Можно прикреплять только картинки.");
      fileInput.value = "";
      return;
    }
    if (file.size > 5 * 1024 * 1024) {
      alert("Файл слишком большой (>5MB).");
      fileInput.value = "";
      return;
    }
    try {
      const data = await fileToBase64(file);
      attachedImage = data;
      previewImg.src = data.dataUrl;
      previewEl.hidden = false;
    } catch (err) {
      alert("Не удалось прочитать файл: " + err);
    }
  });

  previewRemoveBtn.addEventListener("click", function () {
    attachedImage = null;
    previewEl.hidden = true;
    fileInput.value = "";
  });

  /* ───── Reset ───── */
  resetBtn.addEventListener("click", function () {
    history = [];
    messagesEl.innerHTML = "";
    if (welcomeEl) {
      // Re-attach a fresh welcome (the original may already be detached).
      messagesEl.appendChild(welcomeEl);
    }
  });

  /* ───── Quick action chips ───── */
  if (quickActions) {
    quickActions.addEventListener("click", function (e) {
      const btn = e.target.closest(".chip");
      if (!btn) return;
      const prompt = btn.getAttribute("data-prompt") || "";
      input.value = prompt;
      autoresize();
      input.focus();
      form.requestSubmit();
    });
  }

  /* ───── Model picker ───── */
  function getCurrentModel() {
    return availableModels.find(function (m) { return m.id === currentModelId; }) || availableModels[0];
  }

  function updateModelPill() {
    const m = getCurrentModel();
    if (m && modelPillLabel) modelPillLabel.textContent = m.label;
  }

  function modelMatchesFilter(m, filter) {
    if (filter === "all") return true;
    if (filter === "free") return m.badge === "free";
    if (filter === "reasoning") return m.badge === "reasoning" || /reasoning/i.test(m.description || "");
    if (filter === "fast") return m.speed === "fast";
    return m.provider === filter;
  }

  function modelMatchesQuery(m, q) {
    if (!q) return true;
    const haystack = (m.label + " " + m.id + " " + (m.description || "") + " " + (m.provider || "")).toLowerCase();
    return haystack.indexOf(q) !== -1;
  }

  function renderModelList() {
    if (!modelList) return;
    modelList.innerHTML = "";
    const filtered = availableModels.filter(function (m) {
      return modelMatchesFilter(m, modelFilter) && modelMatchesQuery(m, modelQuery);
    });

    if (modelCount) {
      modelCount.textContent =
        filtered.length === availableModels.length
          ? availableModels.length + " моделей доступно"
          : filtered.length + " из " + availableModels.length;
    }
    if (modelEmpty) modelEmpty.hidden = filtered.length > 0;

    filtered.forEach(function (m) {
      const card = document.createElement("button");
      card.type = "button";
      card.className = "model-card" + (m.id === currentModelId ? " active" : "");
      card.setAttribute("data-id", m.id);

      const head = document.createElement("div");
      head.className = "model-head";

      const name = document.createElement("div");
      name.className = "model-name";
      name.textContent = m.label;
      head.appendChild(name);

      const badges = document.createElement("div");
      badges.className = "model-badges";

      const providerBadge = document.createElement("span");
      providerBadge.className = "badge provider-" + (m.provider || "");
      providerBadge.textContent = m.provider === "canopywave" ? "Canopy" : (m.provider || "");
      badges.appendChild(providerBadge);

      if (m.badge) {
        const b = document.createElement("span");
        b.className = "badge " + escapeHtml(m.badge);
        b.textContent = m.badge;
        badges.appendChild(b);
      }
      const speedBadge = document.createElement("span");
      speedBadge.className = "badge speed-" + escapeHtml(m.speed || "medium");
      speedBadge.textContent = m.speed === "fast" ? "fast" : m.speed === "slow" ? "slow" : "balanced";
      badges.appendChild(speedBadge);

      const check = document.createElement("span");
      check.className = "check";
      check.innerHTML = "✓";
      badges.appendChild(check);

      head.appendChild(badges);
      card.appendChild(head);

      const desc = document.createElement("div");
      desc.className = "model-desc";
      desc.textContent = m.description || "";
      card.appendChild(desc);

      card.addEventListener("click", function () {
        selectModel(m.id);
        closeSheet();
      });

      modelList.appendChild(card);
    });
  }

  if (modelSearch) {
    modelSearch.addEventListener("input", function () {
      modelQuery = (modelSearch.value || "").toLowerCase().trim();
      renderModelList();
    });
  }
  if (modelTabs) {
    modelTabs.addEventListener("click", function (e) {
      const btn = e.target.closest(".tab");
      if (!btn) return;
      modelFilter = btn.getAttribute("data-filter") || "all";
      const tabs = modelTabs.querySelectorAll(".tab");
      for (let i = 0; i < tabs.length; i++) tabs[i].classList.remove("active");
      btn.classList.add("active");
      renderModelList();
      if (tg && tg.HapticFeedback && tg.HapticFeedback.selectionChanged) {
        try { tg.HapticFeedback.selectionChanged(); } catch (_) {}
      }
    });
  }

  function selectModel(id) {
    if (!availableModels.some(function (m) { return m.id === id; })) return;
    currentModelId = id;
    try { localStorage.setItem(STORAGE_KEY, id); } catch (_) {}
    updateModelPill();
    renderModelList();
    if (tg && tg.HapticFeedback && tg.HapticFeedback.selectionChanged) {
      try { tg.HapticFeedback.selectionChanged(); } catch (_) {}
    }
  }

  function openSheet() {
    if (!modelSheet) return;
    renderModelList();
    modelSheet.hidden = false;
    if (modelPill) modelPill.setAttribute("aria-expanded", "true");
  }

  function closeSheet() {
    if (!modelSheet) return;
    modelSheet.hidden = true;
    if (modelPill) modelPill.setAttribute("aria-expanded", "false");
  }

  if (modelPill) {
    modelPill.addEventListener("click", openSheet);
  }
  if (modelSheet) {
    modelSheet.addEventListener("click", function (e) {
      if (e.target.closest("[data-close]")) closeSheet();
    });
  }
  document.addEventListener("keydown", function (e) {
    if (e.key === "Escape" && modelSheet && !modelSheet.hidden) closeSheet();
  });

  async function loadModels() {
    try {
      const res = await fetch("/api/models");
      if (!res.ok) throw new Error("HTTP " + res.status);
      const data = await res.json();
      availableModels = (data && data.models) || [];
      const stored = (function () {
        try { return localStorage.getItem(STORAGE_KEY); } catch (_) { return null; }
      })();
      const exists = function (id) { return availableModels.some(function (m) { return m.id === id; }); };
      currentModelId = exists(stored) ? stored : (data && data.default) || (availableModels[0] && availableModels[0].id);
      updateModelPill();
      renderModelList();
    } catch (err) {
      if (modelPillLabel) modelPillLabel.textContent = "по умолчанию";
    }
  }

  /* ───── API call ───── */
  async function callApi(payload) {
    const res = await fetch("/api/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    const data = await res.json().catch(function () { return null; });
    if (!res.ok) {
      const detail = data && data.detail ? data.detail : "HTTP " + res.status;
      throw new Error(detail);
    }
    return data;
  }

  /* ───── Submit ───── */
  form.addEventListener("submit", async function (e) {
    e.preventDefault();
    const text = (input.value || "").trim();
    const img = attachedImage;
    if (!text && !img) return;

    sendBtn.disabled = true;
    sendBtn.classList.add("loading");
    appendMessage("user", text, { imageDataUrl: img ? img.dataUrl : null });
    input.value = "";
    autoresize();

    history.push({ role: "user", content: text || "[фото]" });
    if (history.length > HISTORY_MAX) history = history.slice(-HISTORY_MAX);

    appendMessage("bot", "", { typing: true });

    const payload = {
      init_data: tg ? tg.initData || "" : "",
      messages: history,
      model: currentModelId || undefined,
    };
    if (img) {
      payload.image_base64 = img.base64;
      payload.image_mime = img.mime;
    }

    try {
      const data = await callApi(payload);
      removeTyping();
      const answer = (data && data.answer) || "(пустой ответ)";
      history.push({ role: "assistant", content: answer });
      appendMessage("bot", answer);
      if (tg && tg.HapticFeedback && tg.HapticFeedback.notificationOccurred) {
        try { tg.HapticFeedback.notificationOccurred("success"); } catch (_) {}
      }
    } catch (err) {
      removeTyping();
      appendMessage("error", "⚠️ " + (err && err.message ? err.message : err));
      if (tg && tg.HapticFeedback && tg.HapticFeedback.notificationOccurred) {
        try { tg.HapticFeedback.notificationOccurred("error"); } catch (_) {}
      }
    } finally {
      attachedImage = null;
      previewEl.hidden = true;
      fileInput.value = "";
      sendBtn.disabled = false;
      sendBtn.classList.remove("loading");
      input.focus();
    }
  });

  /* ───── Init ───── */
  loadModels();
})();
