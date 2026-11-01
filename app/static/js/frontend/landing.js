/* Explicitly illustrative product walkthrough, never a simulated live AI task.
   Motion is an enhancement: nothing starts hidden unless this file runs. */
(() => {
  const motionQuery = matchMedia('(prefers-reduced-motion: reduce)');

  const root = document.querySelector('[data-product-demo]');
  if (root) {
    const tabs = [...root.querySelectorAll('[data-demo-step]')];
    const panels = [...root.querySelectorAll('[data-demo-panel]')];
    const select = index => {
      tabs.forEach((tab, i) => { tab.setAttribute('aria-selected', String(i === index)); tab.tabIndex = i === index ? 0 : -1; });
      panels.forEach((panel, i) => { panel.hidden = i !== index; });
      if (!motionQuery.matches) panels[index].animate([{ opacity: .65, transform: 'translateY(6px)' }, { opacity: 1, transform: 'translateY(0)' }], { duration: 180, easing: 'cubic-bezier(.215,.61,.355,1)' });
    };
    tabs.forEach((tab, index) => {
      tab.addEventListener('click', () => select(index));
      tab.addEventListener('keydown', event => {
        if (!['ArrowLeft', 'ArrowRight', 'Home', 'End'].includes(event.key)) return;
        event.preventDefault();
        const next = event.key === 'Home' ? 0 : event.key === 'End' ? tabs.length - 1 : (index + (event.key === 'ArrowRight' ? 1 : -1) + tabs.length) % tabs.length;
        select(next); tabs[next].focus();
      });
    });
  }

  // Reveal groups: content stays visible for crawlers, no-JS and reduced motion.
  const groups = [...document.querySelectorAll('.cf-landing [data-reveal]')].filter(node => !node.classList.contains('cf-hero'));
  if (groups.length && !motionQuery.matches) {
    document.documentElement.classList.add('cf-motion');
    if ('IntersectionObserver' in window) {
      const observer = new IntersectionObserver(entries => entries.forEach(entry => {
        if (!entry.isIntersecting) return;
        observer.unobserve(entry.target);
        entry.target.classList.add('is-in');
      }), { threshold: .12, rootMargin: '0px 0px -6% 0px' });
      groups.forEach(node => observer.observe(node));
    } else {
      groups.forEach(node => node.classList.add('is-in'));
    }
  }

  const hero = document.querySelector('.cf-hero');
  const fine = matchMedia('(pointer: fine) and (hover: hover)');
  const trace = hero && hero.querySelector('.cf-trace');
  const glow = hero && hero.querySelector('.cf-hero-glow');
  const visual = hero && hero.querySelector('.cf-hero-visual');
  if (!hero || !trace || !fine.matches || motionQuery.matches) return;

  // Pointer parallax: one rAF loop, damped interpolation, transform only.
  const MAX_TILT = 2.4;
  const want = { x: 0, y: 0, tiltX: 0, tiltY: 0, scroll: 0 };
  const now = { x: 0, y: 0, tiltX: 0, tiltY: 0, scroll: 0 };
  let frame = 0;

  const render = () => {
    frame = 0;
    let moving = false;
    for (const key of ['x', 'y', 'tiltX', 'tiltY', 'scroll']) {
      const delta = want[key] - now[key];
      if (Math.abs(delta) > .01) { now[key] += delta * .11; moving = true; } else { now[key] = want[key]; }
    }
    trace.style.transform = `perspective(1200px) rotateX(${now.tiltX.toFixed(2)}deg) rotateY(${now.tiltY.toFixed(2)}deg)`;
    if (glow) glow.style.transform = `translate3d(${now.x.toFixed(1)}px,${now.y.toFixed(1)}px,0)`;
    if (visual) visual.style.translate = `0 ${now.scroll.toFixed(1)}px`;
    if (moving) frame = requestAnimationFrame(render);
  };
  const kick = () => { if (!frame) frame = requestAnimationFrame(render); };

  hero.addEventListener('pointermove', event => {
    const box = hero.getBoundingClientRect();
    const px = (event.clientX - box.left) / box.width - .5;
    const py = (event.clientY - box.top) / box.height - .5;
    want.x = px * 20;
    want.y = py * 14;
    want.tiltY = px * MAX_TILT * 2;
    want.tiltX = -py * MAX_TILT * 2;
    kick();
  }, { passive: true });
  hero.addEventListener('pointerleave', () => {
    want.x = 0; want.y = 0; want.tiltX = 0; want.tiltY = 0;
    kick();
  }, { passive: true });

  let queued = 0;
  addEventListener('scroll', () => {
    if (queued) return;
    queued = requestAnimationFrame(() => {
      queued = 0;
      want.scroll = Math.min(scrollY, hero.offsetHeight) * .06;
      kick();
    });
  }, { passive: true });

  // In-page anchors scroll smoothly without hijacking the whole document.
  document.querySelectorAll('.cf-landing a[href^="#"]').forEach(link => {
    link.addEventListener('click', event => {
      const id = link.getAttribute('href');
      const destination = id && id.length > 1 ? document.querySelector(id) : null;
      if (!destination) return;
      event.preventDefault();
      destination.scrollIntoView({ behavior: 'smooth', block: 'start' });
      history.replaceState(null, '', id);
    });
  });
})();
