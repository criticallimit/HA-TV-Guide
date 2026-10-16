import {createI18n} from './i18n.js?v=native-21';
import {createGuideCore} from './guide-core.js?v=native-13';
import {TVGuideChannelPicker} from './channel-picker.js?v=native-14';
import {createPreparation} from './preparation.js?v=native-11';
import {createScope} from './lifecycle.js';

export function createGuideApp({root, request:requestAction, getHass, getTheme}) {
const scope = createScope();
const setTimeout = scope.setTimeout;
const clearTimeout = scope.clearTimeout;
const setInterval = scope.setInterval;
const i18n = createI18n(root, getHass);
const TVGuideCore = createGuideCore(i18n);
const t = (message, values) => i18n?.t(message, values) || message;
const grid = root.querySelector("#grid");
const guideHeader = root.querySelector(".guide-header");
function updateScrollEndSpace() {
  const cards = Array.from(grid.querySelectorAll(".channel-card"));
  let space = 0;
  if (cards.length) {
    const lastTop = cards[cards.length - 1].offsetTop;
    if (lastTop > cards[0].offsetTop) {
      const lastRowHeight = Math.max(...cards.filter(card => Math.abs(card.offsetTop - lastTop) < 1)
        .map(card => card.getBoundingClientRect().height));
      const bottomPadding = parseFloat(getComputedStyle(grid.parentElement).paddingBottom) || 0;
      space = Math.max(0, root.clientHeight - guideHeader.offsetHeight - lastRowHeight - bottomPadding);
    }
  }
  const padding = space + "px";
  if (grid.style.paddingBottom !== padding) grid.style.paddingBottom = padding;
}
scope.observe(grid, updateScrollEndSpace);
scope.observe(root, updateScrollHeaderHeight);
function updateScrollHeaderHeight() {
  const dimensions = {"--guide-width":root.clientWidth,"--guide-height":root.clientHeight,"--guide-header-height":guideHeader.offsetHeight};
  for (const [name, size] of Object.entries(dimensions)) {
    const value = size + "px";
    if (root.style.getPropertyValue(name) !== value) root.style.setProperty(name, value);
  }
  updateScrollEndSpace();
}
scope.observe(guideHeader, updateScrollHeaderHeight);
updateScrollHeaderHeight();
let lastRowScroll = -Infinity;
scope.listen(root, "wheel", event => {
  if (event.ctrlKey || event.shiftKey || !event.deltaY ||
      Math.abs(event.deltaX) > Math.abs(event.deltaY) || root.querySelector("dialog[open]")) return;
  const cards = Array.from(grid.querySelectorAll(".channel-card"));
  if (!cards.length) return;
  const headerHeight = guideHeader.offsetHeight;
  // Tall rows must remain freely scrollable so every programme is reachable.
  if (cards.some(card => card.offsetHeight > root.clientHeight - headerHeight)) return;
  const rows = [...new Set(cards.map(card => Math.round(card.getBoundingClientRect().top - root.getBoundingClientRect().top + root.scrollTop)))];
  const stops = rows.map((top, index) => index === 0 ? 0 : Math.max(0, top - headerHeight));
  const target = event.deltaY > 0
    ? stops.find(top => top > root.scrollTop + 2)
    : stops.reverse().find(top => top < root.scrollTop - 2);
  if (target === undefined) return;
  event.preventDefault();
  const now = performance.now();
  if (now - lastRowScroll < 300) return;
  lastRowScroll = now;
  root.scrollTo({top:target, behavior:"instant"});
}, {passive:false});
const detail = root.querySelector("#detail");
const detailBody = root.querySelector("#detailBody");
const bookmarkProgram = root.querySelector("#bookmarkProgram");
const bookmarkCount = root.querySelector("#bookmarkCount");
const showBookmarks = root.querySelector("#showBookmarks");
const bookmarksDialog = root.querySelector("#bookmarksDialog");
const bookmarksBody = root.querySelector("#bookmarksBody");
const testNotification = root.querySelector("#testNotification");
const testNotificationStatus = root.querySelector("#testNotificationStatus");
const customTimeDialog = root.querySelector("#customTimeDialog");
const customDate = root.querySelector("#customDate");
const customTime = root.querySelector("#customTime");
const applyCustomTime = root.querySelector("#applyCustomTime");
const cancelCustomTime = root.querySelector("#cancelCustomTime");
const customTimeClose = root.querySelector(".custom-time-close");
const reminderEnabled = root.querySelector("#reminderEnabled");
const reminderMinutes = root.querySelector("#reminderMinutes");
const reminderStatus = root.querySelector("#reminderStatus");
const showChannelSettings = root.querySelector("#showChannelSettings");
const channelSettingsDialog = root.querySelector("#channelSettingsDialog");
const channelPicker = new TVGuideChannelPicker(channelSettingsDialog, i18n);
const saveChannelSettings = root.querySelector("#saveChannelSettings");
const resetChannelSettings = root.querySelector("#resetChannelSettings");
const cancelChannelSettings = root.querySelector("#cancelChannelSettings");
const channelSettingsStatus = root.querySelector("#channelSettingsStatus");
const showAppSettings = root.querySelector("#showAppSettings");
const appSettingsDialog = root.querySelector("#appSettingsDialog");
const settingLanguage = root.querySelector("#settingLanguage");
const settingCountry = root.querySelector("#settingCountry");
const settingDefaultView = root.querySelector("#settingDefaultView");
const settingColumns = root.querySelector("#settingColumns");
const settingMaxChannels = root.querySelector("#settingMaxChannels");
const settingTheme = root.querySelector("#settingTheme");
const settingRefresh = root.querySelector("#settingRefresh");
const settingNotificationService = root.querySelector("#settingNotificationService");
const saveAppSettings = root.querySelector("#saveAppSettings");
const cancelAppSettings = root.querySelector("#cancelAppSettings");
const appSettingsStatus = root.querySelector("#appSettingsStatus");

function syncHomeAssistantTheme() {
  const mode = guide?.ui?.theme_mode || "auto";
  const theme = mode === "dark" || mode === "light" ? mode : (getTheme().darkMode ? "dark" : "light");
  if (root.dataset.haTheme !== theme) root.dataset.haTheme = theme;
  if (root.dataset.haThemeSource !== "home-assistant") root.dataset.haThemeSource = "home-assistant";
}

const fmt = TVGuideCore.fmt;
const dateFmt = TVGuideCore.dateFmt;

let guide = null;
// A bounded first-paint snapshot, scoped to this browser tab. Time coverage
// decides whether an older snapshot can still produce a useful initial view.
// Only store it when serialization fits the strict size budget; never add polling.
const GUIDE_FIRST_PAINT_KEY = "tv-guide-first-paint-v1";
const GUIDE_FIRST_PAINT_TTL_MS = 6 * 60 * 60 * 1000;
const GUIDE_FIRST_PAINT_MAX_CHARS = 1024 * 1024;
function showCachedGuide() {
  try {
    const raw = sessionStorage.getItem(GUIDE_FIRST_PAINT_KEY);
    if (!raw || raw.length > GUIDE_FIRST_PAINT_MAX_CHARS) return;
    const cached = JSON.parse(raw);
    if (!cached || cached.version !== 1 || !Number.isFinite(cached.at) || Date.now() - cached.at > GUIDE_FIRST_PAINT_TTL_MS ||
        cached.at > Date.now() || !cached.guide || !Array.isArray(cached.guide.channels) ||
        !cached.guide.ui || cached.guide.refresh_running) return;
    const initialMode = ["now","1800","2015","2200"].includes(cached.guide.ui.default_view)
      ? cached.guide.ui.default_view : "now";
    const target = TVGuideCore.targetForMode(initialMode,startOfDay(new Date()),null).getTime();
    // A gap on one sender must not hide useful schedules on all the others.
    // Reject a wholly expired window; render still-useful upcoming rows now.
    const populated = cached.guide.channels.filter(channel => channel.programs?.length);
    if (populated.length && !populated.some(channel => channel.programs.some(item =>
      new Date(item.end).getTime() > target))) return;
    guide = cached.guide;
    i18n?.configure({...guide.ui, country:guide.country});
    const columns = Number(guide.ui.columns_desktop || 5);
    root.style.setProperty("--desktop-columns", String(Math.max(3, Math.min(6, columns))));
    mode = ["now","1800","2015","2200"].includes(guide.ui.default_view) ? guide.ui.default_view : "now";
    root.dataset.initialized = "1";
    root.querySelectorAll(".tab").forEach(b => b.classList.toggle("active", b.dataset.mode === mode));
    syncHomeAssistantTheme();
    render();
  } catch {
    // Storage can be disabled or full; normal network-backed loading continues.
  }
}
function guideWindow(snapshot, target) {
  const channels = snapshot.channels.map(channel => {
    const entries = channel.programs || [];
    const index = entries.findIndex(item => new Date(item.end).getTime() > target);
    return {...channel, programs:index < 0 ? [] : entries.slice(index,index+7)};
  });
  return {...snapshot, channels, _preview:true};
}
function releaseGuideTimelines() {
  if (!guide) return;
  // Lovelace may retain detached cards. Keep their visible rows and selection,
  // but release the much larger full EPG and every channel reference to it.
  const target = TVGuideCore.targetForMode(mode, selectedDate, customTarget).getTime();
  guide = guideWindow(guide, target);
  renderedChannels = new Map(activeChannels().map(channel => [String(channel.id),channel]));
  activeDetail = null;
  lastGuideLoadedAt = 0;
}
function saveFirstPaintGuide(snapshot) {
  if (snapshot.refresh_running) return;
  // Prepare the snapshot when idle to avoid blocking a user interaction.
  const save = () => {
    if (guide !== snapshot) return;
    try {
      // Store only a short window around the current programme per channel;
      // avoid copying days of EPG or keeping programme history in browser storage.
      const now = Date.now();
      const initialMode = snapshot.ui?.default_view || "now";
      const target = TVGuideCore.targetForMode(initialMode,startOfDay(new Date()),null).getTime();
      const data = JSON.stringify({version:1, at:now, guide:guideWindow(snapshot, target)});
      if (data.length <= GUIDE_FIRST_PAINT_MAX_CHARS) sessionStorage.setItem(GUIDE_FIRST_PAINT_KEY, data);
      else sessionStorage.removeItem(GUIDE_FIRST_PAINT_KEY);
    } catch {}
  };
  scope.idle(save);
}
let mode = "now";
let initialViewPending = true;
let selectedDate = startOfDay(new Date());
let customTarget = null;
let activeDetail = null;
let bookmarks = [];
let startupReloadTimer = null;
let lastGuideLoadedAt = 0;
const GUIDE_VISIBILITY_REFRESH_AGE = 60 * 1000;
let channelSettingsRequest = 0;
let appSettingsRequest = 0;
let settingsWrite = 0, settingsSaving = false;
let appSettingsEditable = false, notificationTesting = false;
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

function updateBookmarkCount() {
  bookmarkCount.textContent = String(bookmarks.length);
}

async function syncBookmark(action, item) {
  ++bookmarksRevision;
  if (action === "remove") ++remindersRevision;
  const body = action === "remove"
    ? {action:"remove", id:item.id}
    : {action:"upsert", ...item};
  const payload = await requestAction({endpoint:"bookmarks",method:"POST",body});
  if (!payload.ok) throw new Error(t(payload.error) || t("Merkliste konnte nicht gespeichert werden."));
  ++bookmarksRevision;
  if (action === "remove") ++remindersRevision;
  bookmarks = Array.isArray(payload.bookmarks) ? payload.bookmarks : [];
  updateBookmarkCount();
}

async function loadBookmarksRemote() {
  const request = ++bookmarksRequest;
  let revision = bookmarksRevision;
  const isCurrent = () => request === bookmarksRequest && revision === bookmarksRevision;
  try {
    const payload = await requestAction({endpoint:"bookmarks",method:"GET"});
    if (!isCurrent()) return;
    bookmarks = Array.isArray(payload.bookmarks) ? payload.bookmarks : [];

  } catch {
    // A failed refresh must not replace current entries with an earlier snapshot.
    if (!isCurrent()) return;
  }

  updateBookmarkCount();
}

function bookmarkId(channel, program) {
  return program.id || ((channel.source_channel_id || channel.id) + "|" + program.start + "|" + program.title);
}

const escapeHtml = TVGuideCore.escapeHtml;

function activeChannels() {
  if (!guide?.channels?.length) return [];
  const ids = channelView === "custom"
    ? (guide.custom_channel_ids || [])
    : (guide.main_channel_ids || []);
  const byId = new Map(guide.channels.map(channel => [channel.id, channel]));
  const maximum = Number(guide.ui?.max_channels) || 0;
  return (maximum > 0 ? ids.slice(0, maximum) : ids).map(id => byId.get(id)).filter(Boolean);
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
    const payload = await requestAction({endpoint:"reminders",method:"GET"});
    if (request !== remindersRequest || revision !== remindersRevision) return;
    reminders = Array.isArray(payload.reminders) ? payload.reminders : [];
  } catch {
    // Keep the last known reminders while the TV Guide action is temporarily unavailable.
  }
}

async function saveReminderForActiveDetail(enabled, minutes) {
  if (!activeDetail) return;
  ++remindersRevision;
  const {channel, program} = activeDetail;
  const id = bookmarkId(channel, program);

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
        language:i18n?.language || "de"
      }
    : {action:"remove", id};

  const payload = await requestAction({endpoint:"reminders",method:"POST",body});
  if (!payload.ok) {
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
  root.querySelector("#bookmarksStatus").textContent = "";
  const now = new Date();
  bookmarks = bookmarks.filter(x => new Date(x.end) > now);
  updateBookmarkCount();
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
        root.querySelector("#bookmarksStatus").textContent = t(err.message) || t("Sendung konnte nicht gelöscht werden.");
        btn.disabled = false;
      }
    });
  });
}

async function testConfiguredNotification() {
  if (!appSettingsEditable || notificationTesting) return;
  const request = appSettingsRequest;
  const isCurrent = () => request === appSettingsRequest && appSettingsDialog.open;
  notificationTesting = true;
  testNotification.disabled = true;
  testNotificationStatus.textContent = t("Wird gesendet …");
  try {
    const payload = await requestAction({endpoint:"test-notification",method:"POST",body:{test:true, notification_service:settingNotificationService.value,
      language:i18n.resolve({language:settingLanguage.value, country:settingCountry.value})}});
    if (!payload.ok) throw new Error(t(payload.error) || t("Testbenachrichtigung konnte nicht gesendet werden."));
    if (isCurrent()) testNotificationStatus.textContent = t("Gesendet über {service}", {service:payload.service});
  } catch (err) {
    if (isCurrent()) testNotificationStatus.textContent = t(err.message);
  } finally {
    notificationTesting = false;
    testNotification.disabled = !appSettingsEditable;
  }
}

async function loadNotificationServiceChoices(currentService, isCurrent = () => true) {
  const fallback = currentService || "persistent_notification.create";

  let services = [];

  try {
    const payload = await requestAction({endpoint:"notification-services",method:"GET"});
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

function setAppSettingsEditing(enabled) {
  appSettingsEditable = enabled;
  testNotification.disabled = !enabled || notificationTesting;
  appSettingsDialog.querySelectorAll("input, select").forEach(control => control.disabled = !enabled);
}
function setChannelSettingsEditing(enabled) {
  channelSettingsDialog.querySelector("#channelSearch").disabled = !enabled;
  for (const id of ["channelCountryFilters", "availableChannelsList", "channelSettingsList"]) {
    channelSettingsDialog.querySelector("#" + id).inert = !enabled;
  }
}

async function openAppSettings() {
  const request = ++appSettingsRequest;
  const isCurrent = () => request === appSettingsRequest && appSettingsDialog.open;
  appSettingsStatus.textContent = t("Einstellungen werden geladen …");
  testNotificationStatus.textContent = "";
  saveAppSettings.disabled = true;
  setAppSettingsEditing(false);
  appSettingsDialog.querySelectorAll("details").forEach(section => section.open = false);
  appSettingsDialog.showModal();
  appSettingsDialog.scrollTop = 0;
  try {
    const settings = await requestAction({endpoint:"settings",method:"GET"});
    if (!isCurrent()) return;
    i18n?.configure(settings);
    settingLanguage.value = settings.language || "auto";
    settingCountry.replaceChildren();
    const countries = settings.countries || settings.country_choices || [];
    for (const country of [...countries].sort((left, right) => t(left.name).localeCompare(t(right.name), i18n.language))) {
      const option = new Option(t(country.name), country.code);
      option.dataset.i18n = country.name;
      settingCountry.append(option);
    }
    if (!Array.isArray(settings.countries) || !settings.countries.length) {
      settingCountry.prepend(new Option(t("Alle Sender des eigenen Feeds"), ""));
    }
    settingCountry.value = settings.country ?? "";
    settingDefaultView.value = settings.default_view || "now";
    settingColumns.value = String(settings.columns_desktop || 5);
    settingMaxChannels.value = String(settings.max_channels ?? 0);
    settingTheme.value = settings.theme_mode || "auto";
    const interval = String(settings.refresh_minutes || 180);
    settingRefresh.querySelectorAll('[data-custom-interval]').forEach(option => option.remove());
    if (![...settingRefresh.options].some(option => option.value === interval)) {
      const option = new Option(interval + ' min', interval);
      option.dataset.customInterval = '1';
      settingRefresh.append(option);
    }
    settingRefresh.value = interval;
    await loadNotificationServiceChoices(
      settings.notification_service || "persistent_notification.create", isCurrent
    );
    if (!isCurrent()) return;
    appSettingsStatus.textContent = "";
    setAppSettingsEditing(true);
    saveAppSettings.disabled = false;
  } catch (err) {
    if (isCurrent()) appSettingsStatus.textContent = t(err.message);
  }
}

function appSettingsValues() {
  return {
    country:settingCountry.value, language:settingLanguage.value,
    default_view:settingDefaultView.value, columns_desktop:Number(settingColumns.value),
    max_channels:Number(settingMaxChannels.value), theme_mode:settingTheme.value,
    refresh_minutes:Number(settingRefresh.value), notification_service:settingNotificationService.value.trim()
  };
}

function applyCommittedAppSettings(committed) {
  i18n.configure({...committed, home_assistant:guide?.ui?.home_assistant});
  if (!guide) return;
  guide = {...guide, ui:{...guide.ui, ...committed}};
  root.style.setProperty("--desktop-columns", String(Math.max(3,Math.min(6,Number(guide.ui.columns_desktop)||5))));
  syncHomeAssistantTheme();
  render(); renderBookmarks(); if (activeDetail) updateDetailControls();
  lastGuideLoadedAt = 0;
  if (committed.country === guide.country) saveFirstPaintGuide(guide);
  else { try { sessionStorage.removeItem(GUIDE_FIRST_PAINT_KEY); } catch {} }
}

async function persistAppSettings() {
  for (const control of [settingColumns, settingMaxChannels]) {
    if (!control.checkValidity()) {
      control.closest('details').open = true;
      control.reportValidity();
      return;
    }
  }
  const write = ++settingsWrite;
  settingsSaving = true;
  // A guide started before this transaction must not repaint the old country
  // or language while the latest selection is being committed.
  ++guideRequest;
  clearTimeout(startupReloadTimer); startupReloadTimer = null;
  const request = appSettingsRequest;
  const isCurrent = () => request === appSettingsRequest && appSettingsDialog.open;
  appSettingsStatus.textContent = t("Wird gespeichert …");
  saveAppSettings.disabled = true;
  setAppSettingsEditing(false);
  let saved = false, lateConfirmed = false;
  const changes = appSettingsValues();
  const confirm = (payload, late = false) => {
    if (!payload.ok || write !== settingsWrite) return;
    lateConfirmed ||= late;
    const preserveDraft = late && isCurrent() && JSON.stringify(appSettingsValues()) !== JSON.stringify(changes);
    applyCommittedAppSettings(payload.settings || changes);
    if (isCurrent()) {
      if (preserveDraft) appSettingsStatus.textContent = "";
      else {
        setAppSettingsEditing(false);
        saveAppSettings.disabled = true;
        appSettingsStatus.textContent = payload.refresh_started
          ? t("Gespeichert. Programmdaten werden im Hintergrund aktualisiert.") : t("Gespeichert.");
        setTimeout(() => { if (isCurrent()) appSettingsDialog.close(); }, 500);
      }
    }
    if (late) loadGuide().catch(() => {});
  };
  try {
    const payload = await requestAction({endpoint:"settings", method:"POST", body:changes,
      onLateResponse:payload => confirm(payload, true)});
    if (!payload.ok) throw new Error(t(payload.error) || t("Einstellungen konnten nicht gespeichert werden."));
    saved = true;
    confirm(payload);
  } catch (err) {
    if (isCurrent() && !lateConfirmed) appSettingsStatus.textContent = t(err.message);
  } finally {
    if (write === settingsWrite) {
      settingsSaving = false;
      // Refresh independently of the committed save, including after failure
      // so a rejected transaction cannot leave guide polling suspended.
      loadGuide().catch(() => {});
    }
    if (isCurrent() && !saved && !lateConfirmed) {
      setAppSettingsEditing(true);
      saveAppSettings.disabled = false;
    }
  }
}

async function openChannelSettings() {
  const request = ++channelSettingsRequest;
  channelPicker.beginLoading();
  setChannelSettingsEditing(false);
  channelSettingsStatus.textContent = t("Senderliste wird geladen …");
  saveChannelSettings.disabled = true;
  resetChannelSettings.disabled = true;
  channelSettingsDialog.showModal();
  try {
    const settings = await requestAction({endpoint:"personal-channels",method:"GET"});
    if (request !== channelSettingsRequest || !channelSettingsDialog.open) return;
    channelPicker.setData(settings);
    setChannelSettingsEditing(true);
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
  setChannelSettingsEditing(false);
  saveChannelSettings.disabled = true;
  resetChannelSettings.disabled = true;

  try {
    const payload = await requestAction({endpoint:"personal-channels",method:"POST",body:reset ? {reset:true} : channelPicker.value()});
    if (!payload.ok) throw new Error(t(payload.error) || t("Senderreihenfolge konnte nicht gespeichert werden."));

    if (reset) {
      if (isCurrent()) {
        const settings = await requestAction({endpoint:"personal-channels",method:"GET"});
        if (isCurrent()) {
          channelPicker.setData(settings);
          channelSettingsStatus.textContent = t("Standardsortierung wiederhergestellt.");
        }
      }
      loadGuide().catch(() => {});
      return;
    }

    if (isCurrent()) {
      channelSettingsDialog.close();
      channelView = "custom";
      root.querySelectorAll("[data-channel-view]").forEach(button =>
        button.classList.toggle("active", button.dataset.channelView === channelView));
    }
    loadGuide().catch(() => {});
  } catch (err) {
    if (isCurrent()) channelSettingsStatus.textContent = t(err.message);
  } finally {
    if (isCurrent()) {
      setChannelSettingsEditing(true);
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

function render(retryLogos = false) {
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
    // A time switch changes programmes, never the station's decoded logos.
    // Keep the card and branding mounted to avoid image/layout churn in WebKit.
    const brandMarkup = TVGuideCore.channelHeader(channel, "/tv_guide/frontend/app/");
    const programsMarkup = TVGuideCore.renderPrograms(channel, mode, selectedDate, customTarget, false);
    let card = renderedCards.get(id);
    if (!card) {
      const element = document.createElement("section");
      element.className = "channel-card";
      element.dataset.channelId = id;
      element.innerHTML = '<div class="channel-brand"></div><div class="programs"></div>';
      card = {element, brandMarkup:null, programsMarkup:null};
      renderedCards.set(id, card);
    }
    const failedLogo = retryLogos && Array.from(card.element.querySelectorAll(".channel-logo")).some(image => image.style.display === "none");
    if (card.brandMarkup !== brandMarkup || failedLogo) {
      card.element.querySelector(".channel-brand").innerHTML = brandMarkup;
      card.brandMarkup = brandMarkup;
    }
    if (card.programsMarkup !== programsMarkup) {
      card.element.querySelector(".programs").innerHTML = programsMarkup;
      card.programsMarkup = programsMarkup;
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

  initialViewPending = false;
  mode = nextMode;
  if (nextMode === "now") selectedDate = startOfDay(new Date());
  root.querySelectorAll(".tab").forEach(b =>
    b.classList.toggle("active", b.dataset.mode === nextMode));
  // The TV Guide guide response contains complete channel timelines. Re-render
  // an already loaded guide locally instead of waiting for a Home Assistant
  // websocket round trip on every time-tab click. Custom XMLTV responses are
  // bounded windows and must request rows for the newly selected time instead.
  // Cached and detached-card previews also contain only seven rows per sender.
  if (guide && !guide._windowed && !guide._preview) render();
  else loadGuide().catch(() => {});
}

function initCustomDate() {
  customDate.value = dateKey(selectedDate);
  customDate.min = dateKey(new Date());
  customDate.max = "";
  if (guide?.channels?.length) {
    let latest = guide.feed_latest_end ? new Date(guide.feed_latest_end).getTime() : -Infinity;
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
let guideRetryDelay = 1500;
let guideReloadFailed = false;
let guidePageSuspended = false;
let lifecycleRevision = 0;
function scheduleGuideReload(failed = false) {
  clearTimeout(startupReloadTimer);
  startupReloadTimer = null;
  if (document.hidden || guidePageSuspended) return;
  const delay = failed ? guideRetryDelay : guide?.refresh_running ? 1500 : 0;
  if (failed) guideRetryDelay = Math.min(30000, guideRetryDelay * 2);
  else guideRetryDelay = 1500;
  if (delay) startupReloadTimer = setTimeout(() => loadGuide().catch(() => {}), delay);
}
async function loadGuide(preview=false) {
  if (guidePageSuspended || settingsSaving) return;
  clearTimeout(startupReloadTimer);
  startupReloadTimer = null;
  const request = ++guideRequest;
  try {
    return await requestGuide(preview, request);
  } catch (error) {
    // Ignore stale failures; current requests retry until HA is reachable again.
    if (request === guideRequest) {
      guideReloadFailed = true;
      scheduleGuideReload(true);
    }
    throw error;
  }
}
async function requestGuide(preview, request) {
  const body = preview
    ? {preview:true,at:new Date().toISOString(),time_zone:Intl.DateTimeFormat().resolvedOptions().timeZone}
    : {};
  // Only a complete in-memory guide may opt into the minimal unchanged reply.
  if (!preview && guide?.revision && lastGuideLoadedAt) body.known_revision = guide.revision;
  const at = root.dataset.initialized && !initialViewPending ? TVGuideCore.targetForMode(mode,selectedDate,customTarget).toISOString() : undefined;
  const nextGuide = await requestAction({endpoint:"guide",method:"GET",at,body});
  if (request !== guideRequest) return;
  guideReloadFailed = false;
  guideRetryDelay = 1500;
  if (nextGuide.unchanged) {
    if (!guide || nextGuide.revision !== guide.revision) throw new Error("TV Guide revision mismatch");
    lastGuideLoadedAt = Date.now();
    if (mode === "now") render();
    scheduleGuideReload();
    return;
  }
  const countryChanged = guide && guide.country !== nextGuide.country;
  guide = nextGuide;
  lastGuideLoadedAt = nextGuide._preview ? 0 : Date.now();
  saveFirstPaintGuide(nextGuide);
  const languageChanged = i18n?.configure({...guide.ui, country:guide.country});
  if (languageChanged) {
    renderBookmarks();
    if (activeDetail) updateDetailControls();
  }

  const columns = Number(guide.ui?.columns_desktop || 5);
  root.style.setProperty("--desktop-columns", String(Math.max(3, Math.min(6, columns))));
  syncHomeAssistantTheme();

  if (initialViewPending) {
    mode = ["now","1800","2015","2200"].includes(guide.ui?.default_view) ? guide.ui.default_view : "now";
    if (!nextGuide._preview) initialViewPending = false;
  }
  if (!root.dataset.initialized) {
    root.dataset.initialized = "1";
    updateBookmarkCount();
  }
  initCustomDate();
  root.querySelectorAll(".tab").forEach(b =>
    b.classList.toggle("active", b.dataset.mode === mode));
  render();
  if (countryChanged) root.scrollTo({top:0, behavior:"instant"});

  if (nextGuide._preview) {
    clearTimeout(startupReloadTimer);
    // Allow the seven visible rows to paint before transferring full timelines.
    requestAnimationFrame(() => requestAnimationFrame(() => {
      if (request === guideRequest && !guidePageSuspended) loadGuide().catch(() => {});
    }));
  } else scheduleGuideReload();
}

root.querySelectorAll(".tab").forEach(btn =>
  btn.addEventListener("click", () => setMode(btn.dataset.mode)));

root.querySelectorAll("[data-channel-view]").forEach(button =>
  button.addEventListener("click", () => {
    channelView = button.dataset.channelView === "custom" ? "custom" : "main";
    root.querySelectorAll("[data-channel-view]").forEach(item =>
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
  initialViewPending = false;
  mode = "other";
  root.querySelectorAll(".tab").forEach(b =>
    b.classList.toggle("active", b.dataset.mode === "other"));
  customTimeDialog.close();
  if (guide && !guide._windowed && !guide._preview) render();
  else loadGuide().catch(() => {});
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
saveAppSettings.addEventListener("click", persistAppSettings);
cancelAppSettings.addEventListener("click", () => appSettingsDialog.close());
showChannelSettings.addEventListener("click", openChannelSettings);
saveChannelSettings.addEventListener("click", () => persistChannelSettings(false));
resetChannelSettings.addEventListener("click", () => persistChannelSettings(true));
cancelChannelSettings.addEventListener("click", () => channelSettingsDialog.close());
channelSettingsDialog.addEventListener("close", () => {
  // Close events are queued; do not clear a catalogue that was already reopened.
  if (channelSettingsDialog.open) return;
  ++channelSettingsRequest;
  channelPicker.beginLoading();
});
detail.querySelector(".close").addEventListener("click", () => detail.close());
bookmarksDialog.querySelector(".bookmarks-close").addEventListener("click", () => bookmarksDialog.close());
appSettingsDialog.querySelector(".app-settings-close").addEventListener("click", () => appSettingsDialog.close());
channelSettingsDialog.querySelector(".channel-settings-close").addEventListener("click", () => channelSettingsDialog.close());
detail.addEventListener("click", e => { if (e.target === detail) detail.close(); });
bookmarksDialog.addEventListener("click", e => { if (e.target === bookmarksDialog) bookmarksDialog.close(); });
appSettingsDialog.addEventListener("click", e => { if (e.target === appSettingsDialog) appSettingsDialog.close(); });
channelSettingsDialog.addEventListener("click", e => { if (e.target === channelSettingsDialog) channelSettingsDialog.close(); });

syncHomeAssistantTheme();
showCachedGuide();
const startupRevision = lifecycleRevision;
Promise.all([loadBookmarksRemote(), loadReminders(), loadGuide(!guide).catch(() => {
  if (startupRevision === lifecycleRevision && !guidePageSuspended) return loadGuide();
})]).catch(() => {
  if (startupRevision !== lifecycleRevision || guidePageSuspended) return;
  if (!guide) grid.innerHTML = ("<div class=\"empty-channel-list\">" + escapeHtml(t("Das TV-Programm konnte nicht geladen werden. Bitte versuche es erneut.")) + "</div>");
});
scope.listen(document, "visibilitychange", () => {
  if (document.hidden || guidePageSuspended) {
    clearTimeout(startupReloadTimer);
    startupReloadTimer = null;
  } else {
    if (guideReloadFailed || !guide || guide.refresh_running || Date.now() - lastGuideLoadedAt >= GUIDE_VISIBILITY_REFRESH_AGE) {
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
scope.listen(window, "pagehide", () => {
  guidePageSuspended = true;
  ++lifecycleRevision;
  releaseGuideTimelines();
  ++guideRequest;
  ++bookmarksRequest;
  ++remindersRequest;
  clearTimeout(startupReloadTimer);
  startupReloadTimer = null;
});
scope.listen(window, "pageshow", event => {
  if (!event.persisted) return;
  guidePageSuspended = false;
  loadGuide().catch(() => {});
  loadReminders().catch(() => {});
  loadBookmarksRemote().then(() => {
    if (bookmarksDialog.open) renderBookmarks();
  }).catch(() => {});
});
setInterval(() => {
  if (document.hidden || guidePageSuspended) return;
  loadGuide().catch(() => {});
  loadReminders().catch(() => {});
  loadBookmarksRemote().then(() => {
    if (bookmarksDialog.open) renderBookmarks();
  }).catch(() => {});
}, 5 * 60 * 1000);
setInterval(() => { if (!document.hidden && !guidePageSuspended && mode === "now") render(); }, 60 * 1000);

const preparation = createPreparation({root, request:requestAction, scope, render:()=>{if (guide) render(true);}});
function suspend() {
  guidePageSuspended = true;
  ++lifecycleRevision;
  releaseGuideTimelines();
  ++guideRequest; ++bookmarksRequest; ++remindersRequest;
  clearTimeout(startupReloadTimer); startupReloadTimer = null;
  root.querySelectorAll('dialog[open]').forEach(dialog=>dialog.close());
  preparation.suspend();
  scope.pause();
}
function resume() {
  scope.resume();
  guidePageSuspended = false;
  syncHomeAssistantTheme();
  if (guide && mode === 'now') render();
  if (guideReloadFailed || !guide || guide.refresh_running || Date.now()-lastGuideLoadedAt >= GUIDE_VISIBILITY_REFRESH_AGE) loadGuide().catch(()=>{});
  loadReminders().catch(()=>{});
  loadBookmarksRemote().then(()=>{if(bookmarksDialog.open)renderBookmarks();}).catch(()=>{});
  preparation.resume();
}
return {
  suspend, resume,
  updateTheme() {
    syncHomeAssistantTheme();
    if (guide && i18n.configure({...guide.ui,country:guide.country})) {
      render(); renderBookmarks(); if(activeDetail)updateDetailControls();
    }
  },
  get guide(){return guide;}, get mode(){return mode;}, get i18n(){return i18n;},
  loadGuide, get lastGuideLoadedAt(){return lastGuideLoadedAt;},
  get guideRetryDelay(){return guideRetryDelay;}, get startupReloadTimer(){return startupReloadTimer;},
  get suspended(){return guidePageSuspended;}
};
}
