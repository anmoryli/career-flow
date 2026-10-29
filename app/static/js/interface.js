'use strict';
// Local document filtering never sends resume names to an external service.
document.addEventListener('DOMContentLoaded', () => {
  const search = document.querySelector('[data-library-search]');
  if (!search) return;
  const documents = [...document.querySelectorAll('[data-library-document]')];
  const empty = document.querySelector('[data-library-empty]');
  search.addEventListener('input', () => {
    const query = search.value.trim().toLocaleLowerCase();
    let visible = 0;
    documents.forEach(item => {
      item.hidden = !item.dataset.documentTitle.toLocaleLowerCase().includes(query);
      if (!item.hidden) visible += 1;
    });
    if (empty) empty.hidden = visible > 0 || documents.length === 0;
  });
});
document.addEventListener('click', event => {
  const evidence = event.target.closest('[data-evidence-filter]');
  if (evidence) {
    const panel = evidence.closest('.diagnosis-result');
    panel.querySelectorAll('[data-evidence-filter]').forEach(button => button.setAttribute('aria-pressed', String(button === evidence)));
    panel.querySelectorAll('[data-evidence-category]').forEach(row => { row.hidden = evidence.dataset.evidenceFilter !== 'all' && row.dataset.evidenceCategory !== evidence.dataset.evidenceFilter; });
  }
  const report = event.target.closest('[data-report-filter]');
  if (report) {
    document.querySelectorAll('[data-report-filter]').forEach(button => button.setAttribute('aria-pressed', String(button === report)));
    let visible = 0;
    document.querySelectorAll('[data-report-operation]').forEach(row => {
      const state = row.dataset.operationState;
      const filter = report.dataset.reportFilter;
      row.hidden = !(filter === 'all' || filter === state || filter === 'active' && ['queued','running'].includes(state) || filter === 'failed' && ['failed','cancelled'].includes(state));
      if (!row.hidden) visible += 1;
    });
    const empty = document.querySelector('[data-report-filter-empty]');
    if (empty) empty.hidden = visible > 0;
  }
});
