/* Shows a library picker when the Docker server has more than one mounted library. */
(function () {
  const box = document.getElementById('libSwitch');
  const sel = document.getElementById('libSelect');
  if (!box || !sel) return;
  let current = '';

  function fill(data) {
    const libs = (data && data.libraries) || [];
    if (libs.length < 2) return;
    current = data.active || '';
    sel.replaceChildren();
    for (const lib of libs) {
      const opt = document.createElement('option');
      opt.value = lib.id;
      opt.textContent = lib.title + (lib.ready ? '' : ' (not ready)');
      if (lib.id === current) opt.selected = true;
      sel.appendChild(opt);
    }
    box.hidden = false;
  }

  fetch('/api/libraries').then(r => r.ok ? r.json() : null).then(fill).catch(() => { });

  sel.addEventListener('change', async () => {
    const id = sel.value;
    if (!id || id === current) return;
    if (!window.confirm('Switch library and reload this page?')) {
      sel.value = current;
      return;
    }
    try {
      await fetch('/api/libraries/use', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ id })
      });
    } catch { /* the server exits to restart */ }
    for (let i = 0; i < 40; i++) {
      await new Promise(done => setTimeout(done, 500));
      try {
        const r = await fetch('/api/libraries');
        if (r.ok) {
          location.reload();
          return;
        }
      } catch { /* still restarting */ }
    }
    location.reload();
  });
})();
