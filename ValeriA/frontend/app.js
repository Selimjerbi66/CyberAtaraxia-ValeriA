const state = {
  currentChatId: null,
  chats: [],
  messages: [],
  availableModels: [],
  abortController: null,
  isStreaming: false,
};

const el = (id) => document.getElementById(id);

marked.setOptions({ breaks: true, gfm: true });

async function api(path, options = {}) {
  const resp = await fetch(path, {
    headers: { "Content-Type": "application/json" },
    credentials: "same-origin",
    ...options,
  });
  if (resp.status === 401) {
    showAuthScreen(false);
    throw new Error("Non authentifié");
  }
  if (!resp.ok) {
    const body = await resp.json().catch(() => ({}));
    throw new Error(body.detail || `Erreur ${resp.status}`);
  }
  return resp.json();
}

// =========================================================================
// AUTH
// =========================================================================

async function checkAuth() {
  const status = await fetch("/api/auth/status").then((r) => r.json());
  if (status.needs_setup) {
    showAuthScreen(true);
  } else if (!status.authenticated) {
    showAuthScreen(false);
  } else {
    showApp();
  }
}

function showAuthScreen(isSetup) {
  el("app").classList.add("hidden");
  el("auth-screen").classList.remove("hidden");
  el("auth-password-confirm").classList.toggle("hidden", !isSetup);
  el("auth-title").innerHTML = isSetup
    ? "Configuration"
    : '<span class="brand-claud">Claud</span><span class="brand-ia">iA</span>';
  el("auth-subtitle").textContent = isSetup
    ? "Choisis un mot de passe pour protéger cette instance."
    : "Entre ton mot de passe pour continuer.";
  el("auth-submit").textContent = isSetup ? "Créer le mot de passe" : "Continuer";
  el("auth-form").dataset.mode = isSetup ? "setup" : "login";
}

function showApp() {
  el("auth-screen").classList.add("hidden");
  el("app").classList.remove("hidden");
  loadModelsGlobal();
  loadChats();
}

el("auth-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const mode = el("auth-form").dataset.mode;
  const password = el("auth-password").value;
  el("auth-error").classList.add("hidden");

  try {
    if (mode === "setup") {
      const confirm = el("auth-password-confirm").value;
      if (password !== confirm) throw new Error("Les mots de passe ne correspondent pas");
      await api("/api/auth/setup", { method: "POST", body: JSON.stringify({ password }) });
    } else {
      await api("/api/auth/login", { method: "POST", body: JSON.stringify({ password }) });
    }
    showApp();
  } catch (err) {
    el("auth-error").textContent = err.message;
    el("auth-error").classList.remove("hidden");
  }
});

el("logout-btn").addEventListener("click", async () => {
  await api("/api/auth/logout", { method: "POST" });
  closeSettings();
  showAuthScreen(false);
});

// =========================================================================
// CHATS (sidebar)
// =========================================================================

let searchDebounceTimer = null;
el("chat-search-input").addEventListener("input", () => {
  clearTimeout(searchDebounceTimer);
  searchDebounceTimer = setTimeout(() => loadChats(el("chat-search-input").value), 250);
});

async function loadChats(search = "") {
  state.chats = await api(`/api/chats?search=${encodeURIComponent(search)}`);
  renderChatList();
  if (!search) {
    if (!state.currentChatId && state.chats.length > 0) {
      selectChat(state.chats[0].id);
    } else if (state.chats.length === 0) {
      await createNewChat();
    }
  }
}

function renderChatList() {
  const container = el("chat-list");
  container.innerHTML = "";
  const pinned = state.chats.filter((c) => c.pinned);
  const rest = state.chats.filter((c) => !c.pinned);

  const renderGroup = (label, list) => {
    if (list.length === 0) return;
    if (label) {
      const groupLabel = document.createElement("div");
      groupLabel.className = "chat-list-group-label";
      groupLabel.textContent = label;
      container.appendChild(groupLabel);
    }
    for (const chat of list) {
      container.appendChild(buildChatListItem(chat));
    }
  };

  renderGroup(pinned.length ? "Épinglées" : "", pinned);
  renderGroup(pinned.length ? "Récentes" : "", rest);
}

function buildChatListItem(chat) {
  const item = document.createElement("div");
  item.className = "chat-list-item" + (chat.id === state.currentChatId ? " active" : "");
  item.innerHTML = `
    <span class="chat-title-text"></span>
    <span class="chat-item-actions">
      <button class="pin-icon${chat.pinned ? " pinned" : ""}" title="Épingler">${chat.pinned ? "★" : "☆"}</button>
      <button class="edit-icon" title="Renommer">✎</button>
      <button class="delete-icon" title="Supprimer">✕</button>
    </span>`;
  item.querySelector(".chat-title-text").textContent = chat.title;
  item.addEventListener("click", (e) => {
    if (e.target.closest(".chat-item-actions")) return;
    selectChat(chat.id);
  });
  item.querySelector(".pin-icon").addEventListener("click", async (e) => {
    e.stopPropagation();
    await api(`/api/chats/${chat.id}/pin`, { method: "PATCH", body: JSON.stringify({ pinned: !chat.pinned }) });
    await loadChats(el("chat-search-input").value);
  });
  item.querySelector(".edit-icon").addEventListener("click", (e) => {
    e.stopPropagation();
    startInlineRename(item, chat);
  });
  item.querySelector(".delete-icon").addEventListener("click", async (e) => {
    e.stopPropagation();
    if (!confirm("Supprimer cette discussion ?")) return;
    await api(`/api/chats/${chat.id}`, { method: "DELETE" });
    if (state.currentChatId === chat.id) state.currentChatId = null;
    await loadChats();
  });
  return item;
}

function startInlineRename(item, chat) {
  const titleSpan = item.querySelector(".chat-title-text");
  const input = document.createElement("input");
  input.type = "text";
  input.value = chat.title;
  input.className = "chat-title-edit-input";
  titleSpan.replaceWith(input);
  input.focus();
  input.select();

  let committed = false;
  const commit = async () => {
    if (committed) return;
    committed = true;
    const newTitle = input.value.trim() || chat.title;
    if (newTitle !== chat.title) {
      await api(`/api/chats/${chat.id}`, { method: "PATCH", body: JSON.stringify({ title: newTitle }) });
    }
    await loadChats(el("chat-search-input").value);
  };

  input.addEventListener("keydown", (ev) => {
    if (ev.key === "Enter") { ev.preventDefault(); input.blur(); }
    if (ev.key === "Escape") { committed = true; loadChats(el("chat-search-input").value); }
  });
  input.addEventListener("blur", commit);
}

el("new-chat-btn").addEventListener("click", createNewChat);

async function createNewChat() {
  const { id } = await api("/api/chats", { method: "POST", body: JSON.stringify({}) });
  await loadChats();
  state.currentChatId = id;
  renderChatList();
  renderMessages([]);
  el("current-chat-title").textContent = "Nouvelle discussion";
  await refreshChatModelSelect();
}

async function selectChat(chatId) {
  state.currentChatId = chatId;
  renderChatList();
  const messages = await api(`/api/chats/${chatId}/messages`);
  state.messages = messages;
  renderMessages(messages);
  const chat = state.chats.find((c) => c.id === chatId);
  if (chat) el("current-chat-title").textContent = chat.title;
  await refreshChatModelSelect();
}

// =========================================================================
// MODELS (global + par chat)
// =========================================================================

async function loadModelsGlobal() {
  try {
    const { models } = await api("/api/models");
    state.availableModels = models;
  } catch {
    state.availableModels = [];
  }
}

async function refreshChatModelSelect() {
  const select = el("chat-model-select");
  select.innerHTML = "";
  const defaultOpt = document.createElement("option");
  defaultOpt.value = "";
  defaultOpt.textContent = "Modèle par défaut";
  select.appendChild(defaultOpt);
  for (const m of state.availableModels) {
    const opt = document.createElement("option");
    opt.value = m;
    opt.textContent = m;
    select.appendChild(opt);
  }
  const chat = state.chats.find((c) => c.id === state.currentChatId);
  select.value = chat && chat.model_override ? chat.model_override : "";
}

el("chat-model-select").addEventListener("change", async () => {
  if (!state.currentChatId) return;
  const value = el("chat-model-select").value;
  await api(`/api/chats/${state.currentChatId}/model`, {
    method: "PATCH",
    body: JSON.stringify({ model: value || null }),
  });
  await loadChats(el("chat-search-input").value);
});

// =========================================================================
// MARKDOWN RENDERING
// =========================================================================

function renderMarkdownInto(bubbleEl, rawText) {
  const html = DOMPurify.sanitize(marked.parse(rawText || ""));
  bubbleEl.innerHTML = html;
  bubbleEl.querySelectorAll("pre code").forEach((block) => {
    hljs.highlightElement(block);
    const pre = block.parentElement;
    if (!pre.querySelector(".code-copy-btn")) {
      const btn = document.createElement("button");
      btn.className = "code-copy-btn";
      btn.textContent = "copier";
      btn.addEventListener("click", () => {
        navigator.clipboard.writeText(block.textContent);
        btn.textContent = "copié !";
        setTimeout(() => (btn.textContent = "copier"), 1500);
      });
      pre.style.position = "relative";
      pre.appendChild(btn);
    }
  });
}

// =========================================================================
// MESSAGES RENDERING
// =========================================================================

function renderMessages(messages) {
  const container = el("messages");
  container.innerHTML = "";
  if (messages.length === 0) {
    container.innerHTML = `
      <div class="empty-state">
        <span class="empty-mark">◆</span>
        <h2><span class="brand-claud">Claud</span><span class="brand-ia">iA</span></h2>
        <p>Chaque réponse s'appuie sur une recherche web en temps réel avant d'être générée par ton modèle Ollama.</p>
      </div>`;
    return;
  }
  for (const msg of messages) {
    appendMessageToDOM(msg.role, msg.content, msg.sources || [], msg);
  }
  scrollToBottom();
}

function appendMessageToDOM(role, content, sources = [], msgData = {}) {
  const container = el("messages");
  const empty = container.querySelector(".empty-state");
  if (empty) empty.remove();

  const row = document.createElement("div");
  row.className = `msg-row ${role}`;
  row.dataset.messageId = msgData.id || "";

  const bubble = document.createElement("div");
  bubble.className = "msg-bubble" + (role === "assistant" ? " markdown" : "");

  if (role === "assistant") {
    renderMarkdownInto(bubble, content);
  } else {
    bubble.textContent = content;
  }
  row.appendChild(bubble);

  if (role === "assistant") {
    const actions = document.createElement("div");
    actions.className = "msg-actions";

    const copyBtn = document.createElement("button");
    copyBtn.className = "msg-action-btn";
    copyBtn.title = "Copier";
    copyBtn.innerHTML = "⧉";
    copyBtn.addEventListener("click", () => {
      navigator.clipboard.writeText(content);
      copyBtn.textContent = "✓";
      setTimeout(() => (copyBtn.innerHTML = "⧉"), 1200);
    });
    actions.appendChild(copyBtn);

    const regenBtn = document.createElement("button");
    regenBtn.className = "msg-action-btn";
    regenBtn.title = "Régénérer";
    regenBtn.innerHTML = "↻";
    regenBtn.addEventListener("click", () => regenerateLast());
    actions.appendChild(regenBtn);

    const upBtn = document.createElement("button");
    upBtn.className = "msg-action-btn up" + (msgData.feedback === "up" ? " active" : "");
    upBtn.innerHTML = "👍";
    upBtn.addEventListener("click", () => toggleFeedback(msgData.id, "up", upBtn, downBtn));
    actions.appendChild(upBtn);

    const downBtn = document.createElement("button");
    downBtn.className = "msg-action-btn down" + (msgData.feedback === "down" ? " active" : "");
    downBtn.innerHTML = "👎";
    downBtn.addEventListener("click", () => toggleFeedback(msgData.id, "down", upBtn, downBtn));
    actions.appendChild(downBtn);

    if (msgData.gen_seconds) {
      const stats = document.createElement("span");
      stats.className = "msg-stats";
      const tps = msgData.gen_tokens && msgData.gen_seconds ? (msgData.gen_tokens / msgData.gen_seconds).toFixed(1) : "?";
      stats.textContent = `⏱ ${msgData.gen_seconds.toFixed(1)}s · ${tps} tok/s`;
      actions.appendChild(stats);
    }

    row.appendChild(actions);

    if (sources.length > 0) {
      row.appendChild(buildSourcesBlock(sources));
    }
  }

  container.appendChild(row);
  return { row, bubble };
}

function buildSourcesBlock(sources) {
  const wrap = document.createElement("div");

  const toggle = document.createElement("button");
  toggle.className = "sources-toggle";
  toggle.textContent = `▸ Sources (${sources.length})`;
  wrap.appendChild(toggle);

  const list = document.createElement("div");
  list.className = "sources-list hidden";
  for (const s of sources) {
    const pill = document.createElement("button");
    pill.className = "source-pill" + (s.method === "failed" ? " failed" : "");
    pill.textContent = s.title || s.url;
    pill.addEventListener("click", () => openLinkConfirm(s.url));
    list.appendChild(pill);
  }
  wrap.appendChild(list);

  toggle.addEventListener("click", () => {
    const isHidden = list.classList.contains("hidden");
    list.classList.toggle("hidden");
    toggle.textContent = `${isHidden ? "▾" : "▸"} Sources (${sources.length})`;
  });

  return wrap;
}

function openLinkConfirm(url) {
  el("link-confirm-url").textContent = url;
  el("link-confirm-modal").classList.remove("hidden");
  const okBtn = el("link-ok-btn");
  const cancelBtn = el("link-cancel-btn");

  const cleanup = () => {
    okBtn.removeEventListener("click", onOk);
    cancelBtn.removeEventListener("click", onCancel);
    el("link-confirm-modal").classList.add("hidden");
  };
  const onOk = () => {
    window.open(url, "_blank", "noopener,noreferrer");
    cleanup();
  };
  const onCancel = () => cleanup();

  okBtn.addEventListener("click", onOk);
  cancelBtn.addEventListener("click", onCancel);
}

async function toggleFeedback(messageId, value, upBtn, downBtn) {
  if (!messageId) return;
  const isActive = (value === "up" ? upBtn : downBtn).classList.contains("active");
  const newValue = isActive ? null : value;
  await api(`/api/messages/${messageId}/feedback`, {
    method: "PATCH",
    body: JSON.stringify({ feedback: newValue }),
  });
  upBtn.classList.remove("active");
  downBtn.classList.remove("active");
  if (newValue) (newValue === "up" ? upBtn : downBtn).classList.add("active");
}

function scrollToBottom() {
  const container = el("messages");
  container.scrollTop = container.scrollHeight;
}

// =========================================================================
// STATUS INDICATOR
// =========================================================================

function showStatus(label) {
  el("status-indicator").classList.remove("hidden");
  el("status-label").textContent = label;
}

function hideStatus() {
  el("status-indicator").classList.add("hidden");
}

// =========================================================================
// STREAMING (envoi + régénération partagent la même logique)
// =========================================================================

function setStreamingUI(isStreaming) {
  state.isStreaming = isStreaming;
  el("send-icon").classList.toggle("hidden", isStreaming);
  el("stop-icon").classList.toggle("hidden", !isStreaming);
  el("send-btn").classList.toggle("stopping", isStreaming);
}

async function consumeSSE(response, handlers) {
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const events = buffer.split("\n\n");
    buffer = events.pop();

    for (const rawEvent of events) {
      const lines = rawEvent.split("\n");
      let eventType = "message";
      let data = "{}";
      for (const line of lines) {
        if (line.startsWith("event: ")) eventType = line.slice(7);
        if (line.startsWith("data: ")) data = line.slice(6);
      }
      let payload;
      try {
        payload = JSON.parse(data);
      } catch {
        continue;
      }
      if (handlers[eventType]) handlers[eventType](payload);
    }
  }
}

async function runStream(fetchPromise) {
  setStreamingUI(true);
  showStatus("Recherche web en cours…");

  let assistantBubble = null;
  let assistantRow = null;
  let assistantContent = "";
  let firstTokenReceived = false;
  let lastSources = [];

  try {
    const resp = await fetchPromise;
    if (resp.status === 401) {
      showAuthScreen(false);
      return;
    }

    await consumeSSE(resp, {
      status: (payload) => {
        if (!firstTokenReceived) showStatus(payload.label);
      },
      sources: (payload) => {
        lastSources = payload.sources;
      },
      token: (payload) => {
        if (!firstTokenReceived) {
          hideStatus();
          firstTokenReceived = true;
          const built = appendMessageToDOM("assistant", "");
          assistantBubble = built.bubble;
          assistantRow = built.row;
        }
        assistantContent += payload.content;
        renderMarkdownInto(assistantBubble, assistantContent);
        scrollToBottom();
      },
      error: (payload) => {
        hideStatus();
        if (!assistantBubble) {
          const built = appendMessageToDOM("assistant", "");
          assistantBubble = built.bubble;
        }
        assistantBubble.textContent = "⚠️ " + payload.message;
        assistantBubble.style.color = "var(--rd)";
      },
      stats: () => {},
      done: async () => {
        hideStatus();
        if (state.currentChatId) {
          await selectChat(state.currentChatId);
          await loadChats(el("chat-search-input").value);
        }
      },
    });
  } catch (err) {
    hideStatus();
    if (err.name !== "AbortError") console.error(err);
  } finally {
    setStreamingUI(false);
    state.abortController = null;
  }
}

el("composer-form").addEventListener("submit", async (e) => {
  e.preventDefault();

  if (state.isStreaming) {
    if (state.abortController) state.abortController.abort();
    return;
  }

  const input = el("composer-input");
  const message = input.value.trim();
  if (!message || !state.currentChatId) return;

  input.value = "";
  autoResizeTextarea();
  appendMessageToDOM("user", message);
  scrollToBottom();

  state.abortController = new AbortController();
  const fetchPromise = fetch("/api/chat/stream", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    credentials: "same-origin",
    signal: state.abortController.signal,
    body: JSON.stringify({ chat_id: state.currentChatId, message }),
  });

  await runStream(fetchPromise);
});

async function regenerateLast() {
  if (!state.currentChatId || state.isStreaming) return;
  // Retire la derniere reponse assistant affichee
  const container = el("messages");
  const rows = container.querySelectorAll(".msg-row.assistant");
  if (rows.length > 0) {
    const lastRow = rows[rows.length - 1];
    lastRow.remove();
  }

  state.abortController = new AbortController();
  const fetchPromise = fetch(`/api/chat/regenerate/${state.currentChatId}`, {
    method: "POST",
    credentials: "same-origin",
    signal: state.abortController.signal,
  });

  await runStream(fetchPromise);
}

// Textarea auto-resize + Enter to send + Ctrl+K
const composerInput = el("composer-input");
composerInput.addEventListener("input", autoResizeTextarea);
composerInput.addEventListener("keydown", (e) => {
  if (e.key === "Enter" && !e.shiftKey) {
    e.preventDefault();
    el("composer-form").requestSubmit();
  }
});

function autoResizeTextarea() {
  composerInput.style.height = "auto";
  composerInput.style.height = Math.min(composerInput.scrollHeight, 200) + "px";
}

document.addEventListener("keydown", (e) => {
  if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "k") {
    e.preventDefault();
    if (!el("app").classList.contains("hidden")) createNewChat();
  }
});

// =========================================================================
// VOICE INPUT
// =========================================================================

const SpeechRecognitionCtor = window.SpeechRecognition || window.webkitSpeechRecognition;
let recognition = null;
let isRecording = false;

if (SpeechRecognitionCtor) {
  recognition = new SpeechRecognitionCtor();
  recognition.continuous = false;
  recognition.interimResults = false;
  recognition.lang = "fr-FR";

  recognition.onresult = (event) => {
    const transcript = event.results[0][0].transcript;
    composerInput.value += (composerInput.value ? " " : "") + transcript;
    autoResizeTextarea();
  };
  recognition.onend = () => {
    isRecording = false;
    el("mic-btn").classList.remove("recording");
  };
  recognition.onerror = () => {
    isRecording = false;
    el("mic-btn").classList.remove("recording");
  };
} else {
  el("mic-btn").title = "Dictée vocale non supportée par ce navigateur";
  el("mic-btn").style.opacity = "0.3";
}

el("mic-btn").addEventListener("click", () => {
  if (!recognition) return;
  if (isRecording) {
    recognition.stop();
    isRecording = false;
    el("mic-btn").classList.remove("recording");
  } else {
    recognition.start();
    isRecording = true;
    el("mic-btn").classList.add("recording");
  }
});

// =========================================================================
// EXPORT
// =========================================================================

el("export-btn").addEventListener("click", () => {
  if (!state.messages || state.messages.length === 0) return;
  let md = `# ${el("current-chat-title").textContent}\n\n`;
  for (const m of state.messages) {
    md += m.role === "user" ? `**Moi :** ${m.content}\n\n` : `**ClaudiA :** ${m.content}\n\n`;
    if (m.sources && m.sources.length) {
      md += "Sources : " + m.sources.map((s) => `[${s.title}](${s.url})`).join(", ") + "\n\n";
    }
  }
  const blob = new Blob([md], { type: "text/markdown" });
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = `${el("current-chat-title").textContent.slice(0, 40)}.md`;
  a.click();
  URL.revokeObjectURL(a.href);
});

// =========================================================================
// SETTINGS MODAL
// =========================================================================

el("settings-btn").addEventListener("click", openSettings);
el("close-settings").addEventListener("click", closeSettings);

el("setting-temperature").addEventListener("input", () => {
  el("temperature-value").textContent = el("setting-temperature").value;
});

async function openSettings() {
  el("settings-modal").classList.remove("hidden");
  const settings = await api("/api/settings");

  el("setting-custom_instructions").value = settings.custom_instructions || "";
  el("setting-auto_detect_search").checked = settings.auto_detect_search !== "false";
  el("setting-search_engine").value = settings.search_engine || "searxng";
  el("setting-searxng_url").value = settings.searxng_url || "";
  el("setting-search_category").value = settings.search_category || "general";
  el("setting-num_sources").value = settings.num_sources || 10;
  el("setting-scrape_mode").value = settings.scrape_mode || "hybrid";
  el("setting-scrape_timeout").value = settings.scrape_timeout || 8;
  el("setting-max_chars_per_page").value = settings.max_chars_per_page || 4000;
  el("setting-ollama_url").value = settings.ollama_url || "";
  el("setting-temperature").value = settings.temperature || 0.7;
  el("temperature-value").textContent = settings.temperature || 0.7;

  await refreshModelList(settings.ollama_model);
}

function closeSettings() {
  el("settings-modal").classList.add("hidden");
  el("password-msg").classList.add("hidden");
}

async function refreshModelList(selectedModel) {
  const modelSelect = el("setting-ollama_model");
  modelSelect.innerHTML = `<option value="">Chargement…</option>`;
  try {
    const { models } = await api("/api/models");
    state.availableModels = models;
    modelSelect.innerHTML = "";
    if (models.length === 0) {
      modelSelect.innerHTML = `<option value="">Aucun modèle trouvé — vérifie l'URL Ollama</option>`;
    }
    for (const m of models) {
      const opt = document.createElement("option");
      opt.value = m;
      opt.textContent = m;
      if (m === selectedModel) opt.selected = true;
      modelSelect.appendChild(opt);
    }
    if (selectedModel && !models.includes(selectedModel)) {
      const opt = document.createElement("option");
      opt.value = selectedModel;
      opt.textContent = selectedModel + " (non détecté)";
      opt.selected = true;
      modelSelect.appendChild(opt);
    }
  } catch {
    modelSelect.innerHTML = `<option value="">Erreur de connexion à Ollama</option>`;
  }
}

el("setting-ollama_url").addEventListener("change", async () => {
  await api("/api/settings", { method: "POST", body: JSON.stringify({ ollama_url: el("setting-ollama_url").value }) });
  await refreshModelList();
});

el("save-settings-btn").addEventListener("click", async () => {
  const payload = {
    custom_instructions: el("setting-custom_instructions").value,
    auto_detect_search: el("setting-auto_detect_search").checked ? "true" : "false",
    search_engine: el("setting-search_engine").value,
    searxng_url: el("setting-searxng_url").value,
    search_category: el("setting-search_category").value,
    num_sources: el("setting-num_sources").value,
    scrape_mode: el("setting-scrape_mode").value,
    scrape_timeout: el("setting-scrape_timeout").value,
    max_chars_per_page: el("setting-max_chars_per_page").value,
    ollama_url: el("setting-ollama_url").value,
    ollama_model: el("setting-ollama_model").value,
    temperature: el("setting-temperature").value,
  };
  await api("/api/settings", { method: "POST", body: JSON.stringify(payload) });
  await loadModelsGlobal();
  await refreshChatModelSelect();
  closeSettings();
});

el("change-password-btn").addEventListener("click", async () => {
  const old_password = el("old-password").value;
  const new_password = el("new-password").value;
  const msg = el("password-msg");
  msg.classList.remove("hidden");
  try {
    await api("/api/auth/change-password", {
      method: "POST",
      body: JSON.stringify({ old_password, new_password }),
    });
    msg.textContent = "Mot de passe changé avec succès.";
    msg.style.color = "var(--green)";
    el("old-password").value = "";
    el("new-password").value = "";
  } catch (err) {
    msg.textContent = err.message;
    msg.style.color = "var(--rd)";
  }
});

// =========================================================================
// INIT
// =========================================================================

checkAuth();
