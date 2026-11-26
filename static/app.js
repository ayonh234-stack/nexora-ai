/* Nexora AI — ChatGPT-style frontend (one chat box; the AI decides text / image / video / photo edit / voice) */
(() => {
  "use strict";
  const API = (window.NEXORA_API_BASE || "").replace(/\/$/, "");
  const $ = (s) => document.querySelector(s);
  const LS_CHATS = "nexora.chats.v2", LS_OLD = "nexora.chats.v1", LS_CUR = "nexora.current.v2", LS_LANG = "nexora.lang", LS_SID = "nexora.sid", LS_THEME = "nexora.theme";

  const T = {
    bn: {
      newChat: "নতুন চ্যাট", search: "চ্যাট খুঁজুন", theme: "থিম (লাইট/ডার্ক)", server: "সার্ভার URL", install: "অ্যাপ ইনস্টল", clearAll: "সব চ্যাট মুছুন",
      leadBtn: "ফ্রি গ্রোথ কনসালটেশন", leadTitle: "ফ্রি গ্রোথ কনসালটেশন", leadSub: "তথ্য দিন, Md Zahngir Hossain নিজে যোগাযোগ করবেন।",
      fName: "নাম", fIg: "Instagram handle", fBudget: "বাজেট", fContact: "যোগাযোগ (Email / WhatsApp / Telegram)", cancel: "বাতিল", submit: "পাঠান",
      placeholder: "Nexora-কে কিছু জিজ্ঞেস করুন", photoQ: "ছবি নিয়ে প্রশ্ন, বা এডিট: যেমন “ব্যাকগ্রাউন্ড সরাও”",
      hello: "আজ কীভাবে সাহায্য করতে পারি?", helloSub: "প্রশ্ন করুন, ক্যাপশন লেখান, ছবি বানান, ছবি এডিট করান বা 🎤 চেপে কথা বলুন — সব এক জায়গায়।",
      disclaimer: "Nexora AI ভুল করতে পারে। গুরুত্বপূর্ণ তথ্য যাচাই করে নিন।",
      copy: "কপি", copied: "কপি হয়েছে", regen: "আবার লিখুন", listen: "শুনুন", download: "ডাউনলোড", rename: "নাম বদলান", del: "মুছুন",
      today: "আজ", yesterday: "গতকাল", week: "গত ৭ দিন", older: "আগের", untitled: "নতুন চ্যাট", noHistory: "এখনো কোনো চ্যাট নেই", noMatch: "কিছু পাওয়া যায়নি",
      confirmClear: "সব চ্যাট মুছে ফেলবেন?", confirmDel: "এই চ্যাটটি মুছবেন?", offline: "আপনি অফলাইনে আছেন", netErr: "নেটওয়ার্ক সমস্যা, আবার চেষ্টা করুন।",
      imgWait: "ছবি তৈরি করছি…", vidWait: "ভিডিও তৈরি হচ্ছে (২০–৯০ সেকেন্ড)…", editing: "ছবি এডিট করছি…", bgMaking: "নতুন ব্যাকগ্রাউন্ড তৈরি হচ্ছে…",
      busy: "ছবি তৈরি করছি…", altServer: "ছবি তৈরি করছি…",
      allBusy: "দুঃখিত, ফ্রি ছবি-সার্ভারগুলো এখন ব্যস্ত, তাই ছবি তৈরি হয়নি। কয়েক সেকেন্ড পরে আবার চেষ্টা করুন।",
      bgFallback: "ফ্রি ব্যাকগ্রাউন্ড-সার্ভার এখন ব্যস্ত, তাই আপাতত গ্রেডিয়েন্ট ব্যাকগ্রাউন্ড দিলাম। কিছুক্ষণ পরে আবার চাইলে আসল দৃশ্য দিতে পারব।",
      rec: "রেকর্ড হচ্ছে… থামাতে 🎤 চাপুন", micDenied: "মাইক্রোফোনের অনুমতি দিন, তারপর আবার চেষ্টা করুন।", noMic: "এই ডিভাইসে মাইক্রোফোন পাওয়া যায়নি।",
      voiceWait: "শুনছি ও উত্তর তৈরি করছি…", tooShort: "রেকর্ডিং খুব ছোট, একটু বেশি সময় ধরে বলুন।", ttsWait: "ভয়েস তৈরি হচ্ছে…",
      designing: "পোস্টের ডিজাইন তৈরি হচ্ছে…",
      saveHint: "ছবিটা চেপে ধরে রাখুন, তারপর \"Save to Photos\" / \"ছবি সংরক্ষণ\" চাপুন",
      saveHintVideo: "ভিডিওর শেয়ার বাটন চেপে \"Save Video\" চাপুন",
      saveFail: "ডাউনলোড করা গেল না, আবার চেষ্টা করুন",
      cutFail: "দুঃখিত, ফ্রি ব্যাকগ্রাউন্ড-রিমুভ সার্ভারগুলো এখন ব্যস্ত, তাই ছবিটা বদলানো হয়নি। এক মিনিট পরে আবার চেষ্টা করুন।",
      leadThanks: "ধন্যবাদ! আপনার তথ্য পৌঁছে গেছে, Md Zahngir Hossain শিগগিরই যোগাযোগ করবেন।", photo: "📷 ছবি",
      chips: [["ইনস্টাগ্রাম ক্যাপশন", "আমার কফি শপের নতুন লাতে নিয়ে ৩টি ইনস্টাগ্রাম ক্যাপশন লিখে দাও"], ["ছবি বানাও", "একটা ইনস্টাগ্রাম পোস্টের ছবি বানাও: গোলাপি ব্যাকগ্রাউন্ডে স্ট্রবেরি আইসক্রিম কোন"],
        ["ব্যবসার পরিকল্পনা", "অনলাইনে নতুন কাপড়ের ব্যবসা শুরু করতে ৩০ দিনের মার্কেটিং প্ল্যান দাও"], ["ইনস্টাগ্রাম গ্রোথ", "আমার ইনস্টাগ্রাম অর্গানিকভাবে গ্রো করতে চাই, কীভাবে শুরু করব?"]],
    },
    en: {
      newChat: "New chat", search: "Search chats", theme: "Theme (light/dark)", server: "Server URL", install: "Install app", clearAll: "Delete all chats",
      leadBtn: "Free growth consultation", leadTitle: "Free growth consultation", leadSub: "Share your details and Md Zahngir Hossain will reach out personally.",
      fName: "Name", fIg: "Instagram handle", fBudget: "Budget", fContact: "Contact (Email / WhatsApp / Telegram)", cancel: "Cancel", submit: "Send",
      placeholder: "Message Nexora AI", photoQ: "Ask about the photo, or edit it: e.g. “remove the background”",
      hello: "How can I help you today?", helloSub: "Ask anything, get captions, create images, edit photos or tap 🎤 to talk — all in one place.",
      disclaimer: "Nexora AI can make mistakes. Check important info.",
      copy: "Copy", copied: "Copied", regen: "Regenerate", listen: "Listen", download: "Download", rename: "Rename", del: "Delete",
      today: "Today", yesterday: "Yesterday", week: "Previous 7 days", older: "Older", untitled: "New chat", noHistory: "No chats yet", noMatch: "No matches",
      confirmClear: "Delete all chats?", confirmDel: "Delete this chat?", offline: "You are offline", netErr: "Network problem, please try again.",
      imgWait: "Creating image…", vidWait: "Creating your video (20–90s)…", editing: "Editing your photo…", bgMaking: "Creating the new background…",
      busy: "Creating image…", altServer: "Creating image…",
      allBusy: "Sorry, the free image servers are busy right now, so no image was created. Please try again in a few seconds.",
      bgFallback: "The free background server is busy, so I used a gradient for now. Ask again in a little while for the real scene.",
      rec: "Recording… tap 🎤 to stop", micDenied: "Please allow microphone access, then try again.", noMic: "No microphone found on this device.",
      voiceWait: "Listening and preparing a reply…", tooShort: "Recording too short — please speak a little longer.", ttsWait: "Creating voice…",
      designing: "Designing your post…",
      saveHint: "Press and hold the picture, then tap \"Save to Photos\"",
      saveHintVideo: "Use the share button and tap \"Save Video\"",
      saveFail: "Download failed, please try again",
      cutFail: "Sorry, the free background-removal servers are busy right now, so the photo was NOT changed. Please try again in a minute.",
      leadThanks: "Thank you! Your details were sent — Md Zahngir Hossain will contact you soon.", photo: "📷 Photo",
      chips: [["Instagram captions", "Write 3 Instagram captions for my coffee shop's new latte"], ["Create an image", "Make an image for an Instagram post: a strawberry ice cream cone on a pink background"],
        ["Business plan", "Give me a 30-day marketing plan to launch an online clothing store"], ["Instagram growth", "I want to grow my Instagram organically — where do I start?"]],
    },
  };
  const ICON = {
    copy: '<svg class="ico" viewBox="0 0 24 24"><rect x="9" y="9" width="11" height="11" rx="2"/><path d="M5 15V6a2 2 0 012-2h9"/></svg>',
    regen: '<svg class="ico" viewBox="0 0 24 24"><path d="M20 11a8 8 0 10-2.3 5.7M20 4v7h-7"/></svg>',
    listen: '<svg class="ico" viewBox="0 0 24 24"><path d="M11 5L6 9H3v6h3l5 4zM15.5 8.5a5 5 0 010 7M18.5 5.5a9 9 0 010 13"/></svg>',
    down: '<svg class="ico" viewBox="0 0 24 24"><path d="M12 4v11M7 10l5 5 5-5M5 20h14"/></svg>',
    edit: '<svg class="ico" viewBox="0 0 24 24"><path d="M12 20h9M16.5 3.5a2.1 2.1 0 013 3L7 19l-4 1 1-4z"/></svg>',
    trash: '<svg class="ico" viewBox="0 0 24 24"><path d="M4 7h16M10 11v6M14 11v6M6 7l1 13h10l1-13M9 7V4h6v3"/></svg>',
  };

  Object.assign(T.bn, {
    stepsDone: "ধাপ সম্পন্ন", fileGone: "ফাইলটি আর সংরক্ষিত নেই — আবার বানাতে বলুন", docReading: "ফাইল পড়ছি…", docBig: "ফাইল খুব বড় (সর্বোচ্চ 4 MB)",
    docMax: "একসাথে সর্বোচ্চ ৩টি ফাইল", docQ: "ফাইলটি নিয়ে কী জানতে চান?", docDefault: "এই ফাইলটি সংক্ষেপে বুঝিয়ে বলো",
    tgBtn: "Telegram লিংক (রিমাইন্ডার)", tgTitle: "Telegram লিংক করুন", tgSub: "রিমাইন্ডার ও প্রতিদিনের কাজ Nexora Telegram বটে পৌঁছায়। একবার লিংক করলে ওয়েব থেকে সেট করা রিমাইন্ডার সরাসরি আপনার Telegram-এ যাবে।",
    tgStep1: "Nexora বট খুলুন (Start চাপুন)", tgStep2: "বট যে কোডটি দেবে সেটা নিচে বসান", tgCode: "লিংক কোড", tgLink: "লিংক করুন", tgUnlink: "লিংক বাদ দিন",
    tgLinked: "✅ Telegram লিংক হয়েছে", tgIsLinked: "এই ব্রাউজার Telegram-এর সাথে লিংক করা আছে",
    vTitle: "ভল্ট", vOff: "ভল্ট চালু নেই", vSetupTitle: "ভল্ট PIN সেট করুন", vSetupSub: "শুধু মালিকের জন্য। কোডটি আপনার (অ্যাডমিন) Telegram-এ যাবে।",
    vSendCode: "Telegram-এ কোড পাঠাও", vCode: "৬ সংখ্যার কোড", vNewPin: "নতুন PIN (৬–১২ সংখ্যা বা ৮+ অক্ষরের পাসফ্রেজ)", vPin2: "PIN আবার লিখুন",
    vSave: "সেভ", vCodeSent: "কোড পাঠানো হয়েছে — Telegram দেখুন", vMismatch: "দুটো PIN মেলেনি", vUnlockSub: "ভল্ট খুলতে PIN দিন।", vForgot: "PIN ভুলে গেছেন / প্রথমবার সেট করবেন?",
    vUnlock: "খুলুন", vLocked: "ভল্ট লক — আবার PIN দিন", vEmpty: "এখনও কিছু রাখা হয়নি", vInfo: "সব কিছু এনক্রিপ্ট করে রাখা। Nexora কাজের সময় ব্যবহার করবে, কিন্তু কখনও মান দেখাবে না।",
    vAdd: "নতুন যোগ করুন", vName: "নাম", vValue: "মান (পাসওয়ার্ড / API key)", vNote: "নোট (ঐচ্ছিক)", vLock: "লক", vDone: "ঠিক আছে", vDelQ: "মুছে ফেলবেন",
  });
  Object.assign(T.en, {
    stepsDone: "steps done", fileGone: "file no longer stored — ask again to recreate it", docReading: "Reading file…", docBig: "File too large (max 4 MB)",
    docMax: "Up to 3 files at once", docQ: "What do you want to know about the file?", docDefault: "Summarize this file",
    tgBtn: "Telegram link (reminders)", tgTitle: "Link Telegram", tgSub: "Reminders and daily tasks are delivered by the Nexora Telegram bot. Link once and reminders you set on the web go straight to your Telegram.",
    tgStep1: "Open the Nexora bot (tap Start)", tgStep2: "Paste the code the bot sends you below", tgCode: "Link code", tgLink: "Link", tgUnlink: "Unlink",
    tgLinked: "✅ Telegram linked", tgIsLinked: "This browser is linked to Telegram",
    vTitle: "Vault", vOff: "Vault is not enabled", vSetupTitle: "Set vault PIN", vSetupSub: "Owner only. The code is sent to your (admin) Telegram.",
    vSendCode: "Send code to Telegram", vCode: "6-digit code", vNewPin: "New PIN (6–12 digits or an 8+ character passphrase)", vPin2: "Repeat PIN",
    vSave: "Save", vCodeSent: "Code sent — check Telegram", vMismatch: "PINs don't match", vUnlockSub: "Enter your PIN to open the vault.", vForgot: "Forgot PIN / first-time setup?",
    vUnlock: "Unlock", vLocked: "Vault locked — enter PIN again", vEmpty: "Nothing stored yet", vInfo: "Everything is encrypted. Nexora uses entries for tasks but never shows the values.",
    vAdd: "Add new", vName: "Name", vValue: "Value (password / API key)", vNote: "Note (optional)", vLock: "Lock", vDone: "Done", vDelQ: "Delete",
  });
  let lang = localStorage.getItem(LS_LANG) || "bn";
  const IS_IOS = /iPad|iPhone|iPod/.test(navigator.userAgent) || (navigator.platform === "MacIntel" && navigator.maxTouchPoints > 1);
  const fileCache = new Map();
  let sid = localStorage.getItem(LS_SID);
  if (!sid) { sid = (crypto.randomUUID ? crypto.randomUUID() : String(Date.now()) + Math.random()).replace(/[^a-z0-9-]/gi, ""); localStorage.setItem(LS_SID, sid); }
  let chats = load();
  let current = localStorage.getItem(LS_CUR);
  let busy = false, pendingPhoto = null, deferredInstall = null, query = "";
  const audioCache = new Map();
  const els = {
    layout: $("#layout"), scroller: $("#scroller"), thread: $("#thread"), input: $("#input"), form: $("#composer"), send: $("#sendBtn"),
    mic: $("#micBtn"), recStatus: $("#recStatus"), history: $("#history"), search: $("#search"), photoInput: $("#photoInput"),
    photoPreview: $("#photoPreview"), photoThumb: $("#photoThumb"), toast: $("#toast"), leadDialog: $("#leadDialog"), leadForm: $("#leadForm"),
  };
  const t = (k) => (T[lang] || T.bn)[k];
  const uid = () => Date.now().toString(36) + Math.random().toString(36).slice(2, 7);
  const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

  // ------------------------------------------------ storage
  function load() {
    try {
      const v2 = JSON.parse(localStorage.getItem(LS_CHATS));
      if (v2) return v2;
      const v1 = JSON.parse(localStorage.getItem(LS_OLD)) || {}; // migrate chats from the old UI
      Object.values(v1).forEach((c) => { c.messages = (c.messages || []).filter((m) => !m.pending); });
      return v1;
    } catch { return {}; }
  }
  function save() {
    const ids = Object.keys(chats).sort((a, b) => chats[b].updated - chats[a].updated);
    ids.slice(80).forEach((id) => delete chats[id]);
    Object.values(chats).forEach((c) => { c.messages = c.messages.slice(-150); });
    const persist = () => localStorage.setItem(LS_CHATS, JSON.stringify(chats, (k, v) => (k === "pending" || k === "autoplay" ? undefined : v)));
    try { persist(); }
    catch { // quota: strip big inline media, oldest chats first
      const order = Object.values(chats).sort((a, b) => a.updated - b.updated);
      for (const c of order) {
        c.messages.forEach((m) => {
          if (m.photo && m.photo.startsWith("data:")) m.photo = "";
          if (m.url && m.url.startsWith("data:")) { m.content = (m.type === "video" ? "🎬 " : "🖼️ ") + (m.prompt || ""); m.url = ""; m.type = ""; }
        });
        try { persist(); break; } catch {}
      }
    }
    if (current) localStorage.setItem(LS_CUR, current);
  }
  function chat() {
    if (!current || !chats[current]) { current = "c" + uid(); chats[current] = { id: current, title: "", messages: [], updated: Date.now() }; }
    return chats[current];
  }

  // ------------------------------------------------ helpers
  function toast(msg) { els.toast.textContent = msg; els.toast.classList.add("show"); clearTimeout(toast._t); toast._t = setTimeout(() => els.toast.classList.remove("show"), 2600); }
  function esc(s) { const d = document.createElement("div"); d.textContent = s == null ? "" : String(s); return d.innerHTML; }
  function url(u) { return u && u.startsWith("/") ? API + u : u; }
  function md(text) { return DOMPurify.sanitize(marked.parse(text || "", { breaks: true, gfm: true }), { ADD_ATTR: ["target"] }); }
  const CLIENT_VERSION = "13";
  async function api(path, opts) {
    opts = opts || {}; opts.headers = Object.assign({ "X-Nexora-Client": CLIENT_VERSION }, agentHeaders(), opts.headers || {});
    return fetch(API + path, opts);
  }
  const LS_OWNER = "nexora.owner", LS_TG = "nexora.tg";
  function ownerToken() { const tk = localStorage.getItem(LS_OWNER) || ""; const exp = Number(tk.split(".")[0]); return exp && exp * 1000 > Date.now() ? tk : ""; }
  function agentHeaders() {
    const h = {}; const o = ownerToken(), tg = localStorage.getItem(LS_TG);
    if (o) h["X-Nexora-Owner"] = o; if (tg) h["X-Nexora-TG"] = tg;
    try { h["X-Nexora-TZ"] = Intl.DateTimeFormat().resolvedOptions().timeZone || "Asia/Dhaka"; } catch (_) { }
    return h;
  }
  async function errText(res) { try { const j = await res.json(); return typeof j.detail === "string" ? j.detail : t("netErr"); } catch { return t("netErr"); } }
  const nearBottom = () => els.scroller.scrollHeight - els.scroller.scrollTop - els.scroller.clientHeight < 140;
  function scrollEnd(force) { if (force || nearBottom()) requestAnimationFrame(() => { els.scroller.scrollTop = els.scroller.scrollHeight; }); }

  // ------------------------------------------------ i18n / theme
  function applyI18n() {
    document.documentElement.lang = lang;
    document.querySelectorAll("[data-i18n]").forEach((el) => { const v = t(el.dataset.i18n); if (typeof v === "string") el.textContent = v; });
    $("#langLabel").textContent = lang === "bn" ? "English" : "বাংলা";
    els.search.placeholder = t("search"); $("#disclaimer").textContent = t("disclaimer");
    if (!pendingPhoto) els.input.placeholder = t("placeholder");
    renderHistory(); if (!chat().messages.length) renderThread();
  }
  function setTheme(th) { document.documentElement.dataset.theme = th; localStorage.setItem(LS_THEME, th); document.querySelector('meta[name="theme-color"]').content = th === "light" ? "#ffffff" : "#212121"; }

  // ------------------------------------------------ sidebar
  const isMobile = () => matchMedia("(max-width: 860px)").matches;
  function openSide() { if (isMobile()) els.layout.classList.add("side-open"); else els.layout.classList.toggle("side-closed"); }
  function closeSide() { els.layout.classList.remove("side-open"); }
  function groupOf(ts) {
    const d0 = new Date(); d0.setHours(0, 0, 0, 0); const day = 86400000;
    if (ts >= d0.getTime()) return "today"; if (ts >= d0.getTime() - day) return "yesterday"; if (ts >= d0.getTime() - 7 * day) return "week"; return "older";
  }
  function renderHistory() {
    els.history.innerHTML = "";
    const q = query.trim().toLowerCase();
    let list = Object.values(chats).filter((c) => c.messages.length).sort((a, b) => b.updated - a.updated);
    if (q) list = list.filter((c) => (c.title || "").toLowerCase().includes(q) || c.messages.some((m) => (m.content || "").toLowerCase().includes(q)));
    if (!list.length) { els.history.innerHTML = `<div class="h-empty">${esc(q ? t("noMatch") : t("noHistory"))}</div>`; return; }
    let last = "";
    list.forEach((c) => {
      const g = groupOf(c.updated);
      if (g !== last) { const h = document.createElement("div"); h.className = "h-group"; h.textContent = t(g); els.history.appendChild(h); last = g; }
      const it = document.createElement("div"); it.className = "h-item" + (c.id === current ? " active" : ""); it.dataset.id = c.id;
      it.innerHTML = `<span class="t">${esc(c.title || t("untitled"))}</span><button class="h-act ren" title="${esc(t("rename"))}" aria-label="${esc(t("rename"))}">${ICON.edit}</button><button class="h-act del" title="${esc(t("del"))}" aria-label="${esc(t("del"))}">${ICON.trash}</button>`;
      it.onclick = (e) => {
        if (e.target.closest(".del")) { if (confirm(t("confirmDel"))) { delete chats[c.id]; if (current === c.id) { current = null; renderThread(); } save(); renderHistory(); } return; }
        if (e.target.closest(".ren")) { renameChat(it, c); return; }
        if (e.target.tagName === "INPUT") return;
        current = c.id; save(); renderThread(true); renderHistory(); closeSide();
      };
      els.history.appendChild(it);
    });
  }
  function renameChat(it, c) {
    const span = it.querySelector(".t"); const inp = document.createElement("input"); inp.value = c.title || ""; inp.maxLength = 80;
    span.replaceWith(inp); inp.focus(); inp.select();
    const done = (ok) => { if (ok && inp.value.trim()) { c.title = inp.value.trim(); c.renamed = true; save(); } renderHistory(); };
    inp.onkeydown = (e) => { if (e.key === "Enter") done(true); if (e.key === "Escape") done(false); };
    inp.onblur = () => done(true);
  }
  function newChat() { current = null; chat(); renderThread(); renderHistory(); closeSide(); clearPhoto(); els.input.focus({ preventScroll: true }); }

  // ------------------------------------------------ thread rendering
  function renderEmpty() {
    const w = document.createElement("div"); w.className = "empty";
    w.innerHTML = `<img class="logo" src="/icons/icon.svg" alt=""><h2>${esc(t("hello"))}</h2><p>${esc(t("helloSub"))}</p><div class="chips"></div>`;
    t("chips").forEach(([title, text]) => {
      const b = document.createElement("button"); b.className = "chip"; b.type = "button";
      b.innerHTML = `<b>${esc(title)}</b><span>${esc(text)}</span>`;
      b.onclick = () => { els.input.value = text; autosize(); submit(); };
      w.querySelector(".chips").appendChild(b);
    });
    els.thread.appendChild(w);
  }
  function renderThread(toBottom) {
    els.thread.innerHTML = "";
    const c = chat();
    if (!c.messages.length) renderEmpty();
    c.messages.forEach((m) => { const e = msgEl(m); e.classList.add("still"); els.thread.appendChild(e); });
    if (toBottom !== false) scrollEnd(true);
  }
  function isLastBot(m) { const ms = chat().messages; return ms[ms.length - 1] === m; }
  function msgEl(m) {
    const row = document.createElement("div"); row.className = "msg " + (m.role === "user" ? "user" : "bot");
    if (m.role === "user") {
      const b = document.createElement("div"); b.className = "bubble";
      if (m.photo) { const im = document.createElement("img"); im.className = "upload"; im.src = m.photo; im.alt = "photo"; row.appendChild(im); }
      (m.docs || []).forEach((d) => { const c = document.createElement("div"); c.className = "doc-chip"; c.textContent = "📄 " + d.name; row.appendChild(c); });
      if (m.content) { b.textContent = m.content; row.appendChild(b); }
      return row;
    }
    row.innerHTML = `<img class="avatar" src="/icons/icon.svg" alt="">`;
    const body = document.createElement("div"); body.className = "body"; row.appendChild(body);
    fillBody(body, m);
    return row;
  }
  function fillBody(body, m) {
    body.innerHTML = "";
    if (m.pending && !m.content) {
      body.innerHTML = stepsHtml(m, true) + `<span class="typing"><i></i><i></i><i></i></span>${m.progress ? `<div class="progress">${esc(m.progress)}</div>` : ""}`;
      return;
    }
    if ((m.type === "image" || m.type === "video") && m.url) {
      const media = m.type === "image"
        ? `<img class="gen${m.fname && m.fname.endsWith(".png") ? " checker" : ""}" src="${esc(url(m.url))}" alt="${esc(m.prompt || "")}" referrerpolicy="no-referrer">`
        : `<video class="gen" src="${esc(url(m.url))}" controls autoplay loop muted playsinline></video>`;
      body.innerHTML = (m.content ? `<div class="md">${md(m.content)}</div>` : "") +
        (m.compare ? `<img class="gen compare" src="${esc(m.compare)}" alt="before / after">` : "") + media + (m.prompt ? `<div class="progress">${m.fname ? "✅" : m.type === "video" ? "🎬" : "🎨"} ${esc(m.prompt)}</div>` : "");
    } else {
      if (m.steps && m.steps.length) body.insertAdjacentHTML("beforeend", stepsHtml(m, false));
      const div = document.createElement("div"); div.className = "md" + (m.error ? " err" : "") + (m.streaming ? " cursor" : "");
      div.innerHTML = md(m.content); body.appendChild(div);
      enhanceMd(div);
    }
    if (m.files && m.files.length) body.appendChild(filesEl(m));
    (m.links || []).forEach((l) => { const a = document.createElement("a"); a.className = "link-btn"; a.href = l.url; a.target = "_blank"; a.rel = "noopener"; a.textContent = l.label; body.appendChild(a); });
    if (m.type === "image" && /^https?:\/\/image\.pollinations\.ai\//.test(m.url || "")) { // chats saved by older versions
      const im = body.querySelector("img.gen"); const legacy = m.url; im.removeAttribute("src"); im.style.minHeight = "120px";
      fetchRealImage(legacy, null, 1).then((du) => {
        if (du) { m.url = du; im.src = du; save(); }
        else { m.type = ""; m.url = ""; m.content = "🖼️ " + (m.prompt || ""); m.regen = { kind: "image", prompt: m.prompt || "" }; fillBody(body, m); save(); }
      });
    }
    if (m.aid && audioCache.has(m.aid)) addAudio(body, audioCache.get(m.aid), m.autoplay);
    if (!m.pending && !m.streaming) body.appendChild(actionsEl(m, body));
  }
  function enhanceMd(div) {
    div.querySelectorAll("a").forEach((a) => { a.target = "_blank"; a.rel = "noopener"; });
    div.querySelectorAll("pre").forEach((pre) => {
      const code = pre.querySelector("code"); if (!code || pre.querySelector(".code-head")) return;
      const langName = ((code.className || "").match(/language-([\w+#-]+)/) || [])[1] || "code";
      const head = document.createElement("div"); head.className = "code-head";
      head.innerHTML = `<span>${esc(langName)}</span><button type="button">${ICON.copy.replace('class="ico"', 'class="ico" style="width:14px;height:14px;vertical-align:-2px"')} ${esc(t("copy"))}</button>`;
      head.querySelector("button").onclick = () => navigator.clipboard?.writeText(code.innerText).then(() => toast(t("copied")));
      pre.prepend(head);
    });
  }
  function actionsEl(m, body) {
    const a = document.createElement("div"); a.className = "actions";
    const btn = (icon, label, fn) => { const b = document.createElement("button"); b.type = "button"; b.title = label; b.innerHTML = `${icon}<span>${esc(label)}</span>`; b.onclick = fn; a.appendChild(b); return b; };
    if (m.content && !m.error) btn(ICON.copy, t("copy"), () => navigator.clipboard?.writeText(m.content).then(() => toast(t("copied"))));
    if (m.url && (m.type === "image" || m.type === "video")) {
      const d = document.createElement("a"); d.href = url(m.url); d.download = m.fname || (m.type === "video" ? "nexora.mp4" : "nexora.jpg"); d.target = "_blank"; d.rel = "noopener";
      d.innerHTML = `${ICON.down}<span>${esc(t("download"))}</span>`; a.appendChild(d);
      if (IS_IOS) prepFile(d.href, d.download); // ready before the tap, so iOS keeps the gesture for share()
    }
    if (m.content && !m.error && !(m.aid && audioCache.has(m.aid)) && !m.type) {
      const sp = btn(ICON.listen, t("listen"), () => speak(m, body, sp));
    }
    if (isLastBot(m) && !busy && (m.regen || m.error)) btn(ICON.regen, t("regen"), () => regenerate(m));
    return a;
  }
  function addAudio(body, src, autoplay) {
    const au = document.createElement("audio"); au.className = "voice-audio"; au.controls = true; au.preload = "auto"; au.src = src;
    body.prepend(au); if (autoplay) au.play().catch(() => {}); return au;
  }

  // ------------------------------------------------ messaging
  function push(m) {
    const c = chat(); m.id = m.id || uid(); c.messages.push(m); c.updated = Date.now();
    if (!c.renamed && m.role === "user" && (!c.title || c.title === t("photo"))) c.title = autoTitle(m);
    if (c.messages.length === 1) els.thread.innerHTML = "";
    const el = msgEl(m); els.thread.appendChild(el);
    save(); renderHistory(); scrollEnd(true); refreshPrevActions();
    return { m, el };
  }
  function autoTitle(m) {
    let s = (m.content || "").replace(/^🎤\s*/, "").replace(/\s+/g, " ").trim();
    if (!s) return t("photo");
    if (s.length > 42) s = s.slice(0, 42).replace(/\s+\S*$/, "") + "…";
    return s;
  }
  function refresh(ref) { const n = msgEl(ref.m); n.classList.add("still"); ref.el.replaceWith(n); ref.el = n; save(); scrollEnd(); }
  function refreshPrevActions() { // remove "regenerate" from older answers
    const rows = els.thread.querySelectorAll(".msg.bot"); rows.forEach((r, i) => { if (i < rows.length - 1) r.querySelectorAll(".actions button").forEach((b) => { if (b.title === t("regen")) b.remove(); }); });
  }
  function historyPayload(uptoIndex) {
    const ms = chat().messages.slice(0, uptoIndex);
    return ms.filter((m) => !m.pending && !m.error).slice(-20).map((m) => ({
      role: m.role === "user" ? "user" : "assistant",
      content: m.type === "image" ? `[Image shown to the user: ${m.prompt}]` : m.type === "video" ? `[Video shown to the user: ${m.prompt}]` : (m.photo ? `[photo] ${m.content || ""}` :
        m.docs && m.docs.length ? m.docs.map((d) => `[Attached file: ${d.name}]\n${(d.text || "(content no longer available)").slice(0, 12000)}`).join("\n\n") + "\n\n[User message]\n" + (m.content || "") :
        (m.files && m.files.length ? m.content + "\n[Files sent: " + m.files.map((f) => f.name).join(", ") + "]" : m.content || "")),
    })).filter((m) => m.content.trim());
  }

  async function sendChat(text, bot, docs) {
    const c = chat(); const idx = c.messages.indexOf(bot.m);
    if (!docs) { const um = c.messages[idx - 1]; if (um && um.docs && um.docs.length && um.docs[0].text) docs = um.docs; }
    bot.m.regen = { kind: "chat", text };
    try {
      const res = await api("/api/chat", { method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message: text, mode: "auto", session_id: sid + ":" + current, history: historyPayload(idx - 1), stream: true,
          attachments: (docs || []).map((d) => ({ name: d.name, text: d.text || "" })) }) });
      if (!res.ok) throw new Error(await errText(res));
      const ct = res.headers.get("content-type") || "";
      if (ct.includes("application/json")) {
        const j = await res.json();
        if (j.action) return mediaAction(j.action, j.prompt, bot);
        Object.assign(bot.m, { content: j.reply || "", pending: false }); refresh(bot); return;
      }
      const reader = res.body.getReader(); const dec = new TextDecoder(); let buf = "", acc = "", lastPaint = 0, action = null;
      const md_ = () => bot.el.querySelector(".md");
      for (;;) {
        const { value, done } = await reader.read(); if (done) break;
        buf += dec.decode(value, { stream: true }); let i;
        while ((i = buf.indexOf("\n\n")) >= 0) {
          const line = buf.slice(0, i).trim(); buf = buf.slice(i + 2);
          if (!line.startsWith("data:")) continue;
          const ev = JSON.parse(line.slice(5));
          if (ev.delta) acc += ev.delta;
          if (ev.action) action = ev;
          if (ev.error) { bot.m.error = !acc; acc = acc ? acc + "\n\n" + ev.error : ev.error; }
          if (ev.tool) { (bot.m.steps = bot.m.steps || []).push(ev.tool.label); if (!acc) refresh(bot); }
          if (ev.file) { (bot.m.files = bot.m.files || []).push(ev.file); }
          if (ev.link) { (bot.m.links = bot.m.links || []).push(ev.link); }
          if (ev.tg_link) { localStorage.setItem(LS_TG, ev.tg_link); toast(t("tgLinked")); }
        }
        if (acc && !action) {
          Object.assign(bot.m, { content: acc, pending: false, streaming: true });
          const now = performance.now();
          if (!md_()) fillBody(bot.el.querySelector(".body"), bot.m);
          else if (now - lastPaint > 50) { const d = md_(); d.innerHTML = md(acc); lastPaint = now; scrollEnd(); }
        }
      }
      if (action) {
        if (acc.trim()) { Object.assign(bot.m, { content: acc, pending: false, streaming: false, regen: null }); refresh(bot); bot = push({ role: "assistant", content: "", pending: true }); }
        return mediaAction(action.action, action.prompt, bot);
      }
      Object.assign(bot.m, { content: acc || ((bot.m.files || []).length ? "" : t("netErr")), pending: false, streaming: false }); refresh(bot);
    } catch (e) { Object.assign(bot.m, { pending: false, streaming: false, error: true, content: e.message || t("netErr") }); refresh(bot); }
  }
  function mediaAction(kind, prompt, bot) {
    Object.assign(bot.m, { pending: true, content: "", progress: kind === "image" ? t("imgWait") : t("vidWait") }); refresh(bot);
    return kind === "video" ? genVideo(prompt, bot) : genImage(prompt, bot);
  }

  // ---- free image sources. Never trust a Pollinations picture blindly: when the visitor is rate-limited it
  // answers with a "Busy right now" / "Free limit reached" notice image, which must never be shown.
  function blobToDataURL(b) { return new Promise((res, rej) => { const r = new FileReader(); r.onload = () => res(r.result); r.onerror = rej; r.readAsDataURL(b); }); }
  const PLACEHOLDER_SIZES = new Set([91585, 83870]);
  const PLACEHOLDER_SHA256 = new Set(["116b73d9224bb6a5a503addf0105616b8efb60996a54acc1e40909c3f2f18ec1", "5b0c323c4889eeb9809c928cba3606c897a36fb3a17b0dc6caf225913b72a82d"]);
  async function looksLikePlaceholder(blob, dataUrl) {
    if (PLACEHOLDER_SIZES.has(blob.size)) return true;
    try {
      if (crypto.subtle) {
        const h = Array.from(new Uint8Array(await crypto.subtle.digest("SHA-256", await blob.arrayBuffer()))).map((x) => x.toString(16).padStart(2, "0")).join("");
        if (PLACEHOLDER_SHA256.has(h)) return true;
      }
      // The notice has a cream text panel across the bottom quarter.
      const im = await loadImg(dataUrl); const cv = document.createElement("canvas"); cv.width = cv.height = 64;
      const g = cv.getContext("2d"); g.drawImage(im, 0, 0, 64, 64);
      const d = g.getImageData(0, 48, 64, 16).data; let cream = 0, dark = 0; const n = d.length / 4;
      for (let i = 0; i < d.length; i += 4) {
        const r = d[i], gg = d[i + 1], b = d[i + 2];
        if (r > 232 && gg > 226 && b > 212 && Math.max(r, gg, b) - Math.min(r, gg, b) < 30) cream++;
        if (r + gg + b < 240) dark++;
      }
      return cream / n > 0.75 && dark / n > 0.005 && dark / n < 0.2;
    } catch { return false; }
  }
  async function fetchRealImage(u, onWait, tries = 1) {
    for (let i = 0; i < tries; i++) {
      let wait = 6;
      try {
        const res = await fetch(u + (i ? `&r=${i}` : ""), { mode: "cors", referrerPolicy: "no-referrer", cache: "no-store" });
        const ct = res.headers.get("content-type") || "";
        if (res.ok && ct.startsWith("image/")) {
          const b = await res.blob();
          if (b.size > 2000) { const du = await blobToDataURL(b); if (!(await looksLikePlaceholder(b, du))) return du; }
        }
        const ra = parseFloat(res.headers.get("retry-after") || ""); if (ra > 0) wait = Math.min(10, ra + 1);
      } catch {}
      if (i < tries - 1) for (let left = Math.round(wait); left > 0; left--) { onWait && onWait(t("busy").replace("{s}", left)); await sleep(1000); }
    }
    return null;
  }
  // Free Hugging Face Spaces called straight from the visitor's browser: their free GPU quota is per visitor IP.
  async function hfCall(host, api, data, timeoutMs = 120000) {
    const ctl = new AbortController(); const timer = setTimeout(() => ctl.abort(), timeoutMs);
    try {
      const r = await fetch(`${host}/gradio_api/call/${api}`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ data }), signal: ctl.signal });
      if (!r.ok) throw new Error("hf " + r.status);
      const { event_id } = await r.json();
      const s = await fetch(`${host}/gradio_api/call/${api}/${event_id}`, { signal: ctl.signal });
      const txt = await s.text();
      const m = txt.match(/event: complete\s*\ndata: (.*)/);
      if (!m) throw new Error("hf error");
      return JSON.parse(m[1]);
    } finally { clearTimeout(timer); }
  }
  async function hfFile(host, item) {
    const u = item && item.path ? `${host}/gradio_api/file=${item.path}` : item && item.url;
    const r = await fetch(u); if (!r.ok) throw new Error("hf file " + r.status);
    return blobToDataURL(await r.blob());
  }
  async function hfUpload(host, blob) {
    const fd = new FormData(); fd.append("files", blob, "photo.jpg");
    const r = await fetch(`${host}/gradio_api/upload`, { method: "POST", body: fd }); if (!r.ok) throw new Error("upload " + r.status);
    const [path] = await r.json(); return { path, meta: { _type: "gradio.FileData" } };
  }
  const FLUX = "https://black-forest-labs-flux-1-schnell.hf.space";
  async function browserFlux(prompt, w, h) {
    const s = Math.min(1, 1024 / Math.max(w || 1024, h || 1024));
    const W = Math.max(256, Math.floor(((w || 1024) * s) / 32) * 32), H = Math.max(256, Math.floor(((h || 1024) * s) / 32) * 32);
    try { const res = await hfCall(FLUX, "infer", [prompt.slice(0, 700), 0, true, W, H, 4], 90000); return await hfFile(FLUX, res[0]); }
    catch { return null; }
  }
  async function browserCutout(file) {
    const spaces = [["https://not-lain-background-removal.hf.space", "png", (f) => [f], 0], ["https://kenjiedec-rembg.hf.space", "inference", (f) => [f, "isnet-general-use", 0, 0], 0]];
    for (const [host, api, args, idx] of spaces) {
      try { const f = await hfUpload(host, file); const res = await hfCall(host, api, args(f), 120000); return await hfFile(host, res[idx]); }
      catch {}
    }
    return null;
  }
  async function serverFallbackImage(prompt, w, h) {
    try {
      const res = await api("/api/image/fallback", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ prompt, width: w || 1024, height: h || 1024 }) });
      if (!res.ok) return null; const j = await res.json(); return j.url || null;
    } catch { return null; }
  }
  // FLUX.1-schnell from this browser (best quality; free quota per visitor) -> FLUX via the server ->
  // Pollinations (checked, lower quality) -> Pollinations again after its wait.
  async function freeImage(pollUrl, prompt, w, h, onWait) {
    let src = await browserFlux(prompt, w, h);
    if (!src) { onWait && onWait(t("altServer")); src = await serverFallbackImage(prompt, w, h); }
    if (!src && pollUrl) src = await fetchRealImage(pollUrl, onWait, 1);
    if (!src && pollUrl) src = await fetchRealImage(pollUrl + "&retry=1", onWait, 2);
    return src;
  }
  function setProgress(ref, text) { ref.m.progress = text; const p = ref.el.querySelector(".progress"); if (p) p.textContent = text; else refresh(ref); }
  async function genImage(prompt, ref) {
    ref.m.regen = { kind: "image", prompt };
    try {
      const idx = chat().messages.indexOf(ref.m);
      const context = idx > 0 ? historyPayload(idx - 1).slice(-6) : [];
      const res = await api("/api/image", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ prompt, context }) });
      if (!res.ok) throw new Error(await errText(res));
      const j = await res.json(); let src = j.url;
      if (j.kind === "design") { // text post: AI paints a text-free background, the server typesets the exact words
        setProgress(ref, t("designing"));
        const bg = await freeImage(j.bg_url, j.bg_prompt, j.width, j.height, (x) => setProgress(ref, x));
        setProgress(ref, t("designing"));
        const r2 = await api("/api/design/render", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ spec: j.spec, background: bg && bg.startsWith("data:") ? bg : "" }) });
        if (!r2.ok) throw new Error(await errText(r2));
        src = (await r2.json()).url;
        Object.assign(ref.m, { pending: false, type: "image", url: src, prompt: j.prompt || prompt, content: "", progress: "", error: false, fname: "nexora-post.png" });
        refresh(ref); return;
      }
      if (j.source === "pollinations-direct") {
        src = await freeImage(j.url, j.prompt || prompt, 1024, 1024, (x) => setProgress(ref, x));
        if (!src) throw new Error(t("allBusy"));
      }
      Object.assign(ref.m, { pending: false, type: "image", url: src, prompt: j.prompt || prompt, content: "", progress: "", error: false });
    } catch (e) { Object.assign(ref.m, { pending: false, error: true, content: e.message || t("netErr"), progress: "" }); }
    refresh(ref);
  }
  async function genVideo(prompt, ref) {
    ref.m.regen = { kind: "video", prompt };
    const started = Date.now();
    const timer = setInterval(() => setProgress(ref, `${t("vidWait")} ${Math.round((Date.now() - started) / 1000)}s`), 1000);
    try {
      const res = await api("/api/video", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ prompt }) });
      if (!res.ok) throw new Error(await errText(res));
      const j = await res.json();
      Object.assign(ref.m, { pending: false, type: "video", url: j.url, prompt: j.prompt || prompt, content: "", progress: "", error: false });
    } catch (e) { Object.assign(ref.m, { pending: false, error: true, content: e.message || t("netErr"), progress: "" }); }
    clearInterval(timer); refresh(ref);
  }
  function loadImg(src) { return new Promise((res, rej) => { const im = new Image(); im.onload = () => res(im); im.onerror = rej; im.src = src; }); }
  async function compositeCutout(cutoutUrl, bgUrl) {
    const fg = await loadImg(cutoutUrl);
    const cv = document.createElement("canvas"); cv.width = fg.naturalWidth; cv.height = fg.naturalHeight; const g = cv.getContext("2d");
    if (bgUrl) { const bg = await loadImg(bgUrl); const s = Math.max(cv.width / bg.naturalWidth, cv.height / bg.naturalHeight); const w = bg.naturalWidth * s, h = bg.naturalHeight * s; g.drawImage(bg, (cv.width - w) / 2, (cv.height - h) / 2, w, h); }
    else { const gr = g.createLinearGradient(0, 0, 0, cv.height); gr.addColorStop(0, "#6366f1"); gr.addColorStop(1, "#ec4899"); g.fillStyle = gr; g.fillRect(0, 0, cv.width, cv.height); }
    g.drawImage(fg, 0, 0); return cv.toDataURL("image/jpeg", 0.9);
  }
  async function sendPhoto(file, question, bot) {
    bot.m.progress = t("editing"); refresh(bot);
    try {
      const fd = new FormData(); fd.append("file", file, file.name || "photo.jpg"); fd.append("question", question || "");
      const res = await api("/api/vision", { method: "POST", body: fd });
      if (!res.ok) throw new Error(await errText(res));
      const j = await res.json();
      if (j.edit) {
        let img = j.image, cutout = j.cutout, note = j.reply || "";
        if (j.client_cutout) { // the server's free cutout servers were busy: do it from this browser
          setProgress(bot, t("editing"));
          cutout = await browserCutout(file);
          if (!cutout) throw new Error(t("cutFail"));
          if (j.op === "remove_bg") img = cutout;
        }
        if (j.op === "replace_bg") {
          const fg = await loadImg(cutout); const w = fg.naturalWidth, h = fg.naturalHeight;
          setProgress(bot, t("bgMaking"));
          const s = 1024 / Math.max(w, h); const bw = Math.max(256, Math.floor((w * s) / 32) * 32), bh = Math.max(256, Math.floor((h * s) / 32) * 32);
          const pollUrl = j.bg_url || `https://image.pollinations.ai/prompt/${encodeURIComponent(j.bg_prompt.slice(0, 700))}?width=${bw}&height=${bh}&nologo=true&seed=${Math.floor(Math.random() * 2e9)}`;
          const bg = await freeImage(pollUrl, j.bg_prompt, bw, bh, (x) => setProgress(bot, x));
          if (!bg) note = "✅ " + t("bgFallback");
          img = await compositeCutout(cutout, bg);
        }
        Object.assign(bot.m, { pending: false, type: "image", url: img, prompt: note.replace(/^✅\s*/, ""), content: "", compare: j.compare || null, progress: "", fname: j.op === "remove_bg" ? "nexora-no-background.png" : j.op === "enhance" ? "nexora-hd.jpg" : "nexora-edit.jpg" });
      } else Object.assign(bot.m, { pending: false, content: j.reply, progress: "" });
    } catch (e) { Object.assign(bot.m, { pending: false, error: true, content: e.message || t("netErr"), progress: "" }); }
    refresh(bot);
  }
  async function regenerate(m) {
    if (busy || !m.regen) return;
    const r = m.regen; busy = true; setBusy(true);
    const c = chat(); const i = c.messages.indexOf(m); const row = els.thread.querySelectorAll(".msg")[i];
    Object.assign(m, { content: "", error: false, pending: true, type: "", url: "", prompt: "", aid: "", progress: "" });
    const ref = { m, el: row || msgEl(m) }; refresh(ref);
    try {
      if (r.kind === "image") await genImage(r.prompt, ref);
      else if (r.kind === "video") await genVideo(r.prompt, ref);
      else await sendChat(r.text, ref);
    } finally { busy = false; setBusy(false); }
  }
  function setBusy(b) { els.send.disabled = b; els.mic.disabled = b; }

  async function submit() {
    if (busy) return;
    const text = els.input.value.trim();
    if (!text && !pendingPhoto && !pendingDocs.length) return;
    if (docBusy) { toast(t("docReading")); return; }
    if (!navigator.onLine) { toast(t("offline")); return; }
    busy = true; setBusy(true);
    els.input.value = ""; autosize(); refreshPrevActions();
    try {
      if (pendingPhoto) {
        const { file, preview } = pendingPhoto; clearPhoto();
        push({ role: "user", content: text, photo: preview });
        const bot = push({ role: "assistant", content: "", pending: true });
        await sendPhoto(file, text, bot);
      } else if (pendingDocs.length) {
        const docs = pendingDocs.slice(); clearDocs();
        const q = text || t("docDefault");
        push({ role: "user", content: q, docs });
        const bot = push({ role: "assistant", content: "", pending: true });
        await sendChat(q, bot, docs);
      } else {
        if (/^\/vault\b/i.test(text)) { openVault(); return; }
        push({ role: "user", content: text });
        const bot = push({ role: "assistant", content: "", pending: true });
        await sendChat(text, bot);
      }
    } finally { busy = false; setBusy(false); const last = chat().messages.slice(-1)[0]; if (last && last.role !== "user") { const rows = els.thread.querySelectorAll(".msg.bot"); const row = rows[rows.length - 1]; if (row) refresh({ m: last, el: row }); } renderHistory(); }
  }

  // ------------------------------------------------ voice: mic -> WAV 16 kHz mono -> /api/voice
  const MAX_REC_MS = 60000; let rec = null;
  function encodeWav(chunks, inRate) {
    let len = 0; chunks.forEach((c) => { len += c.length; });
    const pcm = new Float32Array(len); let o = 0; chunks.forEach((c) => { pcm.set(c, o); o += c.length; });
    const outRate = 16000, ratio = inRate / outRate, n = Math.floor(pcm.length / ratio);
    const buf = new ArrayBuffer(44 + n * 2), v = new DataView(buf);
    const w = (off, s) => { for (let i = 0; i < s.length; i++) v.setUint8(off + i, s.charCodeAt(i)); };
    w(0, "RIFF"); v.setUint32(4, 36 + n * 2, true); w(8, "WAVE"); w(12, "fmt "); v.setUint32(16, 16, true); v.setUint16(20, 1, true); v.setUint16(22, 1, true);
    v.setUint32(24, outRate, true); v.setUint32(28, outRate * 2, true); v.setUint16(32, 2, true); v.setUint16(34, 16, true); w(36, "data"); v.setUint32(40, n * 2, true);
    for (let i = 0; i < n; i++) {
      const s0 = Math.floor(i * ratio), s1 = Math.min(pcm.length, Math.floor((i + 1) * ratio)); let sum = 0, cnt = 0;
      for (let j = s0; j < s1; j++) { sum += pcm[j]; cnt++; }
      const x = Math.max(-1, Math.min(1, cnt ? sum / cnt : 0)); v.setInt16(44 + i * 2, x < 0 ? x * 0x8000 : x * 0x7fff, true);
    }
    return new Blob([buf], { type: "audio/wav" });
  }
  async function startRec() {
    if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) { toast(t("noMic")); return; }
    let stream;
    try { stream = await navigator.mediaDevices.getUserMedia({ audio: { channelCount: 1, echoCancellation: true, noiseSuppression: true } }); }
    catch (e) { toast(e && e.name === "NotFoundError" ? t("noMic") : t("micDenied")); return; }
    const Ctx = window.AudioContext || window.webkitAudioContext; const ctx = new Ctx();
    const src = ctx.createMediaStreamSource(stream); const proc = ctx.createScriptProcessor(4096, 1, 1); const chunks = [];
    proc.onaudioprocess = (e) => chunks.push(new Float32Array(e.inputBuffer.getChannelData(0)));
    src.connect(proc); proc.connect(ctx.destination);
    const started = Date.now(); rec = { stream, ctx, src, proc, chunks, started };
    els.mic.classList.add("recording");
    const tick = () => { if (rec) els.recStatus.textContent = `🔴 ${Math.round((Date.now() - started) / 1000)}s · ${t("rec")}`; };
    tick(); rec.timer = setInterval(() => { tick(); if (Date.now() - started >= MAX_REC_MS) stopRec(); }, 500);
  }
  async function stopRec() {
    const r = rec; if (!r) return; rec = null;
    clearInterval(r.timer); els.mic.classList.remove("recording"); els.recStatus.textContent = "";
    try { r.proc.disconnect(); r.src.disconnect(); } catch {}
    r.stream.getTracks().forEach((tr) => tr.stop());
    const rate = r.ctx.sampleRate; r.ctx.close().catch(() => {});
    if (Date.now() - r.started < 700) { toast(t("tooShort")); return; }
    await sendVoice(encodeWav(r.chunks, rate));
  }
  async function sendVoice(blob) {
    if (busy) return; if (!navigator.onLine) { toast(t("offline")); return; }
    busy = true; setBusy(true); refreshPrevActions();
    const user = push({ role: "user", content: "🎤 …" });
    let bot = push({ role: "assistant", content: "", pending: true, progress: t("voiceWait") });
    try {
      const fd = new FormData(); fd.append("file", blob, "voice.wav"); fd.append("mode", "auto"); fd.append("session_id", sid + ":" + current);
      fd.append("history", JSON.stringify(historyPayload(chat().messages.length - 2)));
      const res = await api("/api/voice", { method: "POST", body: fd });
      if (!res.ok) throw new Error(await errText(res));
      const j = await res.json();
      user.m.content = "🎤 " + (j.transcript || "…"); refresh(user);
      const c = chat(); if (!c.renamed && (!c.title || c.title === "…")) { c.title = autoTitle(user.m); renderHistory(); }
      if (j.action) await mediaAction(j.action, j.prompt, bot);
      else {
        Object.assign(bot.m, { content: j.reply || t("netErr"), pending: false, progress: "", regen: null });
        if (j.audio) { bot.m.aid = "a" + uid(); audioCache.set(bot.m.aid, j.audio); bot.m.autoplay = true; }
        refresh(bot); bot.m.autoplay = false;
      }
    } catch (e) {
      if (user.m.content === "🎤 …") { user.m.content = "🎤"; refresh(user); }
      Object.assign(bot.m, { pending: false, error: true, content: e.message || t("netErr"), progress: "" }); refresh(bot);
    } finally { busy = false; setBusy(false); save(); }
  }
  async function speak(m, body, btn) {
    btn.disabled = true; const old = btn.innerHTML; btn.innerHTML = `⏳ <span>${esc(t("ttsWait"))}</span>`;
    try {
      const res = await api("/api/tts", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ text: m.content.slice(0, 6000) }) });
      if (!res.ok) throw new Error(await errText(res));
      const j = await res.json(); m.aid = m.aid || "a" + uid(); audioCache.set(m.aid, j.audio);
      addAudio(body, j.audio, true); btn.remove();
    } catch (e) { toast(e.message || t("netErr")); btn.disabled = false; btn.innerHTML = old; }
  }
  els.mic.onclick = () => { if (rec) stopRec(); else if (!busy) startRec(); };

  // ------------------------------------------------ photo attach
  function shrink(file) {
    return new Promise((resolve) => {
      const img = new Image(); const r = new FileReader();
      r.onload = () => { img.src = r.result; };
      img.onload = () => {
        const s = Math.min(1, 1280 / Math.max(img.width, img.height));
        const cv = document.createElement("canvas"); cv.width = Math.round(img.width * s); cv.height = Math.round(img.height * s);
        cv.getContext("2d").drawImage(img, 0, 0, cv.width, cv.height);
        const tc = document.createElement("canvas"); const ts = Math.min(1, 360 / Math.max(img.width, img.height));
        tc.width = Math.round(img.width * ts); tc.height = Math.round(img.height * ts); tc.getContext("2d").drawImage(img, 0, 0, tc.width, tc.height);
        cv.toBlob((blob) => resolve({ file: new File([blob], "photo.jpg", { type: "image/jpeg" }), preview: tc.toDataURL("image/jpeg", 0.7) }), "image/jpeg", 0.88);
      };
      img.onerror = () => resolve({ file, preview: "" });
      r.readAsDataURL(file);
    });
  }
  els.photoInput.onchange = async () => {
    const f = els.photoInput.files[0]; els.photoInput.value = ""; if (!f) return;
    if (!/^image\//.test(f.type) || /\.(pdf|docx?|xlsx?|csv|txt|md|json|html?)$/i.test(f.name)) return attachDoc(f);
    pendingPhoto = await shrink(f); els.photoThumb.src = pendingPhoto.preview; els.photoPreview.hidden = false;
    els.input.placeholder = t("photoQ"); els.input.focus();
  };
  function clearPhoto() { pendingPhoto = null; els.photoPreview.hidden = true; els.input.placeholder = t("placeholder"); }
  $("#removePhoto").onclick = clearPhoto;

  // ------------------------------------------------ downloads
  // iPhone/iPad (Safari and home-screen PWA) ignore <a download>: share the file so "Save Image" appears,
  // or show it full screen for a long-press save. Android WebView hands the file to the app (Download/Nexora).
  // Desktop / Android browsers get a real file download through a blob: URL (works for cross-origin images).
  async function toBlob(href) {
    if (href.startsWith("data:") || href.startsWith("blob:") || href.startsWith(location.origin)) {
      const r = await fetch(href); if (!r.ok) throw new Error("fetch " + r.status); return r.blob();
    }
    try { const r = await fetch(href, { mode: "cors", referrerPolicy: "no-referrer" }); if (r.ok) return await r.blob(); } catch (_) { }
    const r = await api("/api/fetch-media?url=" + encodeURIComponent(href)); // same-origin proxy for CORS-less hosts
    if (!r.ok) throw new Error("proxy " + r.status); return r.blob();
  }
  function prepFile(href, name) {
    if (!fileCache.has(href)) {
      const pr = toBlob(href).then((b) => {
        let n = name || "nexora";
        const ext = (b.type.split("/")[1] || "").replace("jpeg", "jpg").replace(/\W.*$/, "");
        if (ext && !n.toLowerCase().endsWith("." + ext)) n = n.replace(/\.\w+$/, "") + "." + ext;
        return new File([b], n, { type: b.type || "image/png" });
      });
      pr.catch(() => fileCache.delete(href));
      fileCache.set(href, pr);
    }
    return fileCache.get(href);
  }
  function showViewer(src, isVideo) {
    let v = document.getElementById("viewer");
    if (!v) {
      v = document.createElement("div"); v.id = "viewer";
      v.innerHTML = `<button type="button" class="v-close" aria-label="close">✕</button><div class="v-body"></div><p class="v-hint"></p>`;
      document.body.appendChild(v);
      v.querySelector(".v-close").onclick = () => { v.hidden = true; v.querySelector(".v-body").innerHTML = ""; };
    }
    v.querySelector(".v-body").innerHTML = isVideo ? `<video src="${esc(src)}" controls playsinline></video>` : `<img src="${esc(src)}" alt="">`;
    v.querySelector(".v-hint").textContent = t(isVideo ? "saveHintVideo" : "saveHint");
    v.hidden = false;
  }
  async function saveMedia(href, name) {
    let file;
    try { file = await prepFile(href, name); } catch (e) { toast(t("saveFail")); return; }
    return saveFileObj(file);
  }
  async function saveFileObj(file) {
    if (window.NexoraAndroid && NexoraAndroid.saveFile) { NexoraAndroid.saveFile(await blobToDataURL(file), file.name); return; }
    if (IS_IOS) {
      if (navigator.canShare && navigator.canShare({ files: [file] })) {
        try { await navigator.share({ files: [file] }); return; }
        catch (e) { if (e && e.name === "AbortError") return; } // user closed the sheet
      }
      if (!/^(image|video)\//.test(file.type)) { const u = URL.createObjectURL(file); window.open(u, "_blank"); return; }
      showViewer(URL.createObjectURL(file), file.type.startsWith("video")); return;
    }
    const u = URL.createObjectURL(file); const a = document.createElement("a");
    a.href = u; a.download = file.name; document.body.appendChild(a); a.click(); a.remove();
    setTimeout(() => URL.revokeObjectURL(u), 60000);
  }
  document.addEventListener("click", (e) => {
    const a = e.target.closest && e.target.closest("a[download]");
    if (!a || a.href.startsWith("blob:") && !IS_IOS && !window.NexoraAndroid) return;
    e.preventDefault(); saveMedia(a.href, a.getAttribute("download") || "nexora");
  }, true);

  // ------------------------------------------------ lead form
  $("#leadBtn").onclick = () => { closeSide(); els.leadDialog.showModal ? els.leadDialog.showModal() : els.leadDialog.setAttribute("open", ""); };
  $("#leadCancel").onclick = () => els.leadDialog.close();
  els.leadForm.onsubmit = async (e) => {
    e.preventDefault();
    const data = Object.fromEntries(new FormData(els.leadForm).entries()); data.session_id = sid;
    const btn = $("#leadSubmit"); btn.disabled = true;
    try {
      const res = await api("/api/lead", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(data) });
      if (!res.ok) throw new Error(await errText(res));
      els.leadDialog.close(); els.leadForm.reset();
      push({ role: "assistant", content: "✅ " + t("leadThanks") + "\n\n[Upwork — Md Zahngir Hossain](https://www.upwork.com/freelancers/mdzahngirhossain2)" });
    } catch (err) { toast(err.message || t("netErr")); }
    btn.disabled = false;
  };

  // ------------------------------------------------ agent: tool steps, files, documents, Telegram link, owner vault
  function stepsHtml(m, live) {
    if (!m.steps || !m.steps.length) return "";
    const items = m.steps.map((s, i) => `<li class="${live && i === m.steps.length - 1 ? "live" : "ok"}">${esc(s)}</li>`).join("");
    return live ? `<ul class="steps">${items}</ul>` : `<details class="steps-done"><summary>⚙️ ${m.steps.length} ${esc(t("stepsDone"))}</summary><ul class="steps">${items}</ul></details>`;
  }
  const FILE_ICON = { pdf: "📕", docx: "📘", xlsx: "📗", csv: "📊", txt: "📄", md: "📄" };
  function fileFromItem(f) {
    const bin = atob(f.data); const u8 = new Uint8Array(bin.length); for (let i = 0; i < bin.length; i++) u8[i] = bin.charCodeAt(i);
    return new File([u8], f.name, { type: f.mime || "application/octet-stream" });
  }
  function filesEl(m) {
    const wrap = document.createElement("div"); wrap.className = "files";
    m.files.forEach((f) => {
      const ext = (f.name.split(".").pop() || "").toLowerCase();
      const card = document.createElement("button"); card.type = "button"; card.className = "file-card";
      const kb = f.size ? (f.size > 1048576 ? (f.size / 1048576).toFixed(1) + " MB" : Math.max(1, Math.round(f.size / 1024)) + " KB") : "";
      card.innerHTML = `<span class="fi">${FILE_ICON[ext] || "📎"}</span><span class="fn"><b>${esc(f.name)}</b><small>${esc(ext.toUpperCase())}${kb ? " · " + kb : ""}${f.data ? "" : " · " + esc(t("fileGone"))}</small></span>${ICON.down}`;
      card.onclick = () => { if (!f.data) { toast(t("fileGone")); return; } saveFileObj(fileFromItem(f)); };
      wrap.appendChild(card);
    });
    return wrap;
  }
  // Keep generated files in saved chats only while they are small (localStorage is ~5 MB).
  const _save0 = save;
  save = function () {
    let total = 0;
    Object.values(chats).sort((a, b) => b.updated - a.updated).forEach((c) => c.messages.forEach((m) => (m.files || []).forEach((f) => {
      if (!f.data) return; total += f.data.length; if (total > 1500000) f.data = "";
    })));
    Object.values(chats).forEach((c) => c.messages.forEach((m) => (m.docs || []).forEach((d) => { if (d.text && d.text.length > 20000) d.text = d.text.slice(0, 20000); })));
    _save0();
  };

  let pendingDocs = [], docBusy = false;
  const docChips = document.createElement("div"); docChips.className = "doc-chips"; docChips.hidden = true;
  els.photoPreview.parentNode.insertBefore(docChips, els.photoPreview.nextSibling);
  function renderDocChips() {
    docChips.innerHTML = ""; docChips.hidden = !pendingDocs.length && !docBusy;
    pendingDocs.forEach((d, i) => {
      const c = document.createElement("span"); c.className = "doc-chip";
      c.innerHTML = `📄 ${esc(d.name)} <small>${Math.round(d.chars / 1000)}k</small> <button type="button" aria-label="remove">✕</button>`;
      c.querySelector("button").onclick = () => { pendingDocs.splice(i, 1); renderDocChips(); };
      docChips.appendChild(c);
    });
    if (docBusy) docChips.insertAdjacentHTML("beforeend", `<span class="doc-chip busy">⏳ ${esc(t("docReading"))}</span>`);
  }
  function clearDocs() { pendingDocs = []; renderDocChips(); }
  async function attachDoc(f) {
    if (f.size > 4000000) { toast(t("docBig")); return; }
    if (pendingDocs.length >= 3) { toast(t("docMax")); return; }
    docBusy = true; renderDocChips();
    try {
      const fd = new FormData(); fd.append("file", f, f.name);
      const r = await api("/api/files/extract", { method: "POST", body: fd });
      if (!r.ok) throw new Error(await errText(r));
      const j = await r.json(); pendingDocs.push({ name: j.name, chars: j.chars, text: j.text });
      els.input.placeholder = t("docQ"); els.input.focus();
    } catch (e) { toast(e.message || t("netErr")); }
    docBusy = false; renderDocChips();
  }
  els.photoInput.setAttribute("accept", "image/*,.pdf,.docx,.xlsx,.xls,.csv,.txt,.md,.json,.html,application/pdf");

  // --- Telegram link (reminders from the web are delivered by the Nexora Telegram bot)
  const BOT_URL = "https://t.me/SocialGrowthLabAI_bot";
  function sheet(html) {
    let d = document.getElementById("agentSheet");
    if (!d) { d = document.createElement("dialog"); d.id = "agentSheet"; d.className = "sheet"; document.body.appendChild(d); }
    d.innerHTML = html; if (!d.open) (d.showModal ? d.showModal() : d.setAttribute("open", ""));
    d.querySelectorAll("[data-close]").forEach((b) => { b.onclick = () => d.close(); });
    return d;
  }
  function openLink() {
    closeSide();
    const linked = !!localStorage.getItem(LS_TG);
    const d = sheet(`<h2>📲 ${esc(t("tgTitle"))}</h2><p class="muted">${esc(t("tgSub"))}</p>
      ${linked ? `<p class="ok-line">✅ ${esc(t("tgIsLinked"))}</p>` : ""}
      <ol class="mini-steps"><li><a href="${BOT_URL}?start=link" target="_blank" rel="noopener">${esc(t("tgStep1"))}</a></li><li>${esc(t("tgStep2"))}</li></ol>
      <label>${esc(t("tgCode"))}<input id="tgCode" placeholder="ABCD1234-XXXXXXXX" autocomplete="off" /></label>
      <div class="sheet-actions">${linked ? `<button type="button" class="ghost-btn" id="tgUnlink">${esc(t("tgUnlink"))}</button>` : ""}
      <button type="button" class="ghost-btn" data-close>${esc(t("cancel"))}</button><button type="button" class="primary-btn" id="tgSave">${esc(t("tgLink"))}</button></div>`);
    if (linked) d.querySelector("#tgUnlink").onclick = () => { localStorage.removeItem(LS_TG); d.close(); toast("✓"); };
    d.querySelector("#tgSave").onclick = async () => {
      try {
        const r = await api("/api/link", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ code: d.querySelector("#tgCode").value.trim() }) });
        if (!r.ok) throw new Error(await errText(r));
        localStorage.setItem(LS_TG, (await r.json()).token); d.close(); toast(t("tgLinked"));
      } catch (e) { toast(e.message); }
    };
  }

  // --- Owner vault (hidden from regular users; open with #vault or by typing /vault)
  async function vaultCall(path, body) {
    const r = await api(path, body === undefined ? {} : { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
    if (r.status === 401) { localStorage.removeItem(LS_OWNER); throw new Error(t("vLocked")); }
    if (!r.ok) throw new Error(await errText(r));
    return r.json();
  }
  async function openVault(view) {
    closeSide();
    let st = { has_pin: true, unlocked: false, enabled: true };
    try { st = await vaultCall("/api/vault/status"); } catch (e) { toast(e.message); }
    if (!st.enabled) { toast(t("vOff")); return; }
    if (st.unlocked && view !== "setup") return vaultUnlocked();
    if (!st.has_pin || view === "setup") {
      const d = sheet(`<h2>🔐 ${esc(t("vSetupTitle"))}</h2><p class="muted">${esc(t("vSetupSub"))}</p>
        <button type="button" class="ghost-btn wide" id="vSend">📨 ${esc(t("vSendCode"))}</button>
        <label>${esc(t("vCode"))}<input id="vCode" inputmode="numeric" maxlength="6" autocomplete="one-time-code" /></label>
        <label>${esc(t("vNewPin"))}<input id="vPin" type="password" minlength="6" maxlength="64" autocomplete="new-password" /></label>
        <label>${esc(t("vPin2"))}<input id="vPin2" type="password" maxlength="64" autocomplete="new-password" /></label>
        <div class="sheet-actions"><button type="button" class="ghost-btn" data-close>${esc(t("cancel"))}</button><button type="button" class="primary-btn" id="vSet">${esc(t("vSave"))}</button></div>`);
      d.querySelector("#vSend").onclick = async (e) => { e.target.disabled = true; try { await vaultCall("/api/vault/setup-code", {}); toast(t("vCodeSent")); } catch (er) { toast(er.message); e.target.disabled = false; } };
      d.querySelector("#vSet").onclick = async () => {
        const pin = d.querySelector("#vPin").value; if (pin !== d.querySelector("#vPin2").value) { toast(t("vMismatch")); return; }
        try { const j = await vaultCall("/api/vault/pin", { code: d.querySelector("#vCode").value.trim(), pin }); localStorage.setItem(LS_OWNER, j.token); $("#vaultBtn").hidden = false; vaultUnlocked(); }
        catch (er) { toast(er.message); }
      };
      return;
    }
    const d = sheet(`<h2>🔐 ${esc(t("vTitle"))}</h2><p class="muted">${esc(t("vUnlockSub"))}</p>
      <label>PIN<input id="vPin" type="password" maxlength="64" autocomplete="current-password" /></label>
      <p class="mini"><a href="#" id="vForgot">${esc(t("vForgot"))}</a></p>
      <div class="sheet-actions"><button type="button" class="ghost-btn" data-close>${esc(t("cancel"))}</button><button type="button" class="primary-btn" id="vUnlock">${esc(t("vUnlock"))}</button></div>`);
    d.querySelector("#vForgot").onclick = (e) => { e.preventDefault(); openVault("setup"); };
    const go = async () => { try { const j = await vaultCall("/api/vault/unlock", { pin: d.querySelector("#vPin").value }); localStorage.setItem(LS_OWNER, j.token); $("#vaultBtn").hidden = false; vaultUnlocked(); } catch (er) { toast(er.message); } };
    d.querySelector("#vUnlock").onclick = go; d.querySelector("#vPin").onkeydown = (e) => { if (e.key === "Enter") { e.preventDefault(); go(); } };
  }
  async function vaultUnlocked(entries) {
    if (!entries) { try { entries = (await vaultCall("/api/vault/list")).entries; } catch (e) { toast(e.message); return openVault(); } }
    const rows = entries.length ? entries.map((e) => `<li><span><b>${esc(e.name)}</b><small>${esc(e.note || "")} · ${esc(e.updated)}</small></span><span class="vv">••••••</span><button type="button" data-del="${esc(e.name)}" title="delete">${ICON.trash}</button></li>`).join("") : `<li class="muted">${esc(t("vEmpty"))}</li>`;
    const d = sheet(`<h2>🔐 ${esc(t("vTitle"))}</h2><p class="muted">${esc(t("vInfo"))}</p><ul class="vault-list">${rows}</ul>
      <details class="vault-add"><summary>➕ ${esc(t("vAdd"))}</summary>
      <label>${esc(t("vName"))}<input id="vName" placeholder="OPENAI_KEY / IG_LOGIN" maxlength="48" autocomplete="off" /></label>
      <label>${esc(t("vValue"))}<input id="vValue" type="password" maxlength="8000" autocomplete="off" /></label>
      <label>${esc(t("vNote"))}<input id="vNote" maxlength="300" autocomplete="off" /></label>
      <button type="button" class="primary-btn" id="vAddBtn">${esc(t("vSave"))}</button></details>
      <div class="sheet-actions"><button type="button" class="ghost-btn" id="vLock">🔒 ${esc(t("vLock"))}</button><button type="button" class="primary-btn" data-close>${esc(t("vDone"))}</button></div>`);
    d.querySelectorAll("[data-del]").forEach((b) => { b.onclick = async () => { if (!confirm(t("vDelQ") + " " + b.dataset.del + "?")) return; try { vaultUnlocked((await vaultCall("/api/vault/delete", { name: b.dataset.del })).entries); } catch (e) { toast(e.message); } }; });
    d.querySelector("#vAddBtn").onclick = async () => {
      try { vaultUnlocked((await vaultCall("/api/vault/set", { name: d.querySelector("#vName").value.trim(), value: d.querySelector("#vValue").value, note: d.querySelector("#vNote").value })).entries); toast("✓"); }
      catch (e) { toast(e.message); }
    };
    d.querySelector("#vLock").onclick = () => { localStorage.removeItem(LS_OWNER); d.close(); toast("🔒"); };
  }
  const sideFoot = document.querySelector(".side-foot");
  sideFoot.insertAdjacentHTML("afterbegin", `<button class="side-link" id="tgBtn">📲 <span data-i18n="tgBtn">${esc(t("tgBtn"))}</span></button><button class="side-link" id="vaultBtn" hidden>🔐 <span data-i18n="vTitle">${esc(t("vTitle"))}</span></button>`);
  $("#tgBtn").onclick = openLink; $("#vaultBtn").onclick = () => openVault();
  if (ownerToken()) $("#vaultBtn").hidden = false;
  if (/^#vault/.test(location.hash)) { history.replaceState(null, "", location.pathname); setTimeout(() => openVault(), 300); }
  if (/^#link/.test(location.hash)) { history.replaceState(null, "", location.pathname); setTimeout(openLink, 300); }

  // ------------------------------------------------ wiring
  function autosize() { els.input.style.height = "auto"; els.input.style.height = Math.min(els.input.scrollHeight, 200) + "px"; }
  els.input.addEventListener("input", autosize);
  els.input.addEventListener("keydown", (e) => { if (e.key === "Enter" && !e.shiftKey && !e.isComposing && matchMedia("(pointer:fine)").matches) { e.preventDefault(); submit(); } });
  els.form.onsubmit = (e) => { e.preventDefault(); submit(); };
  $("#openSide").onclick = openSide; $("#closeSide").onclick = closeSide; $("#scrim").onclick = closeSide;
  $("#newChat").onclick = newChat; $("#newChatTop").onclick = newChat;
  els.search.addEventListener("input", () => { query = els.search.value; renderHistory(); });
  $("#langBtn").onclick = () => { lang = lang === "bn" ? "en" : "bn"; localStorage.setItem(LS_LANG, lang); applyI18n(); };
  $("#themeBtn").onclick = () => setTheme(document.documentElement.dataset.theme === "light" ? "dark" : "light");
  $("#clearAll").onclick = () => { if (confirm(t("confirmClear"))) { chats = {}; current = null; save(); newChat(); } };
  window.addEventListener("beforeinstallprompt", (e) => { e.preventDefault(); deferredInstall = e; $("#installBtn").hidden = false; });
  $("#installBtn").onclick = async () => { if (!deferredInstall) return; deferredInstall.prompt(); await deferredInstall.userChoice; deferredInstall = null; $("#installBtn").hidden = true; };
  if ("serviceWorker" in navigator && (location.protocol === "https:" || location.hostname === "localhost" || location.hostname === "127.0.0.1")) {
    navigator.serviceWorker.register("/sw.js", { updateViaCache: "none" }).then((reg) => {
      document.addEventListener("visibilitychange", () => { if (document.visibilityState === "visible") reg.update().catch(() => {}); });
    }).catch(() => {});
  }
  // A phone can keep this page in memory for days: when it comes back, reload if a newer version is live.
  async function checkVersion() {
    if (busy || rec) return;
    try {
      const r = await fetch(API + "/api/health", { cache: "no-store" }); const j = await r.json();
      if (j.app_version && Number(j.app_version) > Number(CLIENT_VERSION)) location.reload();
    } catch {}
  }
  document.addEventListener("visibilitychange", () => { if (document.visibilityState === "visible") checkVersion(); });
  window.addEventListener("pageshow", (e) => { if (e.persisted) checkVersion(); });
  if (/[?&]v=\d/.test(location.search)) history.replaceState(null, "", location.pathname);
  if (window.NexoraAndroid && /NexoraApp/.test(navigator.userAgent)) { $("#serverBtn").hidden = false; $("#serverBtn").onclick = () => window.NexoraAndroid.openSetup(); }

  // init
  chat(); applyI18n(); renderThread(); save();
})();
