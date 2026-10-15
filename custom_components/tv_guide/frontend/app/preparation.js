/* Initial preparation stays in HA when this view closes. */
export function createPreparation({root, request:requestAction, scope, render}) {
  const setTimeout=scope.setTimeout, clearTimeout=scope.clearTimeout;
  const messages = {
    de: ['TV Guide wird vorbereitet', 'Senderlisten verfügbar', 'Programmdaten', 'Logo-Bibliothek', 'Wird geladen …', 'Verfügbar', 'Du kannst dieses Fenster schließen. Die Vorbereitung läuft im Hintergrund weiter.', 'Schließen', 'Erneut versuchen', 'Download fehlgeschlagen. Die Übersicht bleibt nutzbar.', 'Vorbereitung abgeschlossen', 'Quellen geprüft'],
    en: ['Preparing TV Guide', 'Channel lists available', 'Programme data', 'Logo library', 'Loading …', 'Available', 'You can close this window. Preparation continues in the background.', 'Close', 'Retry', 'Download failed. You can still use the guide.', 'Preparation complete', 'sources checked'],
    da: ['TV Guide klargøres', 'Kanallister er tilgængelige', 'Programdata', 'Logobibliotek', 'Indlæser …', 'Tilgængelig', 'Du kan lukke vinduet. Klargøringen fortsætter i baggrunden.', 'Luk', 'Prøv igen', 'Download mislykkedes. Guiden kan stadig bruges.', 'Klargøring fuldført', 'kilder kontrolleret'],
    fr: ['Préparation de TV Guide', 'Listes des chaînes disponibles', 'Programmes', 'Bibliothèque de logos', 'Chargement…', 'Disponible', 'Vous pouvez fermer cette fenêtre. La préparation continue en arrière-plan.', 'Fermer', 'Réessayer', 'Échec du téléchargement. Le guide reste utilisable.', 'Préparation terminée', 'sources vérifiées'],
    it: ['Preparazione di TV Guide', 'Elenchi dei canali disponibili', 'Programmi', 'Libreria dei loghi', 'Caricamento…', 'Disponibile', 'Puoi chiudere la finestra. La preparazione continua in background.', 'Chiudi', 'Riprova', 'Download non riuscito. La guida resta utilizzabile.', 'Preparazione completata', 'fonti controllate'],
    nl: ['TV Guide wordt voorbereid', 'Zenderlijsten beschikbaar', 'Programmagegevens', 'Logobibliotheek', 'Laden …', 'Beschikbaar', 'Je kunt dit venster sluiten. De voorbereiding gaat op de achtergrond verder.', 'Sluiten', 'Opnieuw proberen', 'Download mislukt. De gids blijft bruikbaar.', 'Voorbereiding voltooid', 'bronnen gecontroleerd'],
    nb: ['TV Guide klargjøres', 'Kanallister tilgjengelige', 'Programdata', 'Logobibliotek', 'Laster …', 'Tilgjengelig', 'Du kan lukke vinduet. Klargjøringen fortsetter i bakgrunnen.', 'Lukk', 'Prøv igjen', 'Nedlasting mislyktes. Guiden kan fortsatt brukes.', 'Klargjøring fullført', 'kilder kontrollert'],
    sv: ['TV Guide förbereds', 'Kanallistor tillgängliga', 'Programdata', 'Logobibliotek', 'Läser in …', 'Tillgänglig', 'Du kan stänga fönstret. Förberedelsen fortsätter i bakgrunden.', 'Stäng', 'Försök igen', 'Hämtningen misslyckades. Guiden kan fortfarande användas.', 'Förberedelsen klar', 'källor kontrollerade']
  };
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
  let timer, stopped = false, current, shown = false, lastLogos = 0, key = '', sequence = 0;
  const text = () => messages[root.lang] || messages.en;
  const dismissed = () => { try { return sessionStorage.getItem(key) === '1'; } catch { return shown; } };
  dialog.addEventListener('close', () => { try { sessionStorage.setItem(key, '1'); } catch {} });
  node('Close').onclick = () => dialog.close();
  badge.onclick = () => { if (!dialog.open) dialog.showModal(); };
  node('Retry').onclick = async () => {
    node('Retry').disabled = true;
    try { await requestAction({endpoint:'preparation',method:'POST'}); }
    catch { node('Error').textContent = text()[9]; }
    finally { node('Retry').disabled = false; if (!stopped) {clearTimeout(timer); void poll();} }
  };
  async function poll() {
    if (stopped || document.hidden) return;
    const request = ++sequence;
    try {
      const result = await requestAction({endpoint:'preparation',method:'GET'});
      if (stopped || request !== sequence || !result.logos) return;
      current = result;
      key = 'tv-guide-preparation-' + current.installation_id;
      const m = text(), logos = current.logos, programmes = current.programmes;
      const error = Boolean(logos.error || programmes.error);
      node('Title').textContent = current.complete ? m[10] : m[0];
      node('Channels').textContent = '✓ ' + m[1];
      node('Programmes').textContent = m[2] + ': ' + (programmes.running ? m[4] : programmes.ready ? m[5] : '—') + ' (' + programmes.sources_completed + ' ' + m[11] + ')';
      node('Logos').textContent = m[3] + ': ' + logos.completed + ' / ' + logos.total;
      node('Progress').max = logos.total || 1; node('Progress').value = logos.completed;
      node('Progress').setAttribute('aria-label', m[3]);
      node('Error').textContent = error ? m[9] : '';
      node('Hint').textContent = m[6]; node('Close').textContent = m[7];
      node('Retry').textContent = m[8]; node('Retry').hidden = !error;
      badge.textContent = error ? m[9] : m[0] + ' · ' + logos.completed + '/' + logos.total;
      badge.hidden = current.complete && !error;
      if (!shown && current.first_install && !current.complete && !dismissed() && !root.querySelector('dialog[open]')) {
        shown = true; dialog.showModal();
      }
      if (logos.completed !== lastLogos) {
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
    suspend(){stopped=true; ++sequence; clearTimeout(timer);},
    resume(){stopped=false; if(!current?.complete || current?.logos?.error || current?.programmes?.error)void poll();}
  };
}
