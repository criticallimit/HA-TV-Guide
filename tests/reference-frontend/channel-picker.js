/* Country filters affect the catalogue only, never the personal selection. */
globalThis.TVGuideChannelPicker = class {
  constructor(dialog) {
    this.dialog = dialog;
    this.filters = dialog.querySelector("#channelCountryFilters");
    this.search = dialog.querySelector("#channelSearch");
    this.available = dialog.querySelector("#availableChannelsList");
    this.personal = dialog.querySelector("#channelSettingsList");
    this.search.addEventListener("input", () => this.renderAvailable());
    this.filters.addEventListener("change", () => {
      this.countries = [...this.filters.querySelectorAll("input:checked")].map(input => input.value);
      this.renderAvailable();
    });
  }

  t(message, values) { return globalThis.TVGuideI18n.t(message, values); }

  beginLoading() {
    this.channels = null;
    this.search.disabled = true;
    this.filters.replaceChildren();
    this.available.replaceChildren();
    this.personal.replaceChildren();
  }

  setData(data) {
    this.search.disabled = false;
    this.channels = new Map(data.channels.map(channel => [channel.id, channel]));
    this.order = [...data.order];
    this.countries = [...data.countries];
    const collator = new Intl.Collator(globalThis.TVGuideI18n?.language || "en", {usage:"sort", sensitivity:"base"});
    this.supported = [...data.supported_countries].sort((left, right) =>
      collator.compare(this.t(left.name), this.t(right.name))
    );
    this.search.value = "";
    this.filters.replaceChildren();
    for (const country of this.supported) {
      const label = document.createElement("label");
      const input = document.createElement("input");
      input.type = "checkbox";
      input.value = country.code;
      input.checked = this.countries.includes(country.code);
      label.append(input, document.createTextNode(this.t(country.name)));
      this.filters.append(label);
    }
    this.render();
  }

  value() { return {order: [...this.order], countries: [...this.countries]}; }

  logo(channel) {
    const wrapper = document.createElement("span");
    wrapper.className = "settings-logo-wrap";
    const sources = {light:channel.logo_normalized_light, dark:channel.logo_normalized_dark};
    for (const theme of ["light", "dark"]) {
      const source = sources[theme];
      if (!source) continue;
      const image = document.createElement("img");
      image.src = source;
      image.alt = "";
      image.loading = "lazy";
      image.className = "settings-logo settings-logo-" + theme;
      image.addEventListener("error", () => { image.style.visibility = "hidden"; });
      wrapper.append(image);
    }
    return wrapper;
  }

  select(id, checked) {
    this.order = checked ? [...this.order, id] : this.order.filter(item => item !== id);
    this.render();
  }

  renderAvailable() {
    if (!this.channels) return;
    const term = this.search.value.trim().toLocaleLowerCase();
    const selected = new Set(this.order);
    this.available.replaceChildren();
    let count = 0;
    for (const country of this.supported) {
      if (!this.countries.includes(country.code)) continue;
      const name = this.t(country.name);
      const channels = [...this.channels.values()].filter(channel => channel.source_country === country.code &&
        `${channel.name} ${name}`.toLocaleLowerCase().includes(term));
      if (!channels.length) continue;
      const heading = document.createElement("h4");
      heading.textContent = name;
      this.available.append(heading);
      for (const channel of channels) {
        const row = document.createElement("label");
        row.className = "available-channel-row";
        row.dataset.channelId = channel.id;
        const input = document.createElement("input");
        input.type = "checkbox";
        input.checked = selected.has(channel.id);
        input.addEventListener("change", () => this.select(channel.id, input.checked));
        const label = document.createElement("span");
        label.textContent = channel.name;
        row.append(input, this.logo(channel), label);
        this.available.append(row);
        count++;
      }
    }
    if (!count) {
      const empty = document.createElement("p");
      empty.className = "channel-picker-empty";
      empty.textContent = this.t(this.countries.length ? "Keine passenden Sender." : "Wähle mindestens ein Land.");
      this.available.append(empty);
    }
    this.dialog.querySelector("#availableChannelCount").textContent = this.t("{count} angezeigt", {count});
  }

  renderPersonal() {
    this.personal.replaceChildren();
    this.order.forEach((id, index) => {
      const channel = this.channels.get(id);
      if (!channel) return;
      const row = document.createElement("div");
      row.className = "channel-settings-row";
      row.dataset.channelId = id;
      row.draggable = true;
      const handle = document.createElement("span");
      handle.className = "drag-handle";
      handle.textContent = "☰";
      handle.title = this.t("Ziehen");
      const meta = document.createElement("span");
      meta.className = "settings-channel-name";
      const name = document.createElement("span");
      name.textContent = channel.name;
      const country = document.createElement("small");
      country.textContent = this.t(channel.country_name);
      meta.append(name, country);
      const actions = document.createElement("div");
      actions.className = "settings-order-buttons";
      for (const [action, symbol, title] of [["up", "↑", "Nach oben"], ["down", "↓", "Nach unten"], ["remove", "×", "Entfernen"]]) {
        const button = document.createElement("button");
        button.type = "button";
        button.className = "move-" + action;
        button.textContent = symbol;
        button.setAttribute("aria-label", channel.name + ": " + this.t(title));
        button.title = this.t(title);
        button.disabled = (action === "up" && index === 0) || (action === "down" && index === this.order.length - 1);
        button.addEventListener("click", () => {
          if (action === "remove") this.order = this.order.filter(item => item !== id);
          else {
            const next = index + (action === "up" ? -1 : 1);
            [this.order[index], this.order[next]] = [this.order[next], this.order[index]];
          }
          this.render();
        });
        actions.append(button);
      }
      row.append(handle, this.logo(channel), meta, actions);
      row.addEventListener("dragstart", event => { event.dataTransfer.setData("text/plain", id); row.classList.add("dragging"); });
      row.addEventListener("dragend", () => row.classList.remove("dragging"));
      row.addEventListener("dragover", event => event.preventDefault());
      row.addEventListener("drop", event => {
        event.preventDefault();
        const dragged = event.dataTransfer.getData("text/plain");
        if (dragged === id || !this.order.includes(dragged)) return;
        const after = event.clientY >= row.getBoundingClientRect().top + row.offsetHeight / 2;
        this.order = this.order.filter(item => item !== dragged);
        this.order.splice(this.order.indexOf(id) + (after ? 1 : 0), 0, dragged);
        this.render();
      });
      this.personal.append(row);
    });
    if (!this.order.length) {
      const empty = document.createElement("p");
      empty.className = "channel-picker-empty";
      empty.textContent = this.t("Wähle deine Sender aus der Liste aus.");
      this.personal.append(empty);
    }
    this.dialog.querySelector("#personalChannelCount").textContent = this.order.length;
  }

  render() { this.renderAvailable(); this.renderPersonal(); }
};
