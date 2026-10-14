(function (root) {
  const supported = ['da', 'de', 'en', 'nl', 'fr', 'it', 'nb', 'sv'];
  let language = 'de';
  function baseLanguage(value) {
    const code = String(value || '').toLowerCase().replace('_', '-').split('-')[0];
    return code === 'no' ? 'nb' : code;
  }
  function supportedLanguage(value) {
    const code = baseLanguage(value);
    return supported.includes(code) ? code : 'en';
  }
  function homeAssistantLanguage() {
    try {
      let frame = root;
      for (let depth = 0; depth < 5; depth++) {
        const hass = frame.document?.querySelector('home-assistant')?.hass || frame.hass;
        const value = hass?.locale?.language || hass?.language ||
          hass?.internationalizationContext?.locale?.language;
        if (value) return value;
        if (frame.parent === frame) break;
        frame = frame.parent;
      }
    } catch {}
    return '';
  }
  function resolve(options = {}) {
    if (options.language && options.language !== 'auto') return supportedLanguage(options.language);
    const profile = homeAssistantLanguage();
    if (profile) return supportedLanguage(profile);
    const installation = options.home_assistant || {};
    if (installation.language) return supportedLanguage(installation.language);
    const country = String(installation.country || options.country || 'de').toLowerCase();
    if (country === 'de' || country === 'at') return 'de';
    if (country === 'nl') return 'nl';
    if (country === 'no') return 'nb';
    if (country === 'fr') return 'fr';
    if (country === 'dk') return 'da';
    if (country === 'se') return 'sv';
    if (country === 'gb') return 'en';
    // A country cannot identify the user's language in multilingual regions.
    return supportedLanguage(root.navigator?.language || 'en');
  }
  function t(message, values = {}) {
    const translated = root.TVGuideTranslations?.[language]?.[message] ||
      root.TVGuideTranslations?.en?.[message] || String(message || '');
    return translated.replace(/\{(\w+)\}/g, (token, key) => Object.hasOwn(values, key) ? String(values[key]) : token);
  }
  function sortTranslatedOptions(select) {
    if (!select?.options) return;
    const selected = select.value;
    const collator = new Intl.Collator(language, {usage:'sort', sensitivity:'base'});
    const options = Array.from(select.options);
    options.sort((left, right) => collator.compare(left.textContent, right.textContent));
    for (const option of options) select.appendChild(option);
    select.value = selected;
  }
  function translateDocument() {
    if (!root.document?.querySelectorAll) return;
    root.document.documentElement.lang = language;
    for (const node of root.document.querySelectorAll('[data-i18n]')) node.textContent = t(node.dataset.i18n);
    for (const attribute of ['title', 'aria-label', 'placeholder']) {
      for (const node of root.document.querySelectorAll(`[data-i18n-${attribute}]`)) {
        node.setAttribute(attribute, t(node.getAttribute(`data-i18n-${attribute}`)));
      }
    }
    sortTranslatedOptions(root.document.getElementById?.('settingCountry'));
  }
  function configure(options = {}) {
    const next = resolve(options);
    const changed = next !== language;
    language = next;
    translateDocument();
    return changed;
  }
  const formatters = new Map();
  function formatter(kind) {
    const key = language + ':' + kind;
    if (!formatters.has(key)) {
      formatters.set(key, new Intl.DateTimeFormat(language, kind === 'time'
        ? {hour:'2-digit', minute:'2-digit', hour12:false}
        : {weekday:'short',day:'2-digit',month:'2-digit'}));
    }
    return formatters.get(key);
  }
  function formatTime(value) { return formatter('time').format(value); }
  function formatDate(value) { return formatter('date').format(value); }
  root.TVGuideI18n = {t,configure,resolve,translateDocument,formatTime,formatDate,get language() {return language;}};
  configure();
})(globalThis);
