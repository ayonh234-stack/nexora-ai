/* Nexora AI — frontend */
(() => {
  "use strict";
  const API = (window.NEXORA_API_BASE || "").replace(/\/$/, "");
  const $ = (s) => document.querySelector(s);
  const LS_CHATS = "nexora.chats.v1", LS_CUR = "nexora.current.v1", LS_LANG = "nexora.lang", LS_SID = "nexora.sid";

  const T = {
    bn: {
      newChat: "নতুন চ্যাট", server: "সার্ভার URL", install: "অ্যাপ ইনস্টল", clearAll: "সব ইতিহাস মুছুন", leadTitle: "ফ্রি গ্রোথ কনসালটেশন",
      leadSub: "তথ্য দিন, Md Zahngir Hossain নিজে যোগাযোগ করবেন।", fName: "নাম", fIg: "Instagram handle", fBudget: "বাজেট",
      fContact: "যোগাযোগ (Email / WhatsApp / Telegram)", cancel: "বাতিল", submit: "পাঠান",
      placeholder: { chat: "Nexora-কে কিছু জিজ্ঞেস করুন…", caption: "পোস্টের বিষয়/নিশ লিখুন, ক্যাপশন বানিয়ে দেব…", growth: "আপনার Instagram/TikTok গ্রোথ নিয়ে জিজ্ঞেস করুন…", image: "কীসের ছবি চান? যেমন: নীল পদ্ম, সূর্যাস্তে…", video: "কীসের ভিডিও চান? যেমন: একটি লাল আপেল ঘুরছে" },
      hint: { chat: "ছবি পাঠাতে 📷 চাপুন · বাংলা বা English", caption: "ক্যাপশন, হ্যাশট্যাগ, রিল আইডিয়া", growth: "SocialGrowthLab · অর্গানিক গ্রোথ, কোনো ফেক ফলোয়ার নয়", image: "ফ্রি AI ছবি · ১০–৪০ সেকেন্ড লাগতে পারে", video: "ফ্রি ২ সেকেন্ডের ক্লিপ · দিনে সীমিত · ২০–৯০ সেকেন্ড" },
      welcomeTitle: "আমি Nexora AI", welcomeSub: "ব্যবসা, মার্কেটিং, কনটেন্ট, রিসার্চ আর দৈনন্দিন কাজে আপনার অল-ইন-ওয়ান AI সহকারী।",
      leadBtn: "📝 ফ্রি কনসালটেশন ফর্ম", copied: "কপি হয়েছে", copy: "কপি", del: "মুছুন", download: "ডাউনলোড",
      imgWait: "ছবি তৈরি হচ্ছে…", vidWait: "ভিডিও তৈরি হচ্ছে (২০–৯০ সেকেন্ড)…", photoQ: "এই ছবিটা নিয়ে কী জানতে চান? (ঐচ্ছিক)",
      leadThanks: "ধন্যবাদ! আপনার তথ্য পৌঁছে গেছে, Md Zahngir Hossain শিগগিরই যোগাযোগ করবেন।", netErr: "নেটওয়ার্ক সমস্যা, আবার চেষ্টা করুন।",
      confirmClear: "সব চ্যাট ইতিহাস মুছে ফেলবেন?", untitled: "নতুন চ্যাট", noHistory: "এখনো কোনো চ্যাট নেই", offline: "আপনি অফলাইনে আছেন",
      modes: { chat: "চ্যাট", caption: "কনটেন্ট", growth: "গ্রোথ", image: "ছবি", video: "ভিডিও" },
    },
    en: {
      newChat: "New chat", server: "Server URL", install: "Install app", clearAll: "Clear all history", leadTitle: "Free growth consultation",
      leadSub: "Share your details and Md Zahngir Hossain will reach out personally.", fName: "Name", fIg: "Instagram handle", fBudget: "Budget",
      fContact: "Contact (Email / WhatsApp / Telegram)", cancel: "Cancel", submit: "Send",
      placeholder: { chat: "Ask Nexora anything…", caption: "Describe your post or niche for captions…", growth: "Ask about growing your Instagram/TikTok…", image: "Describe an image, e.g. a blue lotus at sunset", video: "Describe a clip, e.g. a red apple spinning" },
      hint: { chat: "Tap 📷 to send a photo · Bengali or English", caption: "Captions, hashtags, reel ideas", growth: "SocialGrowthLab · organic growth, no fake followers", image: "Free AI images · may take 10–40s", video: "Free 2-second clips · daily limit · 20–90s" },
      welcomeTitle: "I'm Nexora AI", welcomeSub: "Your all-in-one AI assistant for business, marketing, content, research and everyday life.",
      leadBtn: "📝 Free consultation form", copied: "Copied", copy: "Copy", del: "Delete", download: "Download",
      imgWait: "Creating your image…", vidWait: "Creating your video (20–90s)…", photoQ: "What do you want to know about this photo? (optional)",
      leadThanks: "Thank you! Your details were sent — Md Zahngir Hossain will contact you soon.", netErr: "Network problem, please try again.",
      confirmClear: "Delete all chat history?", untitled: "New chat", noHistory: "No chats yet", offline: "You are offline",
      modes: { chat: "Chat", caption: "Content", growth: "Growth", image: "Image", video: "Video" },
    },
  };
  const MODE_ICONS = { chat: "💬", caption: "✍️", growth: "🚀", image: "🎨", video: "🎬" };
  const SUGGEST = {
    chat: [["Business", "আমার অনলাইন ব্যবসার জন্য ৫টা মার্কেটিং আইডিয়া দাও"], ["Productivity", "Plan my week to balance clients and content"], ["Research", "ক্লায়েন্ট হান্টিং কীভাবে শুরু করব?"], ["Write", "Write a polite follow-up email to a client"]],
    caption: [["Instagram", "কফি শপের নতুন লাতের জন্য ক্যাপশন"], ["TikTok", "Hooks for a fitness coach reel"], ["Hashtags", "Hashtags for a Dhaka fashion boutique"], ["Calendar", "৭ দিনের কনটেন্ট প্ল্যান, বেকারি ব্যবসা"]],
    growth: [["Service", "SocialGrowthLab কীভাবে কাজ করে?"], ["Pricing", "How much does organic growth cost?"], ["Trust", "Do you use bots or fake followers?"], ["Start", "আমি আমার Instagram গ্রো করতে চাই"]],
    image: [["Logo idea", "minimal modern logo for a coffee brand, flat vector"], ["Product", "luxury perfume bottle on black marble, studio light"], ["Art", "নীল পদ্ম ফুল, সূর্যাস্তের আলোয়, ডিজিটাল আর্ট"], ["Social", "Instagram post background, pastel gradient, abstract"]],
    video: [["Nature", "ocean waves at sunset, cinematic"], ["Product", "a red apple spinning slowly on a table"], ["City", "rainy neon city street at night"], ["Fun", "একটি বিড়াল জানালার পাশে বসে আছে"]],
  };

  let lang = localStorage.getItem(LS_LANG) || ((navigator.language || "").startsWith("bn") ? "bn" : "bn");
  let sid = localStorage.getItem(LS_SID);
  if (!sid) { sid = (crypto.randomUUID ? crypto.randomUUID() : String(Date.now()) + Math.random()).replace(/[^a-z0-9-]/gi, ""); localStorage.setItem(LS_SID, sid); }
  let chats = load();
  let current = localStorage.getItem(LS_CUR);
  let mode = "chat";
  let busy = false;
  let pendingPhoto = null;
  let deferredInstall = null;

  const els = {
    messages: $("#messages"), input: $("#input"), form: $("#composer"), send: $("#sendBtn"), modes: $("#modes"),
    hint: $("#hint"), drawer: $("#drawer"), scrim: $("#scrim"), history: $("#historyList"), photoInput: $("#photoInput"),
    photoPreview: $("#photoPreview"), photoThumb: $("#photoThumb"), toast: $("#toast"), leadDialog: $("#leadDialog"), leadForm: $("#leadForm"),
  };

  function t(k) { return T[lang][k]; }
  function load() { try { return JSON.parse(localStorage.getItem(LS_CHATS)) || {}; } catch { return {}; } }
  function save() {
    // keep newest 40 chats, 120 messages each
    const ids = Object.keys(chats).sort((a, b) => chats[b].updated - chats[a].updated);
    ids.slice(40).forEach((id) => delete chats[id]);
    ids.slice(0, 40).forEach((id) => { chats[id].messages = chats[id].messages.slice(-120); });
    try { localStorage.setItem(LS_CHATS, JSON.stringify(chats)); }
    catch { // quota: strip embedded photo previews
      Object.values(chats).forEach((c) => c.messages.forEach((m) => { if (m.photo && m.photo.startsWith("data:")) m.photo = ""; }));
      try { localStorage.setItem(LS_CHATS, JSON.stringify(chats)); } catch {}
    }
    if (current) localStorage.setItem(LS_CUR, current);
  }
  function chat() {
    if (!current || !chats[current]) {
      current = "c" + Date.now().toString(36);
      chats[current] = { id: current, title: "", mode, messages: [], updated: Date.now() };
    }
    return chats[current];
  }
  function toast(msg) {
    els.toast.textContent = msg; els.toast.classList.add("show");
    clearTimeout(toast._t); toast._t = setTimeout(() => els.toast.classList.remove("show"), 2600);
  }
  function md(text) {
    const html = marked.parse(text || "", { breaks: true, gfm: true });
    return DOMPurify.sanitize(html, { ADD_ATTR: ["target"] });
  }
  function esc(s) { const d = document.createElement("div"); d.textContent = s; return d.innerHTML; }
  function url(u) { return u && u.startsWith("/") ? API + u : u; }

  // ------------------------------------------------ rendering
  function applyI18n() {
    document.documentElement.lang = lang;
    document.querySelectorAll("[data-i18n]").forEach((el) => { const v = t(el.dataset.i18n); if (typeof v === "string") el.textContent = v; });
    $("#langLabel").textContent = lang === "bn" ? "English" : "বাংলা";
    renderModes(); updateComposer(); renderHistory();
    if (!chat().messages.length) renderMessages();
  }
  function renderModes() {
    els.modes.innerHTML = "";
    Object.keys(MODE_ICONS).forEach((m) => {
      const b = document.createElement("button");
      b.className = "mode" + (m === mode ? " active" : ""); b.type = "button"; b.setAttribute("role", "tab");
      b.innerHTML = `<span>${MODE_ICONS[m]}</span><span>${t("modes")[m]}</span>`;
      b.onclick = () => setMode(m);
      els.modes.appendChild(b);
    });
  }
  function setMode(m) {
    mode = m; const c = chat(); c.mode = m;
    renderModes(); updateComposer();
    if (!c.messages.length) renderMessages();
    els.input.focus({ preventScroll: true });
  }
  function updateComposer() {
    els.input.placeholder = t("placeholder")[mode];
    els.hint.textContent = t("hint")[mode];
  }
  function renderWelcome() {
    const w = document.createElement("div"); w.className = "welcome";
    w.innerHTML = `<img class="logo" src="/icons/icon.svg" alt=""><h2>${esc(t("welcomeTitle"))}</h2><p>${esc(t("welcomeSub"))}</p>
      <p style="margin-top:6px;font-weight:600;color:#c4b5fd">Your AI. Your Business. Your World.</p><div class="cards"></div>`;
    const cards = w.querySelector(".cards");
    SUGGEST[mode].forEach(([title, text]) => {
      const c = document.createElement("button"); c.className = "card"; c.type = "button";
      c.innerHTML = `<b>${MODE_ICONS[mode]} ${esc(title)}</b>${esc(text)}`;
      c.onclick = () => { els.input.value = text; submit(); };
      cards.appendChild(c);
    });
    if (mode === "growth") {
      const b = document.createElement("button"); b.className = "primary-btn lead-cta"; b.type = "button"; b.textContent = t("leadBtn");
      b.onclick = openLead; w.appendChild(b);
    }
    els.messages.appendChild(w);
  }
  function renderMessages() {
    els.messages.innerHTML = "";
    const c = chat();
    if (!c.messages.length) renderWelcome();
    c.messages.forEach((m, i) => { const e = msgEl(m, i); e.classList.add("still"); els.messages.appendChild(e); });
    scrollEnd(false);
  }
  function msgEl(m, idx) {
    const row = document.createElement("div");
    row.className = "msg " + (m.role === "user" ? "user" : "bot");
    if (m.role !== "user") row.innerHTML = `<img class="avatar" src="/icons/icon.svg" alt="">`;
    const b = document.createElement("div"); b.className = "bubble"; row.appendChild(b);
    fillBubble(b, m);
    if (m.role !== "user" && !m.pending && (m.content || m.url)) {
      const tools = document.createElement("div"); tools.className = "msg-tools";
      if (m.content) {
        const cp = document.createElement("button"); cp.textContent = "📋 " + t("copy");
        cp.onclick = () => navigator.clipboard?.writeText(m.content).then(() => toast(t("copied")));
        tools.appendChild(cp);
      }
      b.appendChild(tools);
    }
    return row;
  }
  function fillBubble(b, m) {
    if (m.role === "user") {
      b.innerHTML = "";
      if (m.photo) { const im = document.createElement("img"); im.className = "upload"; im.src = m.photo; im.alt = "photo"; b.appendChild(im); }
      if (m.content) b.appendChild(document.createTextNode(m.content));
      return;
    }
    if (m.pending && !m.content) {
      b.innerHTML = `<span class="typing"><i></i><i></i><i></i></span>${m.progress ? `<div class="progress">${esc(m.progress)}</div>` : ""}`;
      return;
    }
    if (m.type === "image" && m.url) {
      b.innerHTML = `<img class="gen" src="${esc(url(m.url))}" alt="${esc(m.prompt || "")}" loading="lazy"><div class="media-actions"><a href="${esc(url(m.url))}" download="nexora.jpg" target="_blank" rel="noopener">⬇ ${t("download")}</a></div>${m.prompt ? `<div class="progress">🎨 ${esc(m.prompt)}</div>` : ""}`;
      return;
    }
    if (m.type === "video" && m.url) {
      b.innerHTML = `<video class="gen" src="${esc(url(m.url))}" controls autoplay loop muted playsinline></video><div class="media-actions"><a href="${esc(url(m.url))}" download="nexora.mp4" target="_blank" rel="noopener">⬇ ${t("download")}</a></div>${m.prompt ? `<div class="progress">🎬 ${esc(m.prompt)}</div>` : ""}`;
      return;
    }
    b.innerHTML = md(m.content);
    b.querySelectorAll("a").forEach((a) => { a.target = "_blank"; a.rel = "noopener"; });
    if (m.error) b.classList.add("err");
  }
  function scrollEnd(smooth = true) { requestAnimationFrame(() => els.messages.scrollTo({ top: els.messages.scrollHeight, behavior: smooth ? "smooth" : "auto" })); }
  function renderHistory() {
    els.history.innerHTML = "";
    const list = Object.values(chats).filter((c) => c.messages.length).sort((a, b) => b.updated - a.updated);
    if (!list.length) { els.history.innerHTML = `<div class="empty-h">${esc(t("noHistory"))}</div>`; return; }
    list.forEach((c) => {
      const it = document.createElement("div"); it.className = "h-item" + (c.id === current ? " active" : "");
      it.innerHTML = `<span>${MODE_ICONS[c.mode] || "💬"}</span><span class="t">${esc(c.title || t("untitled"))}</span><button aria-label="${t("del")}">🗑</button>`;
      it.onclick = (e) => {
        if (e.target.tagName === "BUTTON") { delete chats[c.id]; if (current === c.id) current = null; save(); renderHistory(); if (!current) newChat(); return; }
        current = c.id; mode = c.mode || "chat"; save(); renderModes(); updateComposer(); renderMessages(); renderHistory(); closeDrawer();
      };
      els.history.appendChild(it);
    });
  }
  function newChat() {
    current = null; chat(); save(); renderMessages(); renderHistory(); closeDrawer(); els.input.focus({ preventScroll: true });
  }

  // ------------------------------------------------ messaging
  function push(m) {
    const c = chat(); c.messages.push(m); c.updated = Date.now();
    if (!c.title && m.role === "user") c.title = (m.content || "📷 Photo").slice(0, 60);
    if (c.messages.length === 1) els.messages.innerHTML = "";
    const el = msgEl(m, c.messages.length - 1); els.messages.appendChild(el);
    save(); renderHistory(); scrollEnd();
    return { m, el };
  }
  function refresh(ref) {
    const nel = msgEl(ref.m); nel.classList.add("still"); ref.el.replaceWith(nel); ref.el = nel; save(); scrollEnd();
  }
  function historyPayload() {
    return chat().messages.filter((m) => !m.pending && !m.error).slice(-21, -1).map((m) => ({
      role: m.role === "user" ? "user" : "assistant",
      content: m.type === "image" ? `[Generated image: ${m.prompt}]` : m.type === "video" ? `[Generated video: ${m.prompt}]` : (m.photo ? `[photo] ${m.content || ""}` : m.content || ""),
    })).filter((m) => m.content.trim());
  }
  async function errText(res) {
    try { const j = await res.json(); return typeof j.detail === "string" ? j.detail : t("netErr"); } catch { return t("netErr"); }
  }
  async function api(path, opts) {
    return fetch(API + path, opts);
  }

  async function sendChat(text) {
    const bot = push({ role: "assistant", content: "", pending: true });
    try {
      const res = await api("/api/chat", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message: text, mode, session_id: sid + ":" + current, history: historyPayload(), stream: true }),
      });
      if (!res.ok) throw new Error(await errText(res));
      const ct = res.headers.get("content-type") || "";
      if (ct.includes("application/json")) {
        const j = await res.json();
        if (j.action === "image" || j.action === "video") {
          bot.m.pending = true; bot.m.content = ""; bot.m.progress = j.action === "image" ? t("imgWait") : t("vidWait"); refresh(bot);
          return j.action === "image" ? genImage(j.prompt, bot) : genVideo(j.prompt, bot);
        }
        bot.m.content = j.reply || ""; bot.m.pending = false; refresh(bot);
        return;
      }
      // SSE stream
      const reader = res.body.getReader(); const dec = new TextDecoder(); let buf = "", acc = "";
      let lastPaint = 0;
      for (;;) {
        const { value, done } = await reader.read(); if (done) break;
        buf += dec.decode(value, { stream: true });
        let idx;
        while ((idx = buf.indexOf("\n\n")) >= 0) {
          const line = buf.slice(0, idx).trim(); buf = buf.slice(idx + 2);
          if (!line.startsWith("data:")) continue;
          const ev = JSON.parse(line.slice(5));
          if (ev.delta) acc += ev.delta;
          if (ev.error) { bot.m.error = !acc; acc = acc ? acc + "\n\n" + ev.error : ev.error; }
        }
        bot.m.content = acc; bot.m.pending = false;
        const now = performance.now();
        if (now - lastPaint > 60) { fillBubble(bot.el.querySelector(".bubble"), bot.m); scrollEnd(false); lastPaint = now; }
      }
      bot.m.content = acc || t("netErr"); bot.m.pending = false; refresh(bot);
    } catch (e) {
      bot.m.pending = false; bot.m.error = true; bot.m.content = e.message || t("netErr"); refresh(bot);
    }
  }
  async function genImage(prompt, ref) {
    ref = ref || push({ role: "assistant", content: "", pending: true, progress: t("imgWait") });
    try {
      const res = await api("/api/image", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ prompt }) });
      if (!res.ok) throw new Error(await errText(res));
      const j = await res.json();
      Object.assign(ref.m, { pending: false, type: "image", url: j.url, prompt: j.prompt, content: "", progress: "" });
    } catch (e) { Object.assign(ref.m, { pending: false, error: true, content: e.message || t("netErr") }); }
    refresh(ref);
  }
  async function genVideo(prompt, ref) {
    ref = ref || push({ role: "assistant", content: "", pending: true, progress: t("vidWait") });
    const started = Date.now();
    const timer = setInterval(() => { ref.m.progress = `${t("vidWait")} ${Math.round((Date.now() - started) / 1000)}s`; const p = ref.el.querySelector(".progress"); if (p) p.textContent = ref.m.progress; }, 1000);
    try {
      const res = await api("/api/video", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ prompt }) });
      if (!res.ok) throw new Error(await errText(res));
      const j = await res.json();
      Object.assign(ref.m, { pending: false, type: "video", url: j.url, prompt: j.prompt, content: "", progress: "" });
    } catch (e) { Object.assign(ref.m, { pending: false, error: true, content: e.message || t("netErr") }); }
    clearInterval(timer); refresh(ref);
  }
  async function sendPhoto(file, question, preview) {
    push({ role: "user", content: question, photo: preview });
    const bot = push({ role: "assistant", content: "", pending: true });
    try {
      const fd = new FormData(); fd.append("file", file, file.name || "photo.jpg"); fd.append("question", question || "");
      const res = await api("/api/vision", { method: "POST", body: fd });
      if (!res.ok) throw new Error(await errText(res));
      const j = await res.json(); bot.m.content = j.reply;
    } catch (e) { bot.m.error = true; bot.m.content = e.message || t("netErr"); }
    bot.m.pending = false; refresh(bot);
  }

  async function submit() {
    if (busy) return;
    const text = els.input.value.trim();
    if (!text && !pendingPhoto) return;
    if (!navigator.onLine) { toast(t("offline")); return; }
    busy = true; els.send.disabled = true;
    els.input.value = ""; autosize();
    try {
      if (pendingPhoto) {
        const { file, preview } = pendingPhoto; clearPhoto();
        await sendPhoto(file, text, preview);
      } else if (mode === "image") {
        push({ role: "user", content: text }); await genImage(text);
      } else if (mode === "video") {
        push({ role: "user", content: text }); await genVideo(text);
      } else {
        push({ role: "user", content: text }); await sendChat(text);
      }
    } finally { busy = false; els.send.disabled = false; }
  }

  // ------------------------------------------------ photo
  function shrink(file) {
    return new Promise((resolve) => {
      const img = new Image(); const r = new FileReader();
      r.onload = () => { img.src = r.result; };
      img.onload = () => {
        const max = 1280, s = Math.min(1, max / Math.max(img.width, img.height));
        const cv = document.createElement("canvas"); cv.width = Math.round(img.width * s); cv.height = Math.round(img.height * s);
        cv.getContext("2d").drawImage(img, 0, 0, cv.width, cv.height);
        const thumbCv = document.createElement("canvas"); const ts = Math.min(1, 320 / Math.max(img.width, img.height));
        thumbCv.width = Math.round(img.width * ts); thumbCv.height = Math.round(img.height * ts);
        thumbCv.getContext("2d").drawImage(img, 0, 0, thumbCv.width, thumbCv.height);
        cv.toBlob((blob) => resolve({ file: new File([blob], "photo.jpg", { type: "image/jpeg" }), preview: thumbCv.toDataURL("image/jpeg", 0.7) }), "image/jpeg", 0.88);
      };
      img.onerror = () => resolve({ file, preview: "" });
      r.readAsDataURL(file);
    });
  }
  els.photoInput.onchange = async () => {
    const f = els.photoInput.files[0]; els.photoInput.value = "";
    if (!f) return;
    pendingPhoto = await shrink(f);
    els.photoThumb.src = pendingPhoto.preview; els.photoPreview.hidden = false;
    els.input.placeholder = t("photoQ"); els.input.focus();
  };
  function clearPhoto() { pendingPhoto = null; els.photoPreview.hidden = true; updateComposer(); }
  $("#removePhoto").onclick = clearPhoto;

  // ------------------------------------------------ lead form
  function openLead() { els.leadDialog.showModal ? els.leadDialog.showModal() : els.leadDialog.setAttribute("open", ""); }
  $("#leadCancel").onclick = () => els.leadDialog.close();
  els.leadForm.onsubmit = async (e) => {
    e.preventDefault();
    const data = Object.fromEntries(new FormData(els.leadForm).entries());
    data.session_id = sid;
    const btn = $("#leadSubmit"); btn.disabled = true;
    try {
      const res = await api("/api/lead", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(data) });
      if (!res.ok) throw new Error(await errText(res));
      els.leadDialog.close(); els.leadForm.reset();
      if (mode !== "growth") setMode("growth");
      push({ role: "assistant", content: "✅ " + t("leadThanks") + "\n\n[Upwork — Md Zahngir Hossain](https://www.upwork.com/freelancers/mdzahngirhossain2)" });
    } catch (err) { toast(err.message || t("netErr")); }
    btn.disabled = false;
  };

  // ------------------------------------------------ UI wiring
  function autosize() { els.input.style.height = "auto"; els.input.style.height = Math.min(els.input.scrollHeight, 160) + "px"; }
  els.input.addEventListener("input", autosize);
  els.input.addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !e.shiftKey && !e.isComposing && window.matchMedia("(pointer:fine)").matches) { e.preventDefault(); submit(); }
  });
  els.form.onsubmit = (e) => { e.preventDefault(); submit(); };
  function openDrawer() { els.drawer.classList.add("open"); els.scrim.classList.add("show"); }
  function closeDrawer() { els.drawer.classList.remove("open"); els.scrim.classList.remove("show"); }
  $("#openDrawer").onclick = openDrawer; $("#closeDrawer").onclick = closeDrawer; els.scrim.onclick = closeDrawer;
  $("#newChat").onclick = newChat; $("#newChat2").onclick = newChat;
  $("#langBtn").onclick = () => { lang = lang === "bn" ? "en" : "bn"; localStorage.setItem(LS_LANG, lang); applyI18n(); };
  $("#clearAll").onclick = () => { if (confirm(t("confirmClear"))) { chats = {}; current = null; save(); newChat(); } };

  window.addEventListener("beforeinstallprompt", (e) => { e.preventDefault(); deferredInstall = e; $("#installBtn").hidden = false; });
  $("#installBtn").onclick = async () => { if (!deferredInstall) return; deferredInstall.prompt(); await deferredInstall.userChoice; deferredInstall = null; $("#installBtn").hidden = true; };
  if ("serviceWorker" in navigator && (location.protocol === "https:" || location.hostname === "localhost" || location.hostname === "127.0.0.1")) {
    navigator.serviceWorker.register("/sw.js").catch(() => {});
  }

  if (window.NexoraAndroid && /NexoraApp/.test(navigator.userAgent)) {
    $("#serverBtn").hidden = false;
    $("#serverBtn").onclick = () => window.NexoraAndroid.openSetup();
  }

  // init
  const c = chat(); mode = c.mode || "chat";
  applyI18n(); renderMessages();
})();
