const TV_GUIDE_PICKER_LOGO = "<svg xmlns=\"http://www.w3.org/2000/svg\" viewBox=\"0 0 250 100\" width=\"250\" height=\"100\"><title>TV Guide</title><g transform=\"translate(0,2) scale(.75)\"><rect x=\"12\" y=\"21\" width=\"104\" height=\"77\" rx=\"19\" fill=\"#25b9bf\"/><rect x=\"23\" y=\"32\" width=\"82\" height=\"54\" rx=\"10\" fill=\"#102d3e\"/><rect x=\"33\" y=\"42\" width=\"12\" height=\"7\" rx=\"3\" fill=\"#fff\"/><rect x=\"52\" y=\"42\" width=\"42\" height=\"7\" rx=\"3\" fill=\"#fff\"/><rect x=\"33\" y=\"56\" width=\"12\" height=\"7\" rx=\"3\" fill=\"#76e3d8\"/><rect x=\"52\" y=\"56\" width=\"32\" height=\"7\" rx=\"3\" fill=\"#76e3d8\"/><rect x=\"33\" y=\"70\" width=\"12\" height=\"7\" rx=\"3\" fill=\"#fff\" opacity=\".7\"/><rect x=\"52\" y=\"70\" width=\"37\" height=\"7\" rx=\"3\" fill=\"#fff\" opacity=\".7\"/><path d=\"M48 106h32\" stroke=\"#25b9bf\" stroke-width=\"9\" stroke-linecap=\"round\"/></g><text x=\"105\" y=\"60\" font-family=\"Segoe UI,Arial,sans-serif\" font-size=\"29\" font-weight=\"700\" fill=\"#31949b\">TV Guide</text></svg>";

const TV_GUIDE_CARD_TRANSLATIONS = {"da":{"TV Guide wird geladen …":"TV Guide indlæses …","TV Guide konnte nicht geladen werden.":"TV Guide kunne ikke indlæses.","TV Guide ist nicht installiert.":"TV Guide er ikke installeret.","TV Guide ist nicht gestartet.":"TV Guide er ikke startet.","Für TV Guide ist keine Ingress-Adresse verfügbar.":"Ingen ingress-adresse er tilgængelig for TV Guide.","TV-Guide-Karte konnte nicht aufgebaut werden.":"TV Guide-kortet kunne ikke oprettes.","TV-Guide-App wurde in Home Assistant nicht gefunden.":"TV Guide blev ikke fundet i Home Assistant."},"de":{"TV Guide wird geladen …":"TV Guide wird geladen …","TV Guide konnte nicht geladen werden.":"TV Guide konnte nicht geladen werden.","TV Guide ist nicht installiert.":"TV Guide ist nicht installiert.","TV Guide ist nicht gestartet.":"TV Guide ist nicht gestartet.","Für TV Guide ist keine Ingress-Adresse verfügbar.":"Für TV Guide ist keine Ingress-Adresse verfügbar.","TV-Guide-Karte konnte nicht aufgebaut werden.":"TV-Guide-Karte konnte nicht aufgebaut werden.","TV-Guide-App wurde in Home Assistant nicht gefunden.":"TV-Guide-App wurde in Home Assistant nicht gefunden."},"en":{"TV Guide wird geladen …":"Loading TV Guide …","TV Guide konnte nicht geladen werden.":"Could not load TV Guide.","TV Guide ist nicht installiert.":"TV Guide is not installed.","TV Guide ist nicht gestartet.":"TV Guide is not running.","Für TV Guide ist keine Ingress-Adresse verfügbar.":"No ingress address is available for TV Guide.","TV-Guide-Karte konnte nicht aufgebaut werden.":"Could not create the TV Guide card.","TV-Guide-App wurde in Home Assistant nicht gefunden.":"TV Guide was not found in Home Assistant."},"nl":{"TV Guide wird geladen …":"TV Guide laden …","TV Guide konnte nicht geladen werden.":"TV Guide kon niet worden geladen.","TV Guide ist nicht installiert.":"TV Guide is niet geïnstalleerd.","TV Guide ist nicht gestartet.":"TV Guide is niet gestart.","Für TV Guide ist keine Ingress-Adresse verfügbar.":"Geen ingress-adres beschikbaar voor TV Guide.","TV-Guide-Karte konnte nicht aufgebaut werden.":"De TV Guide-kaart kon niet worden gemaakt.","TV-Guide-App wurde in Home Assistant nicht gefunden.":"TV Guide is niet gevonden in Home Assistant."},"fr":{"TV Guide wird geladen …":"Chargement de TV Guide…","TV Guide konnte nicht geladen werden.":"Impossible de charger TV Guide.","TV Guide ist nicht installiert.":"TV Guide n’est pas installé.","TV Guide ist nicht gestartet.":"TV Guide n’est pas démarré.","Für TV Guide ist keine Ingress-Adresse verfügbar.":"Aucune adresse ingress disponible pour TV Guide.","TV-Guide-Karte konnte nicht aufgebaut werden.":"Impossible de créer la carte TV Guide.","TV-Guide-App wurde in Home Assistant nicht gefunden.":"TV Guide est introuvable dans Home Assistant."},"it":{"TV Guide wird geladen …":"Caricamento di TV Guide…","TV Guide konnte nicht geladen werden.":"Impossibile caricare TV Guide.","TV Guide ist nicht installiert.":"TV Guide non è installato.","TV Guide ist nicht gestartet.":"TV Guide non è avviato.","Für TV Guide ist keine Ingress-Adresse verfügbar.":"Nessun indirizzo ingress disponibile per TV Guide.","TV-Guide-Karte konnte nicht aufgebaut werden.":"Impossibile creare la scheda TV Guide.","TV-Guide-App wurde in Home Assistant nicht gefunden.":"TV Guide non è stato trovato in Home Assistant."},"nb":{"TV Guide wird geladen …":"Laster TV Guide …","TV Guide konnte nicht geladen werden.":"Kunne ikke laste TV Guide.","TV Guide ist nicht installiert.":"TV Guide er ikke installert.","TV Guide ist nicht gestartet.":"TV Guide er ikke startet.","Für TV Guide ist keine Ingress-Adresse verfügbar.":"Ingen ingress-adresse er tilgjengelig for TV Guide.","TV-Guide-Karte konnte nicht aufgebaut werden.":"Kunne ikke opprette TV Guide-kortet.","TV-Guide-App wurde in Home Assistant nicht gefunden.":"TV Guide ble ikke funnet i Home Assistant."},"sv":{"TV Guide wird geladen …":"Läser in TV Guide …","TV Guide konnte nicht geladen werden.":"TV Guide kunde inte läsas in.","TV Guide ist nicht installiert.":"TV Guide är inte installerad.","TV Guide ist nicht gestartet.":"TV Guide är inte startad.","Für TV Guide ist keine Ingress-Adresse verfügbar.":"Ingen Ingress-adress är tillgänglig för TV Guide.","TV-Guide-Karte konnte nicht aufgebaut werden.":"TV Guide-kortet kunde inte skapas.","TV-Guide-App wurde in Home Assistant nicht gefunden.":"TV Guide hittades inte i Home Assistant."}};

class TVGuideNativeCardEditor extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({mode:"open"});
    this._hass = null;
    this._config = {};
  }

  set hass(hass) {
    this._hass = hass;
    this._render();
  }

  setConfig(config) {
    this._config = {...(config || {})};
    this._render();
  }

  _changed(patch) {
    const config = {...this._config, ...patch};
    for (const [key, value] of Object.entries(config)) {
      if (value === "" || value === undefined || value === null) delete config[key];
    }
    this._config = config;
    this.dispatchEvent(new CustomEvent("config-changed", {
      detail:{config},
      bubbles:true,
      composed:true
    }));
  }

  _render() {
    if (!this.shadowRoot) return;
    const themes = Object.keys(this._hass?.themes?.themes || {}).sort((a,b) => a.localeCompare(b));
    const currentTheme = String(this._config?.theme || "");
    this.shadowRoot.innerHTML = `
      <style>
        :host { display:block; }
        .form { display:grid; gap:16px; padding:8px 0; }
        label { display:grid; gap:6px; color:var(--primary-text-color); font-size:14px; }
        select {
          width:100%; box-sizing:border-box; min-height:44px; padding:8px 10px;
          border:1px solid var(--divider-color); border-radius:8px;
          background:var(--card-background-color, var(--ha-card-background));
          color:var(--primary-text-color); font:inherit;
        }
        .hint { color:var(--secondary-text-color); font-size:12px; line-height:1.4; }
      </style>
      <div class="form">
        <label>
          <span>Theme</span>
          <select id="theme">
            <option value="">Home Assistant / Dashboard</option>
            ${themes.map(name => `<option value="${name.replace(/&/g,"&amp;").replace(/"/g,"&quot;")}"${name === currentTheme ? " selected" : ""}>${name.replace(/&/g,"&amp;").replace(/</g,"&lt;")}</option>`).join("")}
          </select>
          <span class="hint">Uses the selected Home Assistant theme only for this TV Guide card.</span>
        </label>
      </div>
    `;
    this.shadowRoot.getElementById("theme")?.addEventListener("change", (event) => {
      this._changed({theme:event.target.value});
    });
  }
}

if (!customElements.get("tv-guide-native-card-editor")) {
  customElements.define("tv-guide-native-card-editor", TVGuideNativeCardEditor);
}

class TVGuideNativeCard extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({mode:"open"});
    this._config = {height: 1000};
    this._hass = null;
    this._started = false;
    this._iframe = null;
    this._themeProperties = new Set();
    this._themeFingerprint = "";
    this._lastThemeMessageSignature = "";
    this._themeReadyListening = false;
    this._themeObserver = null;
    this._themeSyncFrame = null;
    this._themeReadyHandler = (event) => {
      if (
        event.origin === window.location.origin &&
        event.source === this._iframe?.contentWindow
      ) {
        if (event.data?.type === "tv-guide-native-request") void this._handleNativeRequest(event);
        else if (event.data?.type === "tv-guide-theme-request") this._sendThemeToIframe(true);
        else if (event.data?.type === "tv-guide-theme-ready") this._iframe.style.opacity = "1";
      }
    };
  }

  _attachThemeReadyListener() {
    if (this._themeReadyListening) return;
    window.addEventListener("message", this._themeReadyHandler);
    this._themeReadyListening = true;
  }

  _detachThemeReadyListener() {
    if (!this._themeReadyListening) return;
    window.removeEventListener("message", this._themeReadyHandler);
    this._themeReadyListening = false;
  }

  _scheduleThemeSync() {
    if (!this.isConnected || !this._iframe || this._themeSyncFrame !== null) return;
    this._themeSyncFrame = window.requestAnimationFrame(() => {
      this._themeSyncFrame = null;
      if (this.isConnected) this._sendThemeToIframe();
    });
  }

  _watchInheritedTheme() {
    this._themeObserver?.disconnect();
    this._themeObserver = new MutationObserver(() => this._scheduleThemeSync());
    // Dashboard themes can change on a shadow host without changing hass.themes.
    for (let node = this; node; node = node.parentNode || node.host) {
      if (node.nodeType === 1) {
        this._themeObserver.observe(node, {attributes:true, attributeFilter:["class", "style"]});
      }
    }
  }

  _themeMessage() {
    const style = getComputedStyle(this);
    const names = [
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
    const vars = {};
    for (const name of names) {
      const value = style.getPropertyValue(name).trim();
      if (value) vars[name] = value;
    }
    const background = vars["--primary-background-color"] || "";
    let darkMode = Boolean(this._hass?.themes?.darkMode);
    const hex = background.match(/^#([0-9a-f]{3}|[0-9a-f]{6})$/i);
    const rgb = background.match(/rgba?\((\d+)\D+(\d+)\D+(\d+)/i);
    let channels = null;
    if (hex) {
      const expanded = hex[1].length === 3
        ? [...hex[1]].map(character => character + character).join("") : hex[1];
      channels = [
        parseInt(expanded.slice(0, 2), 16),
        parseInt(expanded.slice(2, 4), 16),
        parseInt(expanded.slice(4, 6), 16)
      ];
    } else if (rgb) {
      channels = [Number(rgb[1]), Number(rgb[2]), Number(rgb[3])];
    }
    if (channels) {
      const brightness = (channels[0] * 299 + channels[1] * 587 + channels[2] * 114) / 1000;
      darkMode = brightness < 128;
    }
    return {
      type:"tv-guide-theme",
      vars,
      darkMode
    };
  }

  _sendThemeToIframe(force = false) {
    const target = this._iframe?.contentWindow;
    if (!target) return;
    const message = this._themeMessage();
    const signature = JSON.stringify(message);
    if (!force && signature === this._lastThemeMessageSignature) return;
    this._lastThemeMessageSignature = signature;
    target.postMessage(message, window.location.origin);
  }

  static getConfigElement() {
    return document.createElement("tv-guide-native-card-editor");
  }

  _t(message) {
    const language = String(this._hass?.locale?.language || this._hass?.language || "en").toLowerCase().replace("_", "-").split("-")[0];
    return (TV_GUIDE_CARD_TRANSLATIONS[language === "no" ? "nb" : language] || TV_GUIDE_CARD_TRANSLATIONS.en)[message] || message;
  }

  static getStubConfig() {
    return {height:1000};
  }

  getGridOptions() {
    return {
      columns:"full",
      min_columns:6
    };
  }

  setConfig(config) {
    const height = Number(config?.height);
    this._config = {
      ...config,
      height:Number.isFinite(height) && height > 0
        ? Math.max(240, Math.min(2200, height)) : 1000,
      theme:String(config?.theme || "").trim()
    };
    this._applyConfiguredTheme();
    this._renderShell();
    this._scheduleThemeSync();
  }

  _applyConfiguredTheme() {
    const themeName = String(this._config?.theme || "").trim();
    const darkMode = Boolean(this._hass?.themes?.darkMode);
    const themes = this._hass?.themes?.themes || {};
    const selectedTheme = themeName ? themes[themeName] : null;
    const inheritedThemeName = String(this._hass?.themes?.theme || "");
    const inheritedTheme = inheritedThemeName ? themes[inheritedThemeName] : null;
    const sourceTheme = themeName ? selectedTheme : inheritedTheme;
    const fingerprint = JSON.stringify([
      themeName || "__inherit__",
      inheritedThemeName,
      darkMode,
      sourceTheme || null
    ]);

    if (fingerprint === this._themeFingerprint) return false;
    this._themeFingerprint = fingerprint;

    for (const property of this._themeProperties) this.style.removeProperty(property);
    this._themeProperties.clear();

    if (!themeName || !selectedTheme || typeof selectedTheme !== "object") return true;

    const modeValues = selectedTheme.modes?.[darkMode ? "dark" : "light"] || {};
    const values = {...selectedTheme, ...modeValues};
    delete values.modes;

    for (const [rawName, rawValue] of Object.entries(values)) {
      if (rawValue === undefined || rawValue === null || typeof rawValue === "object") continue;
      const property = rawName.startsWith("--") ? rawName : "--" + rawName;
      this.style.setProperty(property, String(rawValue));
      this._themeProperties.add(property);
    }
    return true;
  }

  set hass(hass) {
    this._hass = hass;
    this._applyConfiguredTheme();
    this._scheduleThemeSync();
    const loading = this.shadowRoot?.querySelector(".loading");
    if (loading && !this._started) loading.textContent = this._t("TV Guide wird geladen …");
    if (this.isConnected && !this._started) this._start();
  }

  _isCardPicker() {
    let node = this;
    while (node) {
      if (node.localName === "hui-card-picker") return true;
      node = node.parentNode || node.host;
    }
    return false;
  }

  connectedCallback() {
    this._attachThemeReadyListener();
    this._watchInheritedTheme();
    this._renderShell();
    if (this._hass && !this._started) this._start();
  }

  disconnectedCallback() {
    this._detachThemeReadyListener();
    this._themeObserver?.disconnect();
    this._themeObserver = null;
    if (this._themeSyncFrame !== null) window.cancelAnimationFrame(this._themeSyncFrame);
    this._themeSyncFrame = null;
    this._started = false;
    this._iframe?.remove();
    this._iframe = null;
  }

  getCardSize() {
    return Math.max(10, Math.ceil(this._config.height / 50));
  }

  _renderShell(message = this._t("TV Guide wird geladen …")) {
    if (!this.shadowRoot) return;
    if (this._isCardPicker()) {
      this.shadowRoot.innerHTML = `
        <style>
          :host { display:block; width:100%; }
          .brand { display:flex; align-items:center; justify-content:center;
            min-height:180px; padding:16px; box-sizing:border-box; }
          svg { display:block; width:250px; max-width:100%; height:auto; }
        </style>
        <div class="brand" role="img" aria-label="TV Guide">${TV_GUIDE_PICKER_LOGO}</div>
      `;
      return;
    }
    const iframe = this._iframe;
    if (iframe && iframe.isConnected) {
      iframe.style.height = this._config.height + "px";
      return;
    }

    this.shadowRoot.innerHTML = `
      <style>
        :host {
          display:block;
          width:100%;
        }
        ha-card {
          display:block;
          width:100%;
          padding:0;
          margin:0;
          overflow:hidden;
          background:var(--primary-background-color);
          box-shadow:none;
          border:0;
        }
        .loading {
          box-sizing:border-box;
          min-height:180px;
          display:flex;
          align-items:center;
          justify-content:center;
          padding:24px;
          color:var(--secondary-text-color);
          font:var(--paper-font-body1_-_font,inherit);
        }
        iframe {
          display:block;
          width:100%;
          border:0;
          background:var(--primary-background-color);
        }
      </style>
      <ha-card>
        <div class="loading">${message}</div>
      </ha-card>
    `;
  }

  async _response(service, service_data={}) {
    const result = await this._hass.callWS({type:"call_service",domain:"tv_guide",service,service_data,return_response:true});
    if (!result?.response) throw new Error("TV Guide response unavailable");
    return result.response;
  }
  async _handleNativeRequest(event) {
    const request = event.data;
    if (!this.isConnected || !this._hass || typeof request.id !== "string" || request.id.length > 80) return;
    const frame = this._iframe;
    try {
      const endpoint = request.endpoint;
      const method = request.method;
      const body = request.body || {};
      let response;
      if (this._hass.services?.tv_guide?.native_request && ["guide","channels","personal-channels","channel-settings","settings","status","refresh"].includes(endpoint)) {
        response = await this._response("native_request",{endpoint,method,...(method === "POST" ? {body} : {})});
      } else if (method === "GET" && endpoint === "guide") response = await this._response("get_native_guide", request.at ? {at:request.at} : {});
      else if (method === "GET" && endpoint === "personal-channels") response = await this._response("get_native_channels");
      else if (method === "GET" && endpoint === "settings") response = await this._response("get_ui_settings");
      else if (method === "POST" && endpoint === "settings") {
        const allowed = ["country","language","default_view","columns_desktop","max_channels","theme_mode","refresh_minutes","notification_service"];
        response = await this._response("set_ui_settings", {options:Object.fromEntries(allowed.filter(key => Object.hasOwn(body,key)).map(key => [key,body[key]]))});
      } else if (method === "POST" && endpoint === "personal-channels") {
        await this._hass.callService("tv_guide","set_channels",{channels:body.reset ? [] : body.order});
        response = {ok:true};
      } else if (["bookmarks","reminders"].includes(endpoint) && ["GET","POST"].includes(method)) {
        if (method === "POST") {
          if (body.action === "remove") {
            await this._hass.callService("tv_guide","remove_saved_programme",{id:body.id,kind:endpoint === "bookmarks" ? "programme" : "reminder"});
          } else if (body.action === "upsert") {
            const payload = {id:body.id,title:String(body.title || "").slice(0,240),channel:String(body.channel || "").slice(0,120),channel_id:body.channelId,start:body.start,end:body.end};
            if (endpoint === "reminders") {
              payload.minutes = body.minutes;
              if (body.language) payload.language = body.language;
            }
            await this._hass.callService("tv_guide",endpoint === "bookmarks" ? "save_bookmark" : "save_reminder",payload);
          } else throw new Error("Invalid saved-programme operation");
        }
        response = {ok:true,...await this._response("get_saved_programmes")};
      } else if (method === "GET" && endpoint === "notification-services") {
        const mobile = Object.keys(this._hass.services?.notify || {}).filter(name => name.startsWith("mobile_app_")).map(name => {
          const device = name.slice(11).replaceAll("_"," ");
          return {service:"notify."+name,label:"Mobilgerät · "+(device ? device[0].toUpperCase()+device.slice(1) : name),type:"mobile_app"};
        }).sort((a,b) => a.label.localeCompare(b.label));
        response = {services:[{service:"persistent_notification.create",label:"Home Assistant",type:"home_assistant"},...mobile]};
      } else if (method === "POST" && endpoint === "test-notification" && body.test === true) {
        const settings = await this._response("get_ui_settings");
        const [domain, service] = settings.notification_service.split(".");
        if (!(domain === "notify" || (domain === "persistent_notification" && service === "create"))) throw new Error("Invalid notification destination");
        const t = frame.contentWindow.TVGuideI18n?.t || (message => message);
        const time = new Intl.DateTimeFormat(body.language || "en",{hour:"2-digit",minute:"2-digit",hour12:false,...(this._hass.config?.time_zone ? {timeZone:this._hass.config.time_zone} : {})}).format(new Date(Date.now()+60000));
        await this._hass.callService(domain,service,{title:t("TV Guide – Erinnerung"),message:t("{channel}: „{title}“ beginnt um {time} Uhr.",{channel:"TV Guide",title:t("Testbenachrichtigung"),time})});
        response = {ok:true,service:settings.notification_service};
      } else throw new Error("Unsupported native TV Guide operation");
      if (this.isConnected && this._iframe === frame) event.source.postMessage({type:"tv-guide-native-response",id:request.id,response},window.location.origin);
    } catch (error) {
      if (this.isConnected && this._iframe === frame) event.source.postMessage({type:"tv-guide-native-response",id:request.id,error:error.message || String(error)},window.location.origin);
    }
  }
  _start() {
    if (!this.isConnected || this._started || !this._hass || this._isCardPicker()) return;
    this._started = true;
    this._renderShell();
    const card = this.shadowRoot.querySelector("ha-card");
    if (!card) return;
    card.replaceChildren();
    const iframe = document.createElement("iframe");
    const url = new URL("/tv_guide/frontend/app/index.html",window.location.origin);
    url.searchParams.set("tv_guide_card","1");
    url.searchParams.set("tv_guide_theme",this._config.theme || "__dashboard__");
    this._lastThemeMessageSignature = "";
    iframe.title = "TV Guide";
    iframe.src = url.toString();
    iframe.style.height = this._config.height+"px";
    iframe.style.opacity = "0";
    iframe.setAttribute("allow","clipboard-read; clipboard-write");
    this._iframe = iframe;
    iframe.addEventListener("load",() => {
      if (this._iframe !== iframe || !this.isConnected) return;
      this._sendThemeToIframe(true);
      // Show a readable native error even if the inner data request fails.
      iframe.style.opacity = "1";
    });
    card.appendChild(iframe);
  }
}
if (!customElements.get("tv-guide-native-card")) customElements.define("tv-guide-native-card",TVGuideNativeCard);
window.customCards = window.customCards || [];
if (!window.customCards.some(card => card.type === "tv-guide-native-card")) window.customCards.push({type:"tv-guide-native-card",name:"TV Guide Native",description:"Original TV Guide presentation using native Home Assistant data",preview:true});
