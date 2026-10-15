import {createGuideApp} from './app/app.js?v=native-2';
import {viewMarkup, viewStyles} from './app/view-template.js?v=native-2';

let fontsRegistered = false;
function registerGuideFonts() {
  if (fontsRegistered) return;
  fontsRegistered = true;
  for (const [weight,file] of [['400','Regular'],['500','SemiBold']]) {
    const face=new FontFace('Source Sans Pro', `url(/tv_guide/frontend/app/fonts/SourceSansPro-${file}.ttf)`, {weight});
    document.fonts.add(face);
    face.load().catch(()=>{});
  }
}

const TV_GUIDE_PICKER_LOGO = "<svg xmlns=\"http://www.w3.org/2000/svg\" viewBox=\"0 0 250 100\" width=\"250\" height=\"100\"><title>TV Guide</title><g transform=\"translate(0,2) scale(.75)\"><rect x=\"12\" y=\"21\" width=\"104\" height=\"77\" rx=\"19\" fill=\"#25b9bf\"/><rect x=\"23\" y=\"32\" width=\"82\" height=\"54\" rx=\"10\" fill=\"#102d3e\"/><rect x=\"33\" y=\"42\" width=\"12\" height=\"7\" rx=\"3\" fill=\"#fff\"/><rect x=\"52\" y=\"42\" width=\"42\" height=\"7\" rx=\"3\" fill=\"#fff\"/><rect x=\"33\" y=\"56\" width=\"12\" height=\"7\" rx=\"3\" fill=\"#76e3d8\"/><rect x=\"52\" y=\"56\" width=\"32\" height=\"7\" rx=\"3\" fill=\"#76e3d8\"/><rect x=\"33\" y=\"70\" width=\"12\" height=\"7\" rx=\"3\" fill=\"#fff\" opacity=\".7\"/><rect x=\"52\" y=\"70\" width=\"37\" height=\"7\" rx=\"3\" fill=\"#fff\" opacity=\".7\"/><path d=\"M48 106h32\" stroke=\"#25b9bf\" stroke-width=\"9\" stroke-linecap=\"round\"/></g><text x=\"105\" y=\"60\" font-family=\"Segoe UI,Arial,sans-serif\" font-size=\"29\" font-weight=\"700\" fill=\"#31949b\">TV Guide</text></svg>";

class TVGuideCardEditor extends HTMLElement {
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
    const themesKey = JSON.stringify(themes);
    const select = this.shadowRoot.getElementById("theme");
    if (select && this._themesKey === themesKey) {
      const value = themes.includes(currentTheme) ? currentTheme : "";
      if (select.value !== value) select.value = value;
      return;
    }
    this._themesKey = themesKey;
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

if (!customElements.get("tv-guide-card-editor")) {
  customElements.define("tv-guide-card-editor", TVGuideCardEditor);
}

class TVGuideCard extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({mode:"open"});
    this._config = {height: 1000};
    this._hass = null;
    this._started = false;
    this._app = null;
    this._pending = new Set();
    this._generation = 0;
    this._themeProperties = new Set();
    this._themeFingerprint = "";
    this._themeObserver = null;
    this._themeSyncFrame = null;
    this._lastViewTheme = "";
    this._renderShell();
  }

  _scheduleThemeSync() {
    if (!this.isConnected || !this._app || this._themeSyncFrame !== null) return;
    this._themeSyncFrame = window.requestAnimationFrame(() => {
      this._themeSyncFrame = null;
      if (!this.isConnected) return;
      const signature = this._viewThemeSignature();
      if (signature === this._lastViewTheme) return;
      this._lastViewTheme = signature;
      this._app.updateTheme();
    });
  }

  _viewThemeSignature() {
    return JSON.stringify([this._themeState(), this._hass?.locale?.language || this._hass?.language || ""]);
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

  _themeState() {
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
      vars,
      darkMode
    };
  }

  static getConfigElement() {
    return document.createElement("tv-guide-card-editor");
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
    this._watchInheritedTheme();
    this._renderShell();
    if (this._app) this._app.resume();
    else if (this._hass && !this._started) this._start();
  }

  disconnectedCallback() {
    this._themeObserver?.disconnect();
    this._themeObserver = null;
    if (this._themeSyncFrame !== null) window.cancelAnimationFrame(this._themeSyncFrame);
    this._themeSyncFrame = null;
    this._app?.suspend();
    ++this._generation;
    for (const pending of this._pending) {
      window.clearTimeout(pending.timer);
      pending.reject(new Error("Card closed"));
    }
    this._pending.clear();
  }

  getCardSize() {
    return Math.max(10, Math.ceil(this._config.height / 50));
  }

  _renderShell() {
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
    const existing = this.shadowRoot.querySelector('.guide-root');
    if (existing) { existing.style.height=this._config.height+'px'; return; }
    registerGuideFonts();
    this.shadowRoot.innerHTML = `<style>${viewStyles}</style><ha-card><div class="guide-root">${viewMarkup}</div></ha-card>`;
    this.shadowRoot.querySelector('.guide-root').style.height=this._config.height+'px';
  }

  async _request(request) {
    if (!this.isConnected || !this._hass) throw new Error("Card closed");
    const generation=this._generation;
    return new Promise((resolve,reject)=>{
      const pending={reject,timer:window.setTimeout(()=>{
        this._pending.delete(pending); reject(new Error("Home Assistant request timed out"));
      },15000)};
      this._pending.add(pending);
      this._dispatchGuideRequest(request).then(response=>{
        if (!this.isConnected || generation!==this._generation) throw new Error("Card closed");
        resolve(response);
      }).catch(reject).finally(()=>{
        window.clearTimeout(pending.timer); this._pending.delete(pending);
      });
    });
  }

  async _response(service, service_data={}) {
    const result = await this._hass.callWS({type:"call_service",domain:"tv_guide",service,service_data,return_response:true});
    if (!result?.response) throw new Error("TV Guide response unavailable");
    return result.response;
  }
  async _dispatchGuideRequest(request) {
      const endpoint = request.endpoint;
      const method = request.method;
      const body = request.body || {};
      let response;
      if (endpoint === "preparation" && ["GET","POST"].includes(method)) {
        response = await this._response(method === "POST" ? "retry_preparation" : "get_preparation_status");
      } else if (this._hass.services?.tv_guide?.guide_request && ["guide","channels","personal-channels","channel-settings","settings","status","refresh"].includes(endpoint)) {
        response = await this._response("guide_request",{endpoint,method,...(method === "POST" || (endpoint === "guide" && (body.preview === true || typeof body.known_revision === "string")) ? {body} : {})});
      } else if (method === "GET" && endpoint === "guide") response = await this._response("get_guide", request.at ? {at:request.at} : {});
      else if (method === "GET" && endpoint === "personal-channels") response = await this._response("get_personal_channels");
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
        const t = this._app?.i18n.t || (message => message);
        const time = new Intl.DateTimeFormat(body.language || "en",{hour:"2-digit",minute:"2-digit",hour12:false,...(this._hass.config?.time_zone ? {timeZone:this._hass.config.time_zone} : {})}).format(new Date(Date.now()+60000));
        await this._hass.callService(domain,service,{title:t("TV Guide – Erinnerung"),message:t("{channel}: „{title}“ beginnt um {time} Uhr.",{channel:"TV Guide",title:t("Testbenachrichtigung"),time})});
        response = {ok:true,service:settings.notification_service};
      } else throw new Error("Unsupported TV Guide operation");
      return response;
  }
  _start() {
    if (!this.isConnected || this._started || !this._hass || this._isCardPicker()) return;
    this._started = true;
    this._renderShell();
    this._lastViewTheme = this._viewThemeSignature();
    this._app = createGuideApp({
      root:this.shadowRoot.querySelector('.guide-root'),
      request:request=>this._request(request),
      getHass:()=>this._hass,
      getTheme:()=>this._themeState()
    });
  }
}
if (!customElements.get("tv-guide-card")) customElements.define("tv-guide-card",TVGuideCard);
window.customCards = window.customCards || [];
if (!window.customCards.some(card => card.type === "tv-guide-card")) window.customCards.push({type:"tv-guide-card",name:"TV Guide",description:"TV programme guide for Home Assistant",preview:true});
