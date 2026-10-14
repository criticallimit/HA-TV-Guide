import "./tv-guide-native-card.js?v=9";

class TVGuideNativePanel extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({mode:"open"});
    this.shadowRoot.innerHTML = `
      <style>
        :host {display:block;height:100%;overflow:auto;background:var(--primary-background-color)}
        header {height:64px;display:flex;align-items:center;gap:12px;padding:0 16px;
          box-sizing:border-box;color:var(--primary-text-color);font:20px sans-serif}
        tv-guide-native-card {display:block}
      </style>
      <header><ha-menu-button></ha-menu-button><span>TV Guide</span></header>
      <tv-guide-native-card></tv-guide-native-card>`;
    this._resize = () => this.shadowRoot.querySelector("tv-guide-native-card")
      .setConfig({height:Math.max(240,window.innerHeight-64)});
  }
  set hass(hass) {
    this.shadowRoot.querySelector("tv-guide-native-card").hass = hass;
    this.shadowRoot.querySelector("ha-menu-button").hass = hass;
  }
  set narrow(value) { this.shadowRoot.querySelector("ha-menu-button").narrow = value; }
  connectedCallback() { this._resize();window.addEventListener("resize",this._resize); }
  disconnectedCallback() { window.removeEventListener("resize",this._resize); }
}
if (!customElements.get("tv-guide-native-panel")) customElements.define("tv-guide-native-panel",TVGuideNativePanel);
