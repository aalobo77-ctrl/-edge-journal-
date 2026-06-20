// Trade filtering
const searchInput = document.getElementById('searchInput');
const filterResult = document.getElementById('filterResult');
const filterDir = document.getElementById('filterDir');
const filterSetup = document.getElementById('filterSetup');
const tbody = document.querySelector('#tradesTable tbody');

function filterTrades() {
  if (!tbody) return;
  const q = (searchInput?.value || '').toLowerCase();
  const r = filterResult?.value || '';
  const d = filterDir?.value || '';
  const s = filterSetup?.value || '';
  tbody.querySelectorAll('tr').forEach(tr => {
    const txt = tr.textContent.toLowerCase();
    const result = tr.querySelector('.badge')?.textContent.trim() || '';
    const dir = tr.querySelector('[class*="dir-"]')?.textContent.trim() || '';
    const setup = tr.querySelector('.tag')?.textContent.trim() || '';
    const match = (!q || txt.includes(q)) && (!r || result === r) && (!d || dir === d) && (!s || setup === s);
    tr.style.display = match ? '' : 'none';
  });
}
searchInput?.addEventListener('input', filterTrades);
filterResult?.addEventListener('change', filterTrades);
filterDir?.addEventListener('change', filterTrades);
filterSetup?.addEventListener('change', filterTrades);

// Table sorting
document.querySelectorAll('[data-sort]').forEach(th => {
  th.addEventListener('click', () => {
    const key = th.dataset.sort;
    const tbody = th.closest('table').querySelector('tbody');
    const rows = [...tbody.querySelectorAll('tr')];
    const dir = th.dataset.order === 'asc' ? -1 : 1;
    rows.sort((a, b) => {
      let av = a.cells[[...th.parentNode.children].indexOf(th)].textContent.trim();
      let bv = b.cells[[...th.parentNode.children].indexOf(th)].textContent.trim();
      if (key === 'date') { av = new Date(av); bv = new Date(bv); }
      if (key === 'pnl' || key === 'entry' || key === 'exit' || key === 'r') { av = parseFloat(av.replace(/[$,\s]/g,'')) || 0; bv = parseFloat(bv.replace(/[$,\s]/g,'')) || 0; }
      return av > bv ? dir : av < bv ? -dir : 0;
    });
    rows.forEach(r => tbody.appendChild(r));
    th.dataset.order = dir === 1 ? 'asc' : 'desc';
  });
});
