/* Native TV Guide card. Uses only the authenticated Home Assistant connection. */
const TVG_TEXT = {
  de: {programme:"Programm", bookmarks:"Merkliste", reminders:"Erinnerungen", channels:"Meine Sender", refresh:"Aktualisieren", now:"Jetzt", earlier:"Früher", later:"Später", all:"Alle Sender", save:"Speichern", bookmark:"Merken", remind:"Erinnern", remove:"Entfernen", empty:"Keine Sendungen in diesem Zeitraum.", loading:"Wird geladen …", saved:"Gespeichert", sent:"Zugestellt", missing:"Kein EPG verfügbar. Bitte eine Quelle in TV Guide konfigurieren und erneut laden.", limit:"Maximal 500 Sendungen. Bitte einen Sender oder einen kürzeren Zeitraum wählen.", unavailable:"Kein EPG", selection:"Sender auswählen und mit ↑ / ↓ sortieren (max. 200). Eine leere Auswahl zeigt alle Sender.", savedEmpty:"Keine gespeicherten Sendungen.", minutes:"Minuten vorher", failed:"Aktion fehlgeschlagen", title:"TV Guide", hours:"Stunden"},
  en: {programme:"Schedule", bookmarks:"Bookmarks", reminders:"Reminders", channels:"My channels", refresh:"Refresh", now:"Now", earlier:"Earlier", later:"Later", all:"All channels", save:"Save", bookmark:"Bookmark", remind:"Remind", remove:"Remove", empty:"No programmes in this time range.", loading:"Loading …", saved:"Saved", sent:"Delivered", missing:"No EPG available. Configure a source in TV Guide and retry.", limit:"Maximum 500 programmes. Choose a channel or a shorter interval.", unavailable:"No EPG", selection:"Choose channels and order with ↑ / ↓ (max. 200). An empty selection shows all channels.", savedEmpty:"No saved programmes.", minutes:"minutes before", failed:"Action failed", title:"TV Guide", hours:"hours"},
};
const tvgEscape = value => String(value ?? "").replace(/[&<>"']/g, ch => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[ch]));

class TVGuideNativeCard extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({mode:"open"});
    this._tab = "programme";
    this._channels = [];
    this._selection = [];
    this._programmes = [];
    this._saved = {bookmarks:[], reminders:[]};
    this._start = Date.now();
    this._hours = 3;
    this._channel = "";
    this._busy = false;
    this._loaded = false;
  }
  setConfig(config) {
    this._config = {...config};
    this._render();
  }
  static getStubConfig() { return {type:"custom:tv-guide-native-card"}; }
  getCardSize() { return 8; }
  set hass(value) {
    const reconnect = this._hass && this._hass.connection !== value.connection;
    const languageChanged = this._hass?.language !== value.language;
    this._hass = value;
    if (reconnect) this._loaded = false;
    if (this.isConnected && !this._loaded && !this._busy) void this._load();
    else if (languageChanged) this._render();
  }
  connectedCallback() {
    if (this._hass && !this._busy) void this._load();
  }
  // No timers or subscriptions to leak on removal. In-flight reads cannot trigger writes.
  disconnectedCallback() { this._loaded = false; }
  get _t() { return TVG_TEXT[this._hass?.language?.split("-")[0]] || TVG_TEXT.en; }
  async _response(service, data = {}) {
    const result = await this._hass.callWS({type:"call_service", domain:"tv_guide", service, service_data:data, return_response:true});
    if (!result?.response) throw new Error(this._t.failed);
    return result.response;
  }
  async _load() {
    if (this._busy || !this._hass) return;
    this._busy = true;
    this._error = "";
    this._render();
    try {
      // Lists remain usable even in bridge-only mode or when no EPG is loaded.
      this._saved = await this._response("get_saved_programmes");
      try {
        const catalogue = await this._response("get_channels");
        this._channels = catalogue.channels;
        this._selection = this._channels.filter(item => item.selected).map(item => item.id);
        if (this._channel && !this._channels.some(item => item.selected && item.id === this._channel)) this._channel = "";
        const records = await this._response("get_programmes", {
          start:new Date(this._start).toISOString(),
          end:new Date(this._start + this._hours * 3600000).toISOString(),
          channel_id:this._channel, limit:500,
        });
        this._programmes = records.programmes;
        this._truncated = records.truncated;
        this._epgError = "";
      } catch (error) {
        this._programmes = [];
        this._channels = [];
        this._selection = [];
        this._epgError = `${this._t.missing} (${error.message || String(error)})`;
      }
      this._loaded = true;
    } catch (error) { this._error = error.message || String(error); }
    finally { this._busy = false; this._render(); }
  }
  _time(value) {
    return new Intl.DateTimeFormat(this._hass?.locale?.language || this._hass?.language || "en", {
      timeZone:this._hass?.config?.time_zone || "UTC", month:"short", day:"numeric", hour:"2-digit", minute:"2-digit",
    }).format(new Date(value));
  }
  async _action(service, data) {
    if (this._busy) return;
    this._busy = true;
    this._error = "";
    this._render();
    try {
      await this._hass.callService("tv_guide", service, data);
      this._busy = false;
      await this._load();
    } catch (error) {
      this._busy = false;
      this._error = error.message || String(error);
      this._render();
    }
  }
  _programmeRows(records, kind) {
    const t = this._t;
    return records.map((item, index) => {
      const bookmark = this._saved.bookmarks.some(saved => saved.id === item.id);
      const reminder = this._saved.reminders.find(saved => saved.id === item.id);
      const end = item.stop || item.end;
      const future = new Date(item.start).getTime() > Date.now();
      const active = new Date(end).getTime() > Date.now();
      return `<article><div class="meta">${tvgEscape(item.channel_name || item.channel)} · ${tvgEscape(this._time(item.start))} – ${tvgEscape(this._time(end))}</div>
        <strong>${tvgEscape(item.title)}</strong>
        ${item.description ? `<details><summary>Info</summary><p>${tvgEscape(item.description)}</p></details>` : ""}
        <div class="actions">${kind ? `<button data-remove="${index}" data-kind="${kind}">${t.remove}</button>${kind === "reminders" ? `<span>${item.minutes} ${t.minutes}${item.sent ? ` · ${t.sent}` : ""}</span>` : ""}` : `
        <button data-bookmark="${index}" ${!active || bookmark ? "disabled" : ""}>${bookmark ? "✓ " : ""}${t.bookmark}</button>
        <select aria-label="${t.remind}" id="minutes-${index}" ${!future || reminder ? "disabled" : ""}>${[5,10,15,30].map(n => `<option value="${n}" ${n === 10 ? "selected" : ""}>${n} ${t.minutes}</option>`).join("")}</select>
        <button data-remind="${index}" ${!future || reminder ? "disabled" : ""}>${reminder ? "✓ " : ""}${t.remind}</button>`}</div></article>`;
    }).join("") || `<p>${kind ? t.savedEmpty : t.empty}</p>`;
  }
  _render() {
    if (!this._config || !this.shadowRoot) return;
    const t = this._t;
    const disabled = this._busy ? "disabled" : "";
    let content = "";
    if (this._tab === "programme") {
      content = `<div class="toolbar"><button id="earlier">← ${t.earlier}</button><button id="now">${t.now}</button><button id="later">${t.later} →</button>
        <select id="hours" aria-label="${t.hours}">${[3,6,12,24].map(n => `<option value="${n}" ${this._hours === n ? "selected" : ""}>${n} ${t.hours}</option>`).join("")}</select>
        <select id="channel" aria-label="${t.channels}"><option value="">${t.all}</option>${this._channels.filter(item => item.selected).map(item => `<option value="${tvgEscape(item.id)}" ${this._channel === item.id ? "selected" : ""}>${tvgEscape(item.name)}</option>`).join("")}</select></div>
        <p class="meta">${tvgEscape(this._time(this._start))} – ${tvgEscape(this._time(this._start + this._hours * 3600000))} (${tvgEscape(this._hass?.config?.time_zone || "UTC")})</p>
        ${this._epgError ? `<p role="status">${tvgEscape(this._epgError)}</p>` : this._programmeRows(this._programmes)}
        ${this._truncated && !this._epgError ? `<p role="status">${t.limit}</p>` : ""}`;
    } else if (this._tab === "channels") {
      const channels = [...this._channels].sort((a,b) => {
        const rank = id => {const i = this._selection.indexOf(id); return i < 0 ? Infinity : i;};
        return rank(a.id) - rank(b.id);
      });
      content = `<p>${t.selection}</p><div class="actions"><button id="save-channels" ${!this._channels.length ? "disabled" : ""}>${t.save}</button><button id="all-channels" ${!this._channels.length ? "disabled" : ""}>${t.all}</button></div>
        ${this._epgError ? `<p>${tvgEscape(this._epgError)}</p>` : ""}
        ${channels.map(item => `<div class="station"><label><input type="checkbox" data-channel="${tvgEscape(item.id)}" ${this._selection.includes(item.id) ? "checked" : ""}> ${tvgEscape(item.name)} ${!item.available ? `(${t.unavailable})` : ""}</label>
          ${this._selection.includes(item.id) ? `<button data-move="${tvgEscape(item.id)}" data-direction="-1" aria-label="${t.earlier}">↑</button><button data-move="${tvgEscape(item.id)}" data-direction="1" aria-label="${t.later}">↓</button>` : ""}</div>`).join("")}`;
    } else content = this._programmeRows(this._saved[this._tab], this._tab);
    this.shadowRoot.innerHTML = `<style>
      :host{display:block;color:var(--primary-text-color)}ha-card{padding:16px}h2{margin:0;font-size:22px}.heading,.actions,.toolbar,.tabs{display:flex;gap:8px;align-items:center;flex-wrap:wrap}.heading{justify-content:space-between}.tabs{margin:16px 0;border-bottom:1px solid var(--divider-color);padding-bottom:12px}
      button,select{font:inherit;color:var(--primary-text-color);background:var(--card-background-color,#fff);border:1px solid var(--divider-color,#bbb);border-radius:8px;min-height:40px;padding:6px 10px;cursor:pointer}button[aria-pressed=true]{color:var(--primary-color);border-color:var(--primary-color)}button:disabled,select:disabled{opacity:.5;cursor:default}article{padding:16px 0;border-bottom:1px solid var(--divider-color)}strong{display:block;margin:8px 0}.meta{font-size:13px;color:var(--secondary-text-color)}p{line-height:1.5;overflow-wrap:anywhere}.station{display:flex;align-items:center;gap:8px;margin:8px 0}.station label{flex:1}input{min-width:20px;min-height:20px}.error{color:var(--error-color,#b00020)}details{margin:8px 0}fieldset{border:0;padding:0;margin:0;min-width:0}.list{max-height:65vh;overflow:auto}
      </style><ha-card><div class="heading"><h2>${tvgEscape(this._config.title || t.title)}</h2><button id="refresh" ${disabled}>${t.refresh}</button></div>
      <div class="tabs">${["programme","bookmarks","reminders","channels"].map(tab => `<button data-tab="${tab}" aria-pressed="${this._tab === tab}" ${disabled}>${t[tab]}</button>`).join("")}</div>
      ${this._error ? `<p class="error" role="alert">${tvgEscape(this._error)}</p>` : ""}
      ${this._busy ? `<p role="status">${t.loading}</p>` : ""}<fieldset ${disabled}><div class="list">${content}</div></fieldset></ha-card>`;
    const bind = (selector, event, handler) => this.shadowRoot.querySelectorAll(selector).forEach(el => el.addEventListener(event, handler));
    bind("[data-tab]", "click", event => {this._tab = event.currentTarget.dataset.tab; this._render();});
    bind("#refresh", "click", () => void this._load());
    for (const [id,offset] of [["earlier",-1],["later",1],["now",0]]) bind(`#${id}`, "click", () => {this._start = offset ? this._start + offset*this._hours*3600000 : Date.now(); void this._load();});
    bind("#hours", "change", event => {this._hours = Number(event.target.value); void this._load();});
    bind("#channel", "change", event => {this._channel = event.target.value; void this._load();});
    bind("[data-channel]", "change", event => {
      const id = event.target.dataset.channel;
      this._selection = event.target.checked ? [...this._selection,id] : this._selection.filter(value => value !== id);
      this._render();
    });
    bind("[data-move]", "click", event => {
      const i = this._selection.indexOf(event.currentTarget.dataset.move);
      const j = i + Number(event.currentTarget.dataset.direction);
      if (i >= 0 && j >= 0 && j < this._selection.length) [this._selection[i],this._selection[j]] = [this._selection[j],this._selection[i]];
      this._render();
    });
    bind("#save-channels", "click", () => void this._action("set_channels", {channels:this._selection}));
    bind("#all-channels", "click", () => void this._action("set_channels", {channels:[]}));
    const save = (index, reminder) => {
      const item = this._programmes[index];
      const data = {id:item.id, title:item.title.slice(0,240), channel:(item.channel_name || item.channel).slice(0,120), channel_id:item.channel.slice(0,120), start:item.start, end:item.stop};
      if (reminder) data.minutes = Number(this.shadowRoot.getElementById(`minutes-${index}`).value);
      void this._action(reminder ? "save_reminder" : "save_bookmark", data);
    };
    bind("[data-bookmark]", "click", event => save(Number(event.currentTarget.dataset.bookmark), false));
    bind("[data-remind]", "click", event => save(Number(event.currentTarget.dataset.remind), true));
    bind("[data-remove]", "click", event => {
      const {kind,remove} = event.currentTarget.dataset;
      void this._action("remove_saved_programme", {id:this._saved[kind][Number(remove)].id, kind:kind === "bookmarks" ? "bookmark" : "reminder"});
    });
  }
}
if (!customElements.get("tv-guide-native-card")) customElements.define("tv-guide-native-card", TVGuideNativeCard);
window.customCards = window.customCards || [];
if (!window.customCards.some(card => card.type === "tv-guide-native-card")) window.customCards.push({type:"tv-guide-native-card", name:"TV Guide Native", description:"Native programme schedule, channels, bookmarks and reminders", preview:true});
