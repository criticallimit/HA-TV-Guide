import "./tv-guide-card.js?v=46";

class TVGuidePanel extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({mode:"open"});
    this.shadowRoot.innerHTML = `
      <style>
        :host {display:block;height:100%;overflow:auto;background:var(--primary-background-color)}
        tv-guide-card {display:block}
      </style>
      <tv-guide-card></tv-guide-card>`;
    this._resize = () => this.shadowRoot.querySelector("tv-guide-card")
      .setConfig({height:Math.max(240,window.innerHeight)});
  }
  set hass(hass) {
    this.shadowRoot.querySelector("tv-guide-card").hass = hass;
  }
  connectedCallback() { this._resize();window.addEventListener("resize",this._resize); }
  disconnectedCallback() { window.removeEventListener("resize",this._resize); }
}
if (!customElements.get("tv-guide-panel")) customElements.define("tv-guide-panel",TVGuidePanel);
