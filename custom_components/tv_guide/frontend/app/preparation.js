/* Initial preparation stays in HA when this view closes. */
export function createPreparation({root, request:requestAction, scope, i18n, render}) {
  const setTimeout=scope.setTimeout, clearTimeout=scope.clearTimeout;
  const t = message => i18n.t(message);
  const style = document.createElement('style');
  style.textContent = `#preparationDialog{color:var(--primary-text-color,#eee);background:var(--card-background-color,#202529);border:1px solid var(--divider-color,#666);border-radius:10px;max-width:440px;width:calc(100cqw - 48px);padding:24px;box-sizing:border-box}#preparationDialog h2{margin-top:0}#preparationDialog progress{width:100%}#preparationDialog button,#preparationBadge{padding:8px 12px;border:1px solid var(--divider-color,#888);border-radius:6px;background:var(--card-background-color,#202529);color:var(--primary-text-color,#eee);cursor:pointer}#preparationBadge{position:fixed;right:12px;bottom:12px;z-index:30}#preparationDialog::backdrop{background:#0008}#preparationDialog p{line-height:1.5}`;
  root.append(style);
  const dialog = document.createElement('dialog');
  dialog.id = 'preparationDialog';
  dialog.setAttribute('aria-labelledby', 'preparationTitle');
  dialog.innerHTML = '<h2 id="preparationTitle"></h2><p id="preparationChannels"></p><p id="preparationProgrammes"></p><p id="preparationLogos"></p><progress id="preparationProgress"></progress><p id="preparationError" role="status"></p><p id="preparationHint"></p><button id="preparationRetry" hidden></button> <button id="preparationClose"></button>';
  const badge = document.createElement('button');
  badge.id = 'preparationBadge'; badge.hidden = true; badge.type = 'button';
  root.append(dialog, badge);
  const node = id => dialog.querySelector('#preparation' + id);
  let completionTimer, timer, stopped = false, current, shown = false, lastLogos = 0, key = '', sequence = 0, repairPending = false;
  const dismissed = () => { try { return sessionStorage.getItem(key) === '1'; } catch { return shown; } };
  dialog.addEventListener('close', () => { try { sessionStorage.setItem(key, '1'); } catch {} });
  node('Close').onclick = () => dialog.close();
  badge.onclick = () => { if (!dialog.open) dialog.showModal(); };
  node('Retry').onclick = async () => {
    node('Retry').disabled = true;
    try { await requestAction({endpoint:'preparation',method:'POST'}); repairPending = true; }
    catch { node('Error').textContent = t("Download fehlgeschlagen. Die Übersicht bleibt nutzbar."); }
    finally { node('Retry').disabled = false; if (!stopped) {clearTimeout(timer); void poll();} }
  };
  function updateLanguage() {
    if (!current) return;
    const {logos, programmes} = current;
    const error = Boolean(logos.error || programmes.error);
    node('Title').textContent = current.complete ? t("Vorbereitung abgeschlossen") : t("TV Guide wird vorbereitet");
    node('Channels').textContent = '✓ ' + t("Senderlisten verfügbar");
    node('Programmes').textContent = t("Programmdaten") + ': ' + (programmes.running ? t("Wird geladen …") : programmes.ready ? t("Verfügbar") : '—') + ' (' + programmes.sources_completed + ' ' + t("Quellen geprüft") + ')';
    node('Logos').textContent = t("Logo-Bibliothek") + ': ' + logos.completed + ' / ' + logos.total;
    node('Progress').max = logos.total || 1; node('Progress').value = logos.completed;
    node('Progress').setAttribute('aria-label', t("Logo-Bibliothek"));
    node('Error').textContent = error ? t("Download fehlgeschlagen. Die Übersicht bleibt nutzbar.") : '';
    node('Hint').textContent = t("Du kannst dieses Fenster schließen. Die Vorbereitung läuft im Hintergrund weiter."); node('Close').textContent = t("Schließen");
    node('Retry').textContent = t("Erneut versuchen"); node('Retry').hidden = !error;
    badge.textContent = error ? t("Download fehlgeschlagen. Die Übersicht bleibt nutzbar.") : t("TV Guide wird vorbereitet") + ' · ' + logos.completed + '/' + logos.total;
    badge.hidden = current.complete && !error;
  }
  async function poll() {
    if (stopped || document.hidden) return;
    const request = ++sequence;
    try {
      const result = await requestAction({endpoint:'preparation',method:'GET'});
      if (stopped || request !== sequence || !result.logos) return;
      current = result;
      key = 'tv-guide-preparation-' + current.installation_id;
      const logos = current.logos, programmes = current.programmes;
      const error = Boolean(logos.error || programmes.error);
      updateLanguage();
      if (current.complete && !error && dialog.open && !completionTimer) {
        completionTimer = setTimeout(() => {
          completionTimer = null;
          if (!stopped && current?.complete && !current.logos?.error && !current.programmes?.error && dialog.open) dialog.close();
        }, 1000);
      }
      if (!shown && current.first_install && !current.complete && !dismissed() && !root.querySelector('dialog[open]')) {
        shown = true; dialog.showModal();
      }
      const repairComplete = repairPending && logos.ready;
      if (logos.completed !== lastLogos || repairComplete) {
        if (repairComplete) repairPending = false;
        lastLogos = logos.completed;
        render();
      }
      if (!current.complete || error) timer = setTimeout(poll, error ? 10000 : 2000);
    } catch {
      // A temporary HA disconnection must not discard progress or stop retries.
      if (!stopped && request === sequence) timer = setTimeout(poll, 10000);
    }
  }
  scope.listen(window, 'pagehide', () => {stopped = true; ++sequence; clearTimeout(timer);});
  scope.listen(window, 'pageshow', event => {
    if (event.persisted) {stopped = false; void poll();}
  });
  scope.listen(document, 'visibilitychange', () => {
    clearTimeout(timer);
    ++sequence;
    if (!document.hidden && (!current?.complete || current?.logos?.error || current?.programmes?.error)) void poll();
  });
  void poll();
  return {
    updateLanguage,
    suspend(){stopped=true; ++sequence; clearTimeout(timer); clearTimeout(completionTimer); completionTimer=null;},
    resume(){stopped=false; if(!current?.complete || current?.logos?.error || current?.programmes?.error)void poll();}
  };
}
