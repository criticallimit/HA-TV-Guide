(function () {
  const t = (message, values) => globalThis.TVGuideI18n?.t(message, values) || message;
  const fmt = {format:value => globalThis.TVGuideI18n?.formatTime(value) || new Intl.DateTimeFormat("de-DE", {hour:"2-digit", minute:"2-digit"}).format(value)};
  const dateFmt = {format:value => globalThis.TVGuideI18n?.formatDate(value) || new Intl.DateTimeFormat("de-DE", {weekday:"short", day:"2-digit", month:"2-digit"}).format(value)};

  function escapeHtml(value) {
    return String(value || "").replace(/[&<>"']/g, c => ({
      "&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#039;"
    }[c]));
  }

  function startOfDay(value) {
    const d = new Date(value);
    d.setHours(0,0,0,0);
    return d;
  }

  function dateKey(value) {
    const d = new Date(value);
    const local = new Date(d.getTime() - d.getTimezoneOffset() * 60000);
    return local.toISOString().slice(0,10);
  }

  function sameDay(a,b) {
    return dateKey(a) === dateKey(b);
  }

  function targetForMode(mode, selectedDate, customTarget) {
    if (mode === "now") return new Date();
    if (mode === "other" && customTarget) return customTarget;
    const target = new Date(selectedDate);
    if (mode === "1800") target.setHours(18,0,0,0);
    else if (mode === "2015") target.setHours(20,15,0,0);
    else if (mode === "2200") target.setHours(22,0,0,0);
    else target.setHours(new Date().getHours(), new Date().getMinutes(), 0, 0);
    return target;
  }

  function modeIndex(programs, mode, selectedDate, customTarget) {
    const target = targetForMode(mode, selectedDate, customTarget);
    let i = programs.findIndex(p => new Date(p.start) <= target && target < new Date(p.end));
    if (i < 0) i = programs.findIndex(p => new Date(p.start) >= target);
    return i;
  }

  function pct(start, end, now = new Date()) {
    const a = new Date(start), b = new Date(end);
    const p = ((now - a) / (b - a)) * 100;
    return Math.max(0, Math.min(100, p));
  }

  function channelHeader(channel, logoPrefix="") {
    const fallback = logoPrefix + "logos/" + encodeURIComponent(channel.id) + ".png";

    const localLight = channel.logo_file_light ? logoPrefix + channel.logo_file_light : "";
    const localDark = channel.logo_file ? logoPrefix + channel.logo_file : "";
    const feedLight = channel.logo_light || channel.logo || "";
    const feedDark = channel.logo_dark || channel.logo || "";

    const rawLight = localLight || localDark || feedLight || feedDark || fallback;
    const rawDark = localDark || localLight || feedDark || feedLight || fallback;
    const lightLogo = channel.logo_normalized_light || rawLight;
    const darkLogo = channel.logo_normalized_dark || rawDark;

    function imageMarkup(themeClass, src, rawFallback) {
      const safeSrc = escapeHtml(src);
      const safeFallback = escapeHtml(rawFallback);
      const onerror =
        "if(this.dataset.fallback&&this.src!==this.dataset.fallback){this.src=this.dataset.fallback;this.dataset.fallback='';return;}" +
        "this.style.display='none';const f=this.parentElement.querySelector('.logo-fallback');if(f)f.style.display='block'";
      return '<img class="channel-logo ' + themeClass + ' channel-logo-normalized"' +
        ' src="' + safeSrc + '" data-fallback="' + safeFallback + '"' +
        ' alt="' + escapeHtml(channel.name) + '" loading="lazy" decoding="async" onerror="' + onerror + '">';
    }

    const lightImage = imageMarkup("channel-logo-light", lightLogo, rawLight);
    const darkImage = imageMarkup("channel-logo-dark", darkLogo, rawDark);

    return lightImage + darkImage +
      '<span class="channel-text-logo logo-fallback" style="display:none">' +
      escapeHtml(channel.name) + '</span>' +
      '<span class="channel-label">' + escapeHtml(channel.name) + '</span>';
  }

  function renderPrograms(channel, mode, selectedDate, customTarget, showProgressValue = true) {
    if (!channel.programs || channel.programs.length === 0) {
      const message = channel.data_message ||
        (channel.data_state === "source_unavailable"
          ? t("Programmdatenquellen derzeit nicht erreichbar")
          : t("Für diesen Sender liegen aktuell keine Programmdaten vor"));
      return '<div class="program unavailable" data-data-state="' +
        escapeHtml(channel.data_state || "no_programmes") + '">' +
        escapeHtml(t(message)) + '</div>';
    }

    const base = modeIndex(channel.programs, mode, selectedDate, customTarget);
    if (base < 0) {
      const message = channel.data_state === "ends_early"
        ? t("Die Programmdaten dieses Senders enden früher")
        : channel.data_state === "ended"
          ? t("Die Programmdaten dieses Senders sind abgelaufen")
          : t("Für diese Zeit keine Programmdaten verfügbar");
      return '<div class="program unavailable" data-data-state="' +
        escapeHtml(channel.data_state || "time_gap") + '">' +
        escapeHtml(t(message)) + '</div>';
    }

    const programs = channel.programs.slice(base, base + 7);
    const now = new Date();
    let currentMarked = false;

    return programs.map((program, index) => {
      const overlapsNow = mode === "now" &&
        new Date(program.start) <= now && now < new Date(program.end);
      const isCurrent = overlapsNow && !currentMarked;
      if (isCurrent) currentMarked = true;
      const rowClass = index === 0 ? " first" : (index === 1 ? " second" : "");

      const metaParts = [];
      if (program.subtitle) metaParts.push(program.subtitle);
      if (program.category) metaParts.push(program.category);
      const meta = metaParts.length
        ? '<div class="program-meta">' + escapeHtml(metaParts.join(" · ")) + '</div>'
        : "";

      const time = '<div class="program-time">' + fmt.format(new Date(program.start)) + '</div>';
      const timeMarkup = index === 0
        ? '<div class="program-time-wrapper">' + time + '</div>'
        : index === 1 ? '<div class="program-time-label-wrapper">' + time + '</div>' : time;
      return '<div class="program' + rowClass + (isCurrent ? ' current' : '') + '">' +
        '<button type="button" class="program-link" title="' + escapeHtml(program.title) +
        '" data-program-start="' + escapeHtml(program.start) + '">' +
        timeMarkup + '<div class="program-main"><strong>' + escapeHtml(program.title) + '</strong>' +
        meta + '</div></button>' +
        (isCurrent ? '<div class="progress-track"><div class="progress-fill" style="width:' +
          (showProgressValue ? pct(program.start, program.end) : 0) + '%"></div></div>' : '') + '</div>';
    }).join("");
  }

  function renderChannelCard(channel, mode, selectedDate, customTarget, logoPrefix="", showProgressValue = true) {
    return '<section class="channel-card" data-channel-id="' + escapeHtml(channel.id) + '">' +
      '<div class="channel-brand">' + channelHeader(channel, logoPrefix) + '</div>' +
      '<div class="programs">' + renderPrograms(channel, mode, selectedDate, customTarget, showProgressValue) + '</div>' +
      '</section>';
  }

  window.TVGuideCore = {
    fmt, dateFmt, startOfDay, dateKey, sameDay, targetForMode, modeIndex,
    pct, escapeHtml,
    channelHeader, renderPrograms, renderChannelCard
  };
})();
