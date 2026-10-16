import {translations} from './translations.js?v=native-20';
import {languageRegistry, normalizeLanguage} from './language-registry.js?v=native-1';
export function createI18n(root, getHass) {
  const languageSelect = root.querySelector?.('#settingLanguage');
  if (languageSelect) {
    languageSelect.replaceChildren(new Option('Automatisch · Home Assistant', 'auto'));
    languageSelect.options[0].dataset.i18n = 'Automatisch · Home Assistant';
    for (const [code, item] of Object.entries(languageRegistry)) {
      const option = new Option(item.name, code);
      option.dataset.i18n = item.name;
      languageSelect.append(option);
    }
  }
  let language = 'de';
  let translated = false;
  let countryLanguages = new Map();
  function supportedLanguage(value) { return normalizeLanguage(value); }
  function homeAssistantLanguage() {
    const hass = getHass();
    return hass?.locale?.language || hass?.language || '';
  }
  function resolve(options = {}) {
    if (options.language && options.language !== 'auto') return supportedLanguage(options.language);
    const profile = homeAssistantLanguage();
    if (profile) return supportedLanguage(profile);
    const installation = options.home_assistant || {};
    if (installation.language) return supportedLanguage(installation.language);
    const country = String(options.country || installation.country || 'de').toLowerCase();
    const registered = options.country_language || countryLanguages.get(country);
    if (registered) return supportedLanguage(registered);
    // A country cannot identify the user's language in multilingual regions.
    return supportedLanguage(navigator.language || 'en');
  }
  function t(message, values = {}, targetLanguage = language) {
    const selectedLanguage = targetLanguage === language ? language : supportedLanguage(targetLanguage);
    const translated = translations?.[selectedLanguage]?.[message] ||
      translations?.en?.[message] || String(message || '');
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
    if (!root.querySelectorAll) return;
    root.lang = language;
    for (const node of root.querySelectorAll('[data-i18n]')) node.textContent = t(node.dataset.i18n);
    for (const attribute of ['title', 'aria-label', 'placeholder']) {
      for (const node of root.querySelectorAll(`[data-i18n-${attribute}]`)) {
        node.setAttribute(attribute, t(node.getAttribute(`data-i18n-${attribute}`)));
      }
    }
    sortTranslatedOptions(root.querySelector('#settingCountry'));
  }
  function configure(options = {}) {
    if (Array.isArray(options.countries)) countryLanguages = new Map(options.countries.map(item => [item.code, item.language]));
    const next = resolve(options);
    const changed = next !== language;
    if (!changed && translated) return false;
    language = next;
    translateDocument();
    translated = true;
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
  const i18n = {t,configure,resolve,translateDocument,formatTime,formatDate,get language() {return language;}};
  configure();
  return i18n;
}
