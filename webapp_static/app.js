/* zabolotAI WebApp client */
(function () {
  "use strict";

  const tg = window.Telegram && window.Telegram.WebApp ? window.Telegram.WebApp : null;
  if (tg) {
    try {
      tg.ready();
      tg.expand();
      tg.MainButton.hide();
    } catch (_) {}
  }

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
  const modelBadge = document.getElementById("model-badge");

  // Conversation memory (kept short to stay fast).
  const HISTORY_MAX = 16;
  let history = [];
  let attachedImage = null; // { dataUrl, mime, base64 }

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

  // Minimal markdown-ish formatting: **bold**, *italic*, `code`, code blocks, line breaks.
  function renderText(s) {
    let html = escapeHtml(s);
    html = html.replace(/```([\s\S]*?)```/g, function (_, code) {
      return '<pre><code>' + code + '</code></pre>';
    });
    html = html.replace(/`([^`\n]+)`/g, '<code>$1</code>');
    html = html.replace(/\*\*([^*\n]+)\*\*/g, '<b>$1</b>');
    html = html.replace(/(^|\W)\*([^*\n]+)\*(?=\W|$)/g, '$1<i>$2</i>');
    return html;
  }

  function appendMessage(role, text, options) {
    clearWelcome();
    options = options || {};
    const div = document.createElement("div");
    div.className = "message " + role;
    if (options.imageDataUrl) {
      const img = document.createElement("img");
      img.className = "attached";
      img.src = options.imageDataUrl;
      div.appendChild(img);
    }
    if (text) {
      const span = document.createElement("span");
      span.innerHTML = renderText(text);
      div.appendChild(span);
    }
    if (options.typing) {
      div.classList.add("typing");
      div.id = "typing-indicator";
      div.textContent = "печатает…";
    }
    messagesEl.appendChild(div);
    messagesEl.scrollTop = messagesEl.scrollHeight;
    return div;
  }

  function removeTyping() {
    const t = document.getElementById("typing-indicator");
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
    const data = await fileToBase64(file);
    attachedImage = data;
    previewImg.src = data.dataUrl;
    previewEl.hidden = false;
    if (modelBadge) modelBadge.textContent = "deepseek-v4-flash (vision)";
  });

  previewRemoveBtn.addEventListener("click", function () {
    attachedImage = null;
    previewEl.hidden = true;
    fileInput.value = "";
    if (modelBadge) modelBadge.textContent = "minimax-m2.5";
  });

  resetBtn.addEventListener("click", function () {
    history = [];
    messagesEl.innerHTML = "";
    if (welcomeEl) {
      messagesEl.appendChild(welcomeEl);
    }
  });

  async function callApi(payload) {
    const res = await fetch("/api/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    const data = await res.json().catch(function () {
      return null;
    });
    if (!res.ok) {
      const detail = data && data.detail ? data.detail : "HTTP " + res.status;
      throw new Error(detail);
    }
    return data;
  }

  form.addEventListener("submit", async function (e) {
    e.preventDefault();
    const text = (input.value || "").trim();
    const img = attachedImage;
    if (!text && !img) return;

    sendBtn.disabled = true;
    appendMessage("user", text, { imageDataUrl: img ? img.dataUrl : null });
    input.value = "";
    autoresize();

    history.push({ role: "user", content: text || "[фото]" });
    if (history.length > HISTORY_MAX) history = history.slice(-HISTORY_MAX);

    appendMessage("bot", "", { typing: true });

    const payload = {
      init_data: tg ? tg.initData || "" : "",
      messages: history,
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
    } catch (err) {
      removeTyping();
      appendMessage("error", "⚠️ " + (err && err.message ? err.message : err));
    } finally {
      attachedImage = null;
      previewEl.hidden = true;
      fileInput.value = "";
      sendBtn.disabled = false;
      if (modelBadge) modelBadge.textContent = "minimax-m2.5";
      input.focus();
    }
  });

  // If there is no Telegram context, show a hint so users know it's meant to be opened from the bot.
  if (!tg || !tg.initData) {
    document.addEventListener("DOMContentLoaded", function () {
      // Soft warning only — backend will reject unauth'd requests except in dev mode.
    });
  }
})();
