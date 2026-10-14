const t = (message, values) => globalThis.TVGuideI18n?.t(message, values) || message;
const grid = document.getElementById("grid");
const guideHeader = document.querySelector(".guide-header");
function updateScrollEndSpace() {
  const cards = Array.from(grid.querySelectorAll(".channel-card"));
  let space = 0;
  if (cards.length) {
    const lastTop = cards[cards.length - 1].offsetTop;
    if (lastTop > cards[0].offsetTop) {
      const lastRowHeight = Math.max(...cards.filter(card => Math.abs(card.offsetTop - lastTop) < 1)
        .map(card => card.getBoundingClientRect().height));
      const bottomPadding = parseFloat(getComputedStyle(grid.parentElement).paddingBottom) || 0;
      space = Math.max(0, window.innerHeight - guideHeader.offsetHeight - lastRowHeight - bottomPadding);
    }
  }
  grid.style.paddingBottom = space + "px";
}
new ResizeObserver(updateScrollEndSpace).observe(grid);
window.addEventListener("resize", updateScrollEndSpace);
function updateScrollHeaderHeight() {
  document.documentElement.style.setProperty("--guide-header-height", guideHeader.offsetHeight + "px");
  updateScrollEndSpace();
}
new ResizeObserver(updateScrollHeaderHeight).observe(guideHeader);
updateScrollHeaderHeight();
let lastRowScroll = -Infinity;
window.addEventListener("wheel", event => {
  if (event.ctrlKey || event.shiftKey || !event.deltaY ||
      Math.abs(event.deltaX) > Math.abs(event.deltaY) || document.querySelector("dialog[open]")) return;
  const cards = Array.from(grid.querySelectorAll(".channel-card"));
  if (!cards.length) return;
  const headerHeight = guideHeader.offsetHeight;
  // Tall rows must remain freely scrollable so every programme is reachable.
  if (cards.some(card => card.offsetHeight > window.innerHeight - headerHeight)) return;
  const rows = [...new Set(cards.map(card => Math.round(card.getBoundingClientRect().top + window.scrollY)))];
  const stops = rows.map((top, index) => index === 0 ? 0 : Math.max(0, top - headerHeight));
  const target = event.deltaY > 0
    ? stops.find(top => top > window.scrollY + 2)
    : stops.reverse().find(top => top < window.scrollY - 2);
  if (target === undefined) return;
  event.preventDefault();
  const now = performance.now();
  if (now - lastRowScroll < 300) return;
  lastRowScroll = now;
  window.scrollTo({top:target, behavior:"instant"});
}, {passive:false});
const detail = document.getElementById("detail");
const detailBody = document.getElementById("detailBody");
const bookmarkProgram = document.getElementById("bookmarkProgram");
const bookmarkCount = document.getElementById("bookmarkCount");
const showBookmarks = document.getElementById("showBookmarks");
const bookmarksDialog = document.getElementById("bookmarksDialog");
const bookmarksBody = document.getElementById("bookmarksBody");
const testNotification = document.getElementById("testNotification");
const testNotificationStatus = document.getElementById("testNotificationStatus");
const customTimeDialog = document.getElementById("customTimeDialog");
const customDate = document.getElementById("customDate");
const customTime = document.getElementById("customTime");
const applyCustomTime = document.getElementById("applyCustomTime");
const cancelCustomTime = document.getElementById("cancelCustomTime");
const customTimeClose = document.querySelector(".custom-time-close");
const reminderEnabled = document.getElementById("reminderEnabled");
const reminderMinutes = document.getElementById("reminderMinutes");
const reminderStatus = document.getElementById("reminderStatus");
const showChannelSettings = document.getElementById("showChannelSettings");
const channelSettingsDialog = document.getElementById("channelSettingsDialog");
const channelPicker = new TVGuideChannelPicker(channelSettingsDialog);
const saveChannelSettings = document.getElementById("saveChannelSettings");
const resetChannelSettings = document.getElementById("resetChannelSettings");
const cancelChannelSettings = document.getElementById("cancelChannelSettings");
const channelSettingsStatus = document.getElementById("channelSettingsStatus");
const showAppSettings = document.getElementById("showAppSettings");
const appSettingsDialog = document.getElementById("appSettingsDialog");
const settingLanguage = document.getElementById("settingLanguage");
const settingCountry = document.getElementById("settingCountry");
const settingDefaultView = document.getElementById("settingDefaultView");
const settingColumns = document.getElementById("settingColumns");
const settingMaxChannels = document.getElementById("settingMaxChannels");
const settingTheme = document.getElementById("settingTheme");
const settingRefresh = document.getElementById("settingRefresh");
const sensorSettings = [...document.querySelectorAll("[data-sensor-option]")];
const settingNotificationService = document.getElementById("settingNotificationService");
const saveAppSettings = document.getElementById("saveAppSettings");
const cancelAppSettings = document.getElementById("cancelAppSettings");
const appSettingsStatus = document.getElementById("appSettingsStatus");
const lovelaceCardState = document.getElementById("lovelaceCardState");
const lovelaceResourceUrl = document.getElementById("lovelaceResourceUrl");
const copyLovelaceResource = document.getElementById("copyLovelaceResource");
const openLovelaceResources = document.getElementById("openLovelaceResources");
const checkLovelaceCard = document.getElementById("checkLovelaceCard");
const lovelaceSetupStatus = document.getElementById("lovelaceSetupStatus");

const THEME_VARS = [
  "--primary-background-color",
  "--secondary-background-color",
  "--card-background-color",
  "--ha-card-background",
  "--primary-text-color",
  "--secondary-text-color",
  "--divider-color",
  "--primary-color",
  "--accent-color",
  "--lovelace-background"
];

function rgbLuminance(value) {
  const m = String(value || "").match(/rgba?\((\d+)\D+(\d+)\D+(\d+)/i);
  if (!m) return null;
  const [r,g,b] = [Number(m[1]), Number(m[2]), Number(m[3])].map(v => v / 255);
  const linear = c => c <= 0.03928 ? c / 12.92 : Math.pow((c + 0.055) / 1.055, 2.4);
  return 0.2126 * linear(r) + 0.7152 * linear(g) + 0.0722 * linear(b);
}

const dashboardParams = new URLSearchParams(window.location.search);
const inDashboardCard = dashboardParams.get("tv_guide_card") === "1";
const dashboardThemeKey = "tv-guide-dashboard-theme:" + (dashboardParams.get("tv_guide_theme") || "__dashboard__");
const dashboardDisplayModeKey = "tv-guide-dashboard-display-mode";
let dashboardThemeState = null;

function dashboardDisplayMode() {
  const configured = guide?.ui?.theme_mode;
  if (configured === "dark" || configured === "light" || configured === "auto") return configured;
  try {
    const cached = sessionStorage.getItem(dashboardDisplayModeKey);
    if (cached === "dark" || cached === "light" || cached === "auto") return cached;
  } catch {}
  return "auto";
}

function applyDashboardThemeState(state) {
  if (!state?.vars) return false;
  for (const name of THEME_VARS) {
    const value = String(state.vars[name] || "").trim();
    if (value) document.documentElement.style.setProperty(name, value);
    else document.documentElement.style.removeProperty(name);
  }
  dashboardThemeState = state;
  const displayMode = dashboardDisplayMode();
  document.documentElement.dataset.haTheme =
    displayMode === "dark" || displayMode === "light"
      ? displayMode
      : (state.darkMode ? "dark" : "light");
  document.documentElement.dataset.haThemeSource = "home-assistant";
  return true;
}

if (inDashboardCard) {
  try {
    const cached = JSON.parse(sessionStorage.getItem(dashboardThemeKey) || "null");
    applyDashboardThemeState(cached);
  } catch {}
}

window.addEventListener("message", (event) => {
  if (!inDashboardCard || event.source !== window.parent || event.origin !== window.location.origin) return;
  if (event.data?.type !== "tv-guide-theme" || !event.data.vars) return;

  const state = {
    vars:event.data.vars,
    darkMode:Boolean(event.data.darkMode)
  };
  applyDashboardThemeState(state);
  try {
    sessionStorage.setItem(dashboardThemeKey, JSON.stringify(state));
  } catch {}
  window.parent.postMessage({type:"tv-guide-theme-ready"}, window.location.origin);
});
if (inDashboardCard) {
  // Synchronize as soon as scripts are ready, without waiting for logo downloads.
  window.parent.postMessage({type:"tv-guide-theme-request"}, window.location.origin);
}

function syncHomeAssistantTheme() {
  if (inDashboardCard) {
    const configured = guide?.ui?.theme_mode || dashboardDisplayMode();
    try {
      sessionStorage.setItem(dashboardDisplayModeKey, configured);
    } catch {}
    if (dashboardThemeState) applyDashboardThemeState(dashboardThemeState);
    else {
      document.documentElement.dataset.haTheme =
        configured === "dark" || configured === "light" ? configured : "light";
      document.documentElement.dataset.haThemeSource = "home-assistant";
    }
    return true;
  }

  const configured = guide?.ui?.theme_mode || "auto";
  if (configured === "dark" || configured === "light") {
    for (const name of THEME_VARS) {
      document.documentElement.style.removeProperty(name);
    }
    document.documentElement.dataset.haTheme = configured;
    document.documentElement.dataset.haThemeSource = "forced";
    return true;
  }

  try {
    if (window.parent !== window) {
      const parentDoc = window.parent.document;
      const parentStyle = window.parent.getComputedStyle(parentDoc.documentElement);
      const frameStyle = window.frameElement
        ? window.parent.getComputedStyle(window.frameElement)
        : null;
      let copied = 0;

      for (const name of THEME_VARS) {
        const value =
          frameStyle?.getPropertyValue(name).trim() ||
          parentStyle.getPropertyValue(name).trim();
        if (value) {
          document.documentElement.style.setProperty(name, value);
          copied++;
        }
      }

      const parentBody = parentDoc.body;
      const parentHtml = parentDoc.documentElement;
      const bodyStyle = parentBody ? window.parent.getComputedStyle(parentBody) : null;
      const bg =
        frameStyle?.getPropertyValue("--primary-background-color").trim() ||
        parentStyle.getPropertyValue("--primary-background-color").trim() ||
        bodyStyle?.backgroundColor ||
        "";
      const lum = rgbLuminance(bg);

      const dark =
        parentHtml.classList.contains("dark-mode") ||
        parentBody?.classList.contains("dark-mode") ||
        frameStyle?.colorScheme.includes("dark") ||
        parentStyle.colorScheme.includes("dark") ||
        (lum !== null && lum < 0.35);

      document.documentElement.dataset.haTheme = dark ? "dark" : "light";
      document.documentElement.dataset.haThemeSource = copied > 0 ? "home-assistant" : "system";
      if (copied > 0) return true;
    }
  } catch {}

  document.documentElement.dataset.haTheme =
    window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
  document.documentElement.dataset.haThemeSource = "system";
  return false;
}

function watchHomeAssistantTheme() {
  syncHomeAssistantTheme();
  try {
    if (window.parent === window) return;
    const target = window.parent.document.documentElement;
    const observer = new MutationObserver(() => {
      syncHomeAssistantTheme();
      if (guide && globalThis.TVGuideI18n?.configure({...guide.ui,country:guide.country})) {
        render();
        renderBookmarks();
        if (activeDetail) updateDetailControls();
      }
    });
    observer.observe(target, {attributes:true, attributeFilter:["class","style","lang"]});
    if (window.parent.document.body) {
      observer.observe(window.parent.document.body, {attributes:true, attributeFilter:["class","style"]});
    }
  } catch {}
}

const fmt = TVGuideCore.fmt;
const dateFmt = TVGuideCore.dateFmt;

let guide = null;
let mode = "now";
let selectedDate = startOfDay(new Date());
let customTarget = null;
let activeDetail = null;
let bookmarks = loadBookmarksLocal();
let startupReloadTimer = null;
let lastGuideLoadedAt = 0;
const GUIDE_VISIBILITY_REFRESH_AGE = 60 * 1000;
let channelSettingsRequest = 0;
let appSettingsRequest = 0;
let channelView = "main";
let reminders = [];
let bookmarksRevision = 0, bookmarksRequest = 0;
let remindersRevision = 0, remindersRequest = 0;

function startOfDay(value) {
  return TVGuideCore.startOfDay(value);
}

function dateKey(value) {
  return TVGuideCore.dateKey(value);
}

function loadBookmarksLocal() {
  try {
    const items = JSON.parse(localStorage.getItem("tvguide-bookmarks") || "[]");
    return Array.isArray(items) ? items.filter(item => item && typeof item === "object") : [];
  }
  catch { return []; }
}

function saveBookmarksLocal() {
  try { localStorage.setItem("tvguide-bookmarks", JSON.stringify(bookmarks)); } catch {}
  bookmarkCount.textContent = String(bookmarks.length);
}

async function syncBookmark(action, item) {
  ++bookmarksRevision;
  if (action === "remove") ++remindersRevision;
  const url = new URL("api/bookmarks", window.location.href);
  const body = action === "remove"
    ? {action:"remove", id:item.id}
    : {action:"upsert", ...item};
  const res = await fetch(url, {
    method:"POST",
    headers:{"Content-Type":"application/json"},
    body:JSON.stringify(body)
  });
  const payload = await res.json();
  if (!res.ok || !payload.ok) throw new Error(t(payload.error) || t("Merkliste konnte nicht gespeichert werden."));
  ++bookmarksRevision;
  if (action === "remove") ++remindersRevision;
  bookmarks = Array.isArray(payload.bookmarks) ? payload.bookmarks : [];
  saveBookmarksLocal();
}

async function loadBookmarksRemote() {
  const request = ++bookmarksRequest;
  let revision = bookmarksRevision;
  const isCurrent = () => request === bookmarksRequest && revision === bookmarksRevision;
  const local = loadBookmarksLocal();
  let migrationDone = true;
  try { migrationDone = localStorage.getItem("tvguide-bookmarks-migrated") === "1"; } catch {}

  try {
    const url = new URL("api/bookmarks", window.location.href);
    const res = await fetch(url, {cache:"no-store"});
    if (!res.ok) throw new Error(t("Merkliste konnte nicht geladen werden."));
    const payload = await res.json();
    if (!isCurrent()) return;
    bookmarks = Array.isArray(payload.bookmarks) ? payload.bookmarks : [];

    // Import old browser-only bookmarks exactly once. Afterwards the
    // persistent add-on store is authoritative so deleted entries cannot
    // reappear from a stale browser cache.
    if (!migrationDone) {
      for (const item of local) {
        if (!isCurrent()) return;
        if (!bookmarks.some(x => x.id === item.id) && new Date(item.end) > new Date()) {
          ++revision; // Account for this import's own write, not unrelated writes.
          await syncBookmark("upsert", item);
          ++revision;
        }
      }
      if (!isCurrent()) return;
      try { localStorage.setItem("tvguide-bookmarks-migrated", "1"); } catch {}
    }
  } catch {
    // A failed refresh must not replace current entries with an earlier snapshot.
    if (!isCurrent()) return;
    if (!migrationDone) bookmarks = local;
  }

  saveBookmarksLocal();
}

function bookmarkId(channel, program) {
  return (channel.source_channel_id || channel.id) + "|" + program.start + "|" + program.title;
}

const escapeHtml = TVGuideCore.escapeHtml;

function activeChannels() {
  if (!guide?.channels?.length) return [];
  const ids = channelView === "custom"
    ? (guide.custom_channel_ids || [])
    : (guide.main_channel_ids || []);
  const byId = new Map(guide.channels.map(channel => [channel.id, channel]));
  return ids.map(id => byId.get(id)).filter(Boolean);
}

function isBookmarked(channel, program) {
  const id = bookmarkId(channel, program);
  return bookmarks.some(x => x.id === id);
}

function reminderFor(channel, program) {
  const id = bookmarkId(channel, program);
  return reminders.find(item => item.id === id) || null;
}

function updateDetailControls() {
  if (!activeDetail) return;
  const {channel, program} = activeDetail;
  const marked = isBookmarked(channel, program);
  const reminder = reminderFor(channel, program);
  const started = new Date(program.start) <= new Date();

  bookmarkProgram.textContent = marked ? t("★ Löschen") : t("☆ Merken");
  bookmarkProgram.classList.toggle("active", marked);

  reminderEnabled.checked = Boolean(reminder);
  reminderEnabled.disabled = !marked || started;
  reminderMinutes.hidden = !reminderEnabled.checked;
  reminderMinutes.disabled = started || !reminderEnabled.checked;
  reminderMinutes.value = reminder ? String(reminder.minutes) : "10";

  if (!marked) {
    reminderStatus.textContent = "";
  } else if (started) {
    reminderStatus.textContent = reminder ? t("Erinnerung ist gesetzt.") : "";
  } else if (reminder) {
    reminderStatus.textContent = t("Erinnerung {minutes} Minuten vorher.", {minutes:reminder.minutes});
  } else {
    reminderStatus.textContent = "";
  }
}

async function loadReminders() {
  const request = ++remindersRequest, revision = remindersRevision;
  try {
    const url = new URL("api/reminders", window.location.href);
    const res = await fetch(url, {cache:"no-store"});
    if (!res.ok) throw new Error(t("Erinnerungen konnten nicht geladen werden."));
    const payload = await res.json();
    if (request !== remindersRequest || revision !== remindersRevision) return;
    reminders = Array.isArray(payload.reminders) ? payload.reminders : [];
  } catch {
    // Keep the last known reminders while the add-on is temporarily unreachable.
  }
}

async function saveReminderForActiveDetail(enabled, minutes) {
  if (!activeDetail) return;
  ++remindersRevision;
  const {channel, program} = activeDetail;
  const id = bookmarkId(channel, program);

  const url = new URL("api/reminders", window.location.href);
  const body = enabled
    ? {
        action:"upsert",
        id,
        channel:channel.name,
        channelId:channel.id,
        title:program.title,
        start:program.start,
        end:program.end,
        minutes,
        language:globalThis.TVGuideI18n?.language || "de"
      }
    : {action:"remove", id};

  const res = await fetch(url, {
    method:"POST",
    headers:{"Content-Type":"application/json"},
    body:JSON.stringify(body)
  });
  const payload = await res.json();
  if (!res.ok || !payload.ok) {
    throw new Error(t(payload.error) || t("Erinnerung konnte nicht gespeichert werden."));
  }
  ++remindersRevision;
  reminders = Array.isArray(payload.reminders) ? payload.reminders : [];
}

function showDetail(channel, program) {
  activeDetail = {channel, program};
  const subtitle = program.subtitle ? '<p class="detail-subtitle">' + escapeHtml(program.subtitle) + '</p>' : "";
  const category = program.category ? '<p><strong>Genre:</strong> ' + escapeHtml(program.category) + '</p>' : "";
  const description = program.desc ? '<p>' + escapeHtml(program.desc) + '</p>' : ("<p>" + escapeHtml(t("Keine Beschreibung verfügbar.")) + "</p>");

  detailBody.innerHTML =
    '<div class="detail-channel">' + escapeHtml(channel.name) + '</div>' +
    '<h2>' + escapeHtml(program.title) + '</h2>' +
    '<p class="detail-time">' + dateFmt.format(new Date(program.start)) + ' · ' +
      fmt.format(new Date(program.start)) + '–' + fmt.format(new Date(program.end)) + '</p>' +
    subtitle + category + description;
  updateDetailControls();
  detail.showModal();
}

async function toggleBookmark() {
  if (!activeDetail) return;
  const {channel, program} = activeDetail;
  const id = bookmarkId(channel, program);
  const index = bookmarks.findIndex(x => x.id === id);

  bookmarkProgram.disabled = true;

  try {
    if (index >= 0) {
      const item = bookmarks[index];
      await syncBookmark("remove", item);
      reminders = reminders.filter(item => item.id !== id);
      updateDetailControls();
      return;
    }

    const item = {
      id,
      channel:channel.name,
      channelId:channel.id,
      title:program.title,
      start:program.start,
      end:program.end
    };
    await syncBookmark("upsert", item);
    updateDetailControls();
  } catch (err) {
    updateDetailControls();
    reminderStatus.textContent = t(err.message) || t("Merkliste konnte nicht gespeichert werden.");
  } finally {
    bookmarkProgram.disabled = false;
  }
}

function renderBookmarks() {
  document.querySelector("#bookmarksStatus").textContent = "";
  const now = new Date();
  bookmarks = bookmarks.filter(x => new Date(x.end) > now);
  saveBookmarksLocal();
  if (!bookmarks.length) {
    bookmarksBody.innerHTML = ("<p class=\"empty-bookmarks\">" + escapeHtml(t("Noch keine Sendung gemerkt.")) + "</p>");
    return;
  }
  bookmarksBody.innerHTML = bookmarks.map(item => {
    const reminder = reminders.find(r => r.id === item.id);
    const reminderText = reminder ? ' · ⏰ ' + escapeHtml(t('{minutes} Min.', {minutes:reminder.minutes})) : '';
    return '<div class="bookmark-row"><div><strong>' + escapeHtml(item.title) + '</strong>' +
      '<div>' + escapeHtml(item.channel) + ' · ' + dateFmt.format(new Date(item.start)) +
      ' · ' + fmt.format(new Date(item.start)) + reminderText + '</div></div>' +
      '<button type="button" data-remove="' + escapeHtml(item.id) + ("\">" + escapeHtml(t("×")) + "</button></div>");
  }).join("");
  bookmarksBody.querySelectorAll("[data-remove]").forEach(btn => {
    btn.addEventListener("click", async () => {
      const id = btn.dataset.remove;
      const item = bookmarks.find(x => x.id === id) || {id};
      btn.disabled = true;
      try {
        await syncBookmark("remove", item);
        reminders = reminders.filter(item => item.id !== id);
        renderBookmarks();
      } catch (err) {
        document.querySelector("#bookmarksStatus").textContent = t(err.message) || t("Sendung konnte nicht gelöscht werden.");
        btn.disabled = false;
      }
    });
  });
}

async function testConfiguredNotification() {
  testNotification.disabled = true;
  testNotificationStatus.textContent = t("Wird gesendet …");
  try {
    const url = new URL("api/test-notification", window.location.href);
    const res = await fetch(url, {
      method:"POST",
      headers:{"Content-Type":"application/json"},
      body:JSON.stringify({test:true, language:globalThis.TVGuideI18n?.language || "de"})
    });
    const payload = await res.json();
    if (!res.ok || !payload.ok) throw new Error(t(payload.error) || t("Testbenachrichtigung konnte nicht gesendet werden."));
    testNotificationStatus.textContent = t("Gesendet über {service}", {service:payload.service});
  } catch (err) {
    testNotificationStatus.textContent = t(err.message);
  } finally {
    testNotification.disabled = false;
  }
}

function lovelaceCardRegistered() {
  const hosts = [window, window.parent, window.top];
  for (const host of hosts) {
    try {
      if (host?.customElements?.get("tv-guide-card")) return true;
      if (Array.isArray(host?.customCards) &&
          host.customCards.some(card => card?.type === "tv-guide-card")) return true;
    } catch {}
  }
  return false;
}

function getHomeAssistantConnection() {
  const docs = [];
  try { docs.push(window.document); } catch {}
  try { if (window.parent?.document) docs.push(window.parent.document); } catch {}
  try { if (window.top?.document) docs.push(window.top.document); } catch {}

  for (const doc of docs) {
    try {
      const root = doc.querySelector("home-assistant");
      const connection = root?.hass?.connection;
      if (connection?.sendMessagePromise) return connection;
    } catch {}
  }
  return null;
}

async function lovelaceResourceRegistered() {
  const connection = getHomeAssistantConnection();
  if (!connection) return null;

  try {
    const resources = await connection.sendMessagePromise({type:"lovelace/resources"});
    if (!Array.isArray(resources)) return false;
    return resources.some(resource => {
      const url = String(resource?.url || "").split("?")[0];
      return url === "/local/tv-guide-card-loader.js";
    });
  } catch {
    return null;
  }
}

async function checkLovelaceSetup() {
  lovelaceCardState.textContent = t("Wird geprüft …");
  lovelaceCardState.className = "lovelace-state";
  lovelaceSetupStatus.textContent = "";

  let assetReady = false;
  try {
    const res = await fetch("/local/tv-guide-card-loader.js?t=" + Date.now(), {
      method:"GET",
      cache:"no-store"
    });
    assetReady = res.ok;
  } catch {}

  const cardLoaded = lovelaceCardRegistered();
  const resourceRegistered = await lovelaceResourceRegistered();

  if (cardLoaded) {
    lovelaceCardState.textContent = "Bereit";
    lovelaceCardState.className = "lovelace-state ready";
    lovelaceSetupStatus.textContent = t("Die TV-Guide-Karte ist geladen und steht im Kartenwähler zur Verfügung.");
    return;
  }

  if (resourceRegistered === true) {
    lovelaceCardState.textContent = t("Ressource eingetragen");
    lovelaceCardState.className = "lovelace-state pending";
    lovelaceSetupStatus.textContent = t("Die Ressource ist bereits in Home Assistant eingetragen. Lade die Home-Assistant-Oberfläche jetzt einmal vollständig neu; danach sollte TV Guide im Kartenwähler erscheinen.");
    return;
  }

  if (assetReady && resourceRegistered === false) {
    lovelaceCardState.textContent = t("Ressource fehlt");
    lovelaceCardState.className = "lovelace-state pending";
    lovelaceSetupStatus.textContent = t("Die Kartendatei ist installiert, aber noch nicht als Home-Assistant-Ressource eingetragen.");
    return;
  }

  if (assetReady) {
    lovelaceCardState.textContent = t("Datei bereit");
    lovelaceCardState.className = "lovelace-state pending";
    lovelaceSetupStatus.textContent = t("Die Kartendatei ist installiert. Der Ressourcenstatus konnte aus der Ingress-Seite nicht sicher gelesen werden. Falls du sie bereits eingetragen hast, lade Home Assistant einmal vollständig neu.");
  } else {
    lovelaceCardState.textContent = t("Noch nicht bereit");
    lovelaceCardState.className = "lovelace-state error";
    lovelaceSetupStatus.textContent = t("Die Kartendatei ist noch nicht unter /local erreichbar. Falls /local bisher nicht verwendet wurde, starte Home Assistant einmal neu und prüfe danach erneut.");
  }
}

async function copyLovelaceResourceUrl() {
  const value = lovelaceResourceUrl.textContent.trim();

  const clipboardTargets = [];
  try { if (window.top?.navigator?.clipboard?.writeText) clipboardTargets.push(window.top.navigator.clipboard); } catch {}
  try { if (window.parent?.navigator?.clipboard?.writeText) clipboardTargets.push(window.parent.navigator.clipboard); } catch {}
  try { if (navigator.clipboard?.writeText) clipboardTargets.push(navigator.clipboard); } catch {}

  for (const clipboard of clipboardTargets) {
    try {
      await clipboard.writeText(value);
      lovelaceSetupStatus.textContent = t("Ressourcen-URL kopiert.");
      return;
    } catch {}
  }

  const docs = [];
  try { if (window.top?.document) docs.push(window.top.document); } catch {}
  try { if (window.parent?.document) docs.push(window.parent.document); } catch {}
  docs.push(document);

  for (const doc of docs) {
    try {
      const textarea = doc.createElement("textarea");
      textarea.value = value;
      textarea.setAttribute("readonly", "");
      textarea.style.position = "fixed";
      textarea.style.left = "-9999px";
      textarea.style.top = "0";
      textarea.style.opacity = "0";
      doc.body.appendChild(textarea);
      textarea.focus();
      textarea.select();
      textarea.setSelectionRange(0, value.length);
      const ok = doc.execCommand("copy");
      textarea.remove();

      if (ok) {
        lovelaceSetupStatus.textContent = t("Ressourcen-URL kopiert.");
        return;
      }
    } catch {}
  }

  try {
    const range = document.createRange();
    range.selectNodeContents(lovelaceResourceUrl);
    const selection = window.getSelection();
    selection.removeAllRanges();
    selection.addRange(range);
    lovelaceSetupStatus.textContent = t("Automatisches Kopieren wird vom Browser blockiert. Die Ressourcen-URL ist markiert; bitte einmal manuell kopieren.");
  } catch {
    lovelaceSetupStatus.textContent = t("Automatisches Kopieren wird vom Browser blockiert. Bitte die Ressourcen-URL manuell kopieren.");
  }
}

function openLovelaceResourcesPage() {
  try {
    if (window.parent !== window) {
      window.parent.location.href = "/config/lovelace/resources";
    } else {
      window.location.href = "/config/lovelace/resources";
    }
  } catch {
    lovelaceSetupStatus.textContent = t("Öffnen nicht möglich. Bitte Einstellungen → Dashboards → Ressourcen manuell öffnen.");
  }
}

async function loadNotificationServiceChoices(currentService, isCurrent = () => true) {
  const fallback = currentService || "persistent_notification.create";
  const url = new URL("api/notification-services", window.location.href);
  let services = [];

  try {
    const res = await fetch(url, {cache:"no-store"});
    if (!res.ok) throw new Error(t("Empfänger konnten nicht geladen werden."));
    const payload = await res.json();
    services = Array.isArray(payload.services) ? payload.services : [];
  } catch {
    services = [{
      service:"persistent_notification.create",
      label:t("Home Assistant"),
      type:"home_assistant"
    }];
  }

  if (!isCurrent()) return;
  if (!services.some(item => item.service === fallback)) {
    services.push({
      service:fallback,
      label:t("Aktuell konfiguriert · {service}", {service:fallback}),
      type:"existing"
    });
  }

  settingNotificationService.innerHTML = services
    .map(item =>
      '<option value="' + escapeHtml(item.service) + '">' +
      escapeHtml(item.type === "mobile_app" ? t("Mobilgerät · {device}", {device:(item.label || item.service).split(" · ").slice(1).join(" · ")}) : item.label || item.service) +
      '</option>'
    )
    .join("");
  settingNotificationService.value = fallback;
}

async function openAppSettings() {
  const request = ++appSettingsRequest;
  const isCurrent = () => request === appSettingsRequest && appSettingsDialog.open;
  appSettingsStatus.textContent = t("Einstellungen werden geladen …");
  saveAppSettings.disabled = true;
  appSettingsDialog.querySelectorAll("details").forEach(section => section.open = false);
  appSettingsDialog.showModal();
  appSettingsDialog.scrollTop = 0;
  try {
    const url = new URL("api/settings", window.location.href);
    const res = await fetch(url, {cache:"no-store"});
    if (!res.ok) throw new Error(t("Einstellungen konnten nicht geladen werden."));
    const settings = await res.json();
    if (!isCurrent()) return;
    globalThis.TVGuideI18n?.configure(settings);
    settingLanguage.value = settings.language || "auto";
    settingCountry.value = settings.country || "de";
    settingDefaultView.value = settings.default_view || "now";
    settingColumns.value = String(settings.columns_desktop || 5);
    settingMaxChannels.value = String(settings.max_channels ?? 0);
    settingTheme.value = settings.theme_mode || "auto";
    settingRefresh.value = String(settings.refresh_minutes || 180);
    sensorSettings.forEach(input => { input.checked = settings[input.dataset.sensorOption] === true; });
    await loadNotificationServiceChoices(
      settings.notification_service || "persistent_notification.create", isCurrent
    );
    if (!isCurrent()) return;
    appSettingsStatus.textContent = "";
    saveAppSettings.disabled = false;
    await checkLovelaceSetup();
  } catch (err) {
    if (isCurrent()) appSettingsStatus.textContent = t(err.message);
  }
}

async function persistAppSettings() {
  const request = appSettingsRequest;
  const isCurrent = () => request === appSettingsRequest && appSettingsDialog.open;
  appSettingsStatus.textContent = t("Wird gespeichert …");
  saveAppSettings.disabled = true;
  try {
    const url = new URL("api/settings", window.location.href);
    const res = await fetch(url, {
      method:"POST",
      headers:{"Content-Type":"application/json"},
      body:JSON.stringify({
        country:settingCountry.value,
        language:settingLanguage.value,
        default_view:settingDefaultView.value,
        columns_desktop:Number(settingColumns.value),
        max_channels:Number(settingMaxChannels.value),
        theme_mode:settingTheme.value,
        refresh_minutes:Number(settingRefresh.value),
        notification_service:settingNotificationService.value.trim(),
        ...Object.fromEntries(sensorSettings.map(input => [input.dataset.sensorOption, input.checked]))
      })
    });
    const payload = await res.json();
    if (!res.ok || !payload.ok) throw new Error(t(payload.error) || t("Einstellungen konnten nicht gespeichert werden."));
    await loadGuide();
    if (!isCurrent()) return;
    appSettingsStatus.textContent = payload.refresh_started
      ? t("Gespeichert. Programmdaten werden im Hintergrund aktualisiert.")
      : t("Gespeichert.");
    window.setTimeout(() => { if (isCurrent()) appSettingsDialog.close(); }, 500);
  } catch (err) {
    if (isCurrent()) appSettingsStatus.textContent = t(err.message);
  } finally {
    if (isCurrent()) saveAppSettings.disabled = false;
  }
}

async function openChannelSettings() {
  const request = ++channelSettingsRequest;
  channelPicker.beginLoading();
  channelSettingsStatus.textContent = t("Senderliste wird geladen …");
  saveChannelSettings.disabled = true;
  resetChannelSettings.disabled = true;
  channelSettingsDialog.showModal();
  try {
    const url = new URL("api/personal-channels", window.location.href);
    const res = await fetch(url, {cache:"no-store"});
    if (!res.ok) throw new Error(t("Senderliste konnte nicht geladen werden."));
    const settings = await res.json();
    if (request !== channelSettingsRequest || !channelSettingsDialog.open) return;
    channelPicker.setData(settings);
    saveChannelSettings.disabled = false;
    resetChannelSettings.disabled = false;
    channelSettingsStatus.textContent = "";
  } catch (err) {
    if (request === channelSettingsRequest && channelSettingsDialog.open) channelSettingsStatus.textContent = t(err.message);
  }
}

async function persistChannelSettings(reset = false) {
  const request = channelSettingsRequest;
  const isCurrent = () => request === channelSettingsRequest && channelSettingsDialog.open;
  channelSettingsStatus.textContent = t("Wird gespeichert …");
  saveChannelSettings.disabled = true;
  resetChannelSettings.disabled = true;

  try {
    const url = new URL("api/personal-channels", window.location.href);
    const res = await fetch(url, {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify(reset ? {reset:true} : channelPicker.value())
    });
    const payload = await res.json();
    if (!res.ok || !payload.ok) throw new Error(t(payload.error) || t("Senderreihenfolge konnte nicht gespeichert werden."));

    if (reset) {
      if (isCurrent()) {
        const reload = await fetch(url, {cache:"no-store"});
        if (!reload.ok) throw new Error(t("Senderliste konnte nicht geladen werden."));
        const settings = await reload.json();
        if (isCurrent()) {
          channelPicker.setData(settings);
          channelSettingsStatus.textContent = t("Standardsortierung wiederhergestellt.");
        }
      }
      await loadGuide();
      return;
    }

    if (isCurrent()) {
      channelSettingsDialog.close();
      channelView = "custom";
      document.querySelectorAll("[data-channel-view]").forEach(button =>
        button.classList.toggle("active", button.dataset.channelView === channelView));
    }
    await loadGuide();
  } catch (err) {
    if (isCurrent()) channelSettingsStatus.textContent = t(err.message);
  } finally {
    if (isCurrent()) {
      saveChannelSettings.disabled = false;
      resetChannelSettings.disabled = false;
    }
  }
}

let renderedChannels = new Map();
const renderedCards = new Map();

// One delegated listener survives programme and theme updates.
grid.addEventListener("click", event => {
  const row = event.target.closest("[data-program-start]");
  const section = row?.closest(".channel-card");
  const channel = renderedChannels.get(section?.dataset.channelId);
  const programme = channel?.programs?.find(item => item.start === row.dataset.programStart);
  if (programme) showDetail(channel, programme);
});

function render() {
  if (!guide) return;
  if (mode === "now") selectedDate = startOfDay(new Date());
  const channels = activeChannels();
  renderedChannels = new Map(channels.map(channel => [String(channel.id), channel]));
  if (!channels.length) {
    renderedCards.clear();
    const message = t("Noch keine eigenen Sender ausgewählt. Über „☰ Sender“ kannst du deine Senderliste zusammenstellen.");
    if (!grid.firstElementChild?.classList.contains("empty-channel-list")) {
      const empty = document.createElement("div");
      empty.className = "empty-channel-list";
      grid.replaceChildren(empty);
    }
    if (grid.firstElementChild.textContent !== message) grid.firstElementChild.textContent = message;
    return;
  }

  for (const child of Array.from(grid.children)) {
    if (!renderedChannels.has(child.dataset.channelId)) child.remove();
  }
  for (const id of renderedCards.keys()) {
    if (!renderedChannels.has(id)) renderedCards.delete(id);
  }
  const now = new Date();
  channels.forEach((channel, index) => {
    const id = String(channel.id);
    // Progress changes independently of programme content and must not replace focused buttons.
    const markup = TVGuideCore.renderChannelCard(channel, mode, selectedDate, customTarget, "", false);
    let card = renderedCards.get(id);
    if (!card || card.markup !== markup) {
      const template = document.createElement("template");
      template.innerHTML = markup;
      const element = template.content.firstElementChild;
      card?.element.replaceWith(element);
      card = {markup, element};
      renderedCards.set(id, card);
    }
    if (grid.children[index] !== card.element) grid.insertBefore(card.element, grid.children[index] || null);
    const progress = card.element.querySelector(".progress-fill");
    if (progress) {
      const start = card.element.querySelector(".program.current [data-program-start]").dataset.programStart;
      const programme = channel.programs.find(item => item.start === start);
      progress.style.width = TVGuideCore.pct(programme.start, programme.end, now) + "%";
    }
  });
}

function setMode(nextMode) {
  if (nextMode === "other") {
    initCustomDate();
    customTimeDialog.showModal();
    return;
  }

  mode = nextMode;
  if (nextMode === "now") selectedDate = startOfDay(new Date());
  document.querySelectorAll(".tab").forEach(b =>
    b.classList.toggle("active", b.dataset.mode === nextMode));
  render();
}

function initCustomDate() {
  customDate.value = dateKey(selectedDate);
  customDate.min = dateKey(new Date());
  if (guide?.channels?.length) {
    let latest = -Infinity;
    for (const channel of guide.channels) {
      for (const programme of channel.programs || []) {
        const end = new Date(programme.end).getTime();
        if (Number.isFinite(end) && end > latest) latest = end;
      }
    }
    // Clear a previous country's limit if the new country has no valid dates.
    customDate.max = Number.isFinite(latest) ? dateKey(new Date(latest)) : "";
  }
}

let guideRequest = 0;
async function loadGuide() {
  const request = ++guideRequest;
  const url = new URL("api/guide", window.location.href);
  const res = await fetch(url, {cache:"no-store"});
  if (!res.ok) throw new Error(t("Programmdaten konnten nicht geladen werden."));
  const nextGuide = await res.json();
  if (request !== guideRequest) return;
  const countryChanged = guide && guide.country !== nextGuide.country;
  guide = nextGuide;
  lastGuideLoadedAt = Date.now();
  const languageChanged = globalThis.TVGuideI18n?.configure({...guide.ui, country:guide.country});
  if (languageChanged) {
    renderBookmarks();
    if (activeDetail) updateDetailControls();
  }

  const columns = Number(guide.ui?.columns_desktop || 5);
  document.documentElement.style.setProperty("--desktop-columns", String(Math.max(3, Math.min(6, columns))));
  syncHomeAssistantTheme();

  if (!document.body.dataset.initialized) {
    mode = ["now","1800","2015","2200"].includes(guide.ui?.default_view) ? guide.ui.default_view : "now";
    document.body.dataset.initialized = "1";
    saveBookmarksLocal();
  }
  initCustomDate();
  document.querySelectorAll(".tab").forEach(b =>
    b.classList.toggle("active", b.dataset.mode === mode));
  render();
  if (countryChanged) window.scrollTo({top:0, behavior:"instant"});

  clearTimeout(startupReloadTimer);
  if (guide.refresh_running && !document.hidden) {
    startupReloadTimer = setTimeout(() => loadGuide().catch(() => {}), 1500);
  } else {
    startupReloadTimer = null;
  }
}

document.querySelectorAll(".tab").forEach(btn =>
  btn.addEventListener("click", () => setMode(btn.dataset.mode)));

document.querySelectorAll("[data-channel-view]").forEach(button =>
  button.addEventListener("click", () => {
    channelView = button.dataset.channelView === "custom" ? "custom" : "main";
    document.querySelectorAll("[data-channel-view]").forEach(item =>
      item.classList.toggle("active", item.dataset.channelView === channelView));
    initCustomDate();
      render();
  }));


applyCustomTime.addEventListener("click", () => {
  if (!customDate.value || !customTime.value) return;
  const target = new Date(customDate.value + "T" + customTime.value + ":00");
  if (Number.isNaN(target.getTime())) return;
  selectedDate = startOfDay(target);
  customTarget = target;
  mode = "other";
  document.querySelectorAll(".tab").forEach(b =>
    b.classList.toggle("active", b.dataset.mode === "other"));
  customTimeDialog.close();
  render();
});

cancelCustomTime.addEventListener("click", () => customTimeDialog.close());
customTimeClose.addEventListener("click", () => customTimeDialog.close());
customTimeDialog.addEventListener("click", event => {
  if (event.target === customTimeDialog) customTimeDialog.close();
});

bookmarkProgram.addEventListener("click", toggleBookmark);
reminderEnabled.addEventListener("change", async () => {
  if (!activeDetail || reminderEnabled.disabled) return;
  reminderEnabled.disabled = true;
  reminderMinutes.hidden = !reminderEnabled.checked;
  reminderMinutes.disabled = true;
  reminderStatus.textContent = reminderEnabled.checked
    ? t("Erinnerung wird gespeichert …")
    : t("Erinnerung wird entfernt …");
  try {
    await saveReminderForActiveDetail(
      reminderEnabled.checked,
      Number(reminderMinutes.value || 10)
    );
  } catch (err) {
    updateDetailControls();
    reminderStatus.textContent = t(err.message);
    return;
  }
  updateDetailControls();
});
reminderMinutes.addEventListener("change", async () => {
  if (!activeDetail || !reminderEnabled.checked || reminderMinutes.disabled) return;
  reminderMinutes.disabled = true;
  reminderStatus.textContent = t("Erinnerung wird aktualisiert …");
  try {
    await saveReminderForActiveDetail(
      true,
      Number(reminderMinutes.value || 10)
    );
  } catch (err) {
    updateDetailControls();
    reminderStatus.textContent = t(err.message);
    return;
  }
  updateDetailControls();
});
showBookmarks.addEventListener("click", () => {
  renderBookmarks();
  testNotificationStatus.textContent = "";
  bookmarksDialog.showModal();
});
testNotification.addEventListener("click", testConfiguredNotification);
showAppSettings.addEventListener("click", openAppSettings);
copyLovelaceResource.addEventListener("click", copyLovelaceResourceUrl);
openLovelaceResources.addEventListener("click", openLovelaceResourcesPage);
checkLovelaceCard.addEventListener("click", checkLovelaceSetup);
saveAppSettings.addEventListener("click", persistAppSettings);
cancelAppSettings.addEventListener("click", () => appSettingsDialog.close());
showChannelSettings.addEventListener("click", openChannelSettings);
saveChannelSettings.addEventListener("click", () => persistChannelSettings(false));
resetChannelSettings.addEventListener("click", () => persistChannelSettings(true));
cancelChannelSettings.addEventListener("click", () => channelSettingsDialog.close());
detail.querySelector(".close").addEventListener("click", () => detail.close());
bookmarksDialog.querySelector(".bookmarks-close").addEventListener("click", () => bookmarksDialog.close());
appSettingsDialog.querySelector(".app-settings-close").addEventListener("click", () => appSettingsDialog.close());
channelSettingsDialog.querySelector(".channel-settings-close").addEventListener("click", () => channelSettingsDialog.close());
detail.addEventListener("click", e => { if (e.target === detail) detail.close(); });
bookmarksDialog.addEventListener("click", e => { if (e.target === bookmarksDialog) bookmarksDialog.close(); });
appSettingsDialog.addEventListener("click", e => { if (e.target === appSettingsDialog) appSettingsDialog.close(); });
channelSettingsDialog.addEventListener("click", e => { if (e.target === channelSettingsDialog) channelSettingsDialog.close(); });

watchHomeAssistantTheme();
Promise.all([loadBookmarksRemote(), loadReminders(), loadGuide()]).catch(() => {
  if (!guide) grid.innerHTML = ("<div class=\"empty-channel-list\">" + escapeHtml(t("Das TV-Programm konnte nicht geladen werden. Bitte versuche es erneut.")) + "</div>");
});
document.addEventListener("visibilitychange", () => {
  if (document.hidden) {
    clearTimeout(startupReloadTimer);
    startupReloadTimer = null;
  } else {
    if (!guide || guide.refresh_running || Date.now() - lastGuideLoadedAt >= GUIDE_VISIBILITY_REFRESH_AGE) {
      loadGuide().catch(() => {});
    } else if (mode === "now") {
      render();
    }
    loadReminders().catch(() => {});
    loadBookmarksRemote().then(() => {
      if (bookmarksDialog.open) renderBookmarks();
    }).catch(() => {});
  }
});
setInterval(() => {
  if (document.hidden) return;
  loadGuide().catch(() => {});
  loadReminders().catch(() => {});
  loadBookmarksRemote().then(() => {
    if (bookmarksDialog.open) renderBookmarks();
  }).catch(() => {});
}, 5 * 60 * 1000);
setInterval(() => { if (!document.hidden && mode === "now") render(); }, 60 * 1000);
