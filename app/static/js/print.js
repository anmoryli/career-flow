document.querySelector('#print-document')?.addEventListener('click', async () => {
  await window.prepareResumePrint?.();
  window.print();
});
document.querySelectorAll('[data-rf]').forEach(node => { node.hidden = !node.textContent.trim(); });
document.querySelectorAll('[data-rf-if]').forEach(node => {
  const value = node.querySelector('[data-rf]');
  if (value) node.hidden = !value.textContent.trim() || /^https?:\/\/$/i.test(value.textContent.trim());
});
document.querySelectorAll('[data-rf-entry]').forEach(node => {
  node.hidden = node.classList.contains('rd-skill-group')
    ? !node.querySelector('.rd-skill-items')?.textContent.trim() : !node.textContent.trim();
});
document.querySelectorAll('[data-rf-section]').forEach(node => {
  const hidden = JSON.parse(document.body.dataset.hiddenSections || '[]');
  node.hidden = hidden.includes(node.dataset.rfSection) || !Array.from(node.querySelectorAll('[data-rf],[data-rf-list]')).some(
    child => child.textContent.trim() && !child.closest('[hidden]')
  );
});
