import "./tv-guide-native-card.js?v=9";

class TVGuideNativePanel extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({mode:"open"});
    this.shadowRoot.innerHTML = `
      <style>
        :host {display:block;height:100%;overflow:auto;background:var(--primary-background-color)}
        tv-guide-native-card {display:block}
      </style>
      <tv-guide-native-card></tv-guide-native-card>`;
    this._resize = () => this.shadowRoot.querySelector("tv-guide-native-card")
      .setConfig({height:Math.max(240,window.innerHeight)});
  }
  set hass(hass) {
    this.shadowRoot.querySelector("tv-guide-native-card").hass = hass;
  }
  connectedCallback() { this._resize();window.addEventListener("resize",this._resize); }
  disconnectedCallback() { window.removeEventListener("resize",this._resize); }
}
if (!customElements.get("tv-guide-native-panel")) customElements.define("tv-guide-native-panel",TVGuideNativePanel);
