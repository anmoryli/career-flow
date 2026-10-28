(() => {
  const findDocument = () => {
    const stage = document.querySelector('[data-resume-stage]');
    if (stage) {
      const active = stage.querySelector(
        '[data-resume-panel="' + stage.dataset.activeTemplate + '"]',
      );
      return active?.querySelector('.resume-doc') || null;
    }
    return document.querySelector('.print-stage .resume-doc');
  };

  window.prepareResumePrint = async () => {
    const documentNode = findDocument();
    if (!documentNode) return 1;
    documentNode.classList.add('resume-print-fit');
    if (document.fonts?.ready) await document.fonts.ready;
    await Promise.all([...documentNode.querySelectorAll('img')].map(image =>
      image.decode?.().catch(() => undefined),
    ));

    await new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)));
    const availableHeight = 1114;
    const contentHeight = Math.max(availableHeight, documentNode.scrollHeight);
    const scale = Math.max(0.35, Math.min(1, availableHeight / contentHeight));
    documentNode.style.setProperty('--resume-print-scale', String(scale));
    documentNode.style.setProperty('--resume-print-min-height', String(297 / scale) + 'mm');
    return scale;
  };

  window.addEventListener('beforeprint', () => {
    const documentNode = findDocument();
    if (!documentNode) return;
    documentNode.classList.add('resume-print-fit');
    const height = Math.max(1114, documentNode.scrollHeight);
    const scale = Math.max(0.35, Math.min(1, 1114 / height));
    documentNode.style.setProperty('--resume-print-scale', String(scale));
    documentNode.style.setProperty('--resume-print-min-height', String(297 / scale) + 'mm');
  });

  window.addEventListener('afterprint', () => {
    const documentNode = findDocument();
    documentNode?.style.removeProperty('--resume-print-scale');
    documentNode?.style.removeProperty('--resume-print-min-height');
    documentNode?.classList.remove('resume-print-fit');
  });
})();
