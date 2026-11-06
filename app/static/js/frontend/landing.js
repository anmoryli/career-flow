/* Landing motion: reveal, counters, header states. Nothing starts hidden unless this runs. */
(() => {
  const motionQuery = matchMedia('(prefers-reduced-motion: reduce)');

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

  // Number count-up: the P99 evidence inside the hero trace card.
  const counters = [...document.querySelectorAll('[data-count]')];
  if (counters.length && !motionQuery.matches) {
    const easeOut = t => 1 - Math.pow(2, -10 * t);
    counters.forEach(node => { node.style.fontVariantNumeric = 'tabular-nums'; });
    const run = node => {
      const target = Number(node.dataset.count) || 0;
      const start = performance.now(), span = 1500;
      const tick = now => {
        const t = Math.min((now - start) / span, 1);
        node.textContent = String(Math.round(target * (1 - easeOut(t)) + target * t));
        if (t < 1) requestAnimationFrame(tick);
      };
      requestAnimationFrame(tick);
    };
    if ('IntersectionObserver' in window) {
      const seen = new IntersectionObserver(entries => entries.forEach(entry => {
        if (!entry.isIntersecting) return;
        seen.unobserve(entry.target);
        run(entry.target);
      }), { threshold: .4 });
      counters.forEach(node => seen.observe(node));
    } else {
      counters.forEach(run);
    }
  }

  const hero = document.querySelector('.cf-hero');
  const landingRoot = document.querySelector('.cf-landing');
  const header = document.querySelector('[data-site-header]');

  // Scroll progress line pinned to the header edge (marketing pages only).
  if (landingRoot && header && !motionQuery.matches) {
    const bar = document.createElement('i');
    bar.className = 'cf-scroll-progress';
    bar.setAttribute('aria-hidden', 'true');
    header.appendChild(bar);
    const paint = () => {
      const max = document.documentElement.scrollHeight - innerHeight;
      bar.style.transform = `scaleX(${max > 0 ? (scrollY / max).toFixed(4) : 0})`;
    };
    paint();
    addEventListener('scroll', paint, { passive: true });
    addEventListener('resize', paint, { passive: true });
  }

  // Header flips between transparent-on-hero and frosted-on-content.
  if (landingRoot && header) {
    const syncHeader = () => {
      const limit = hero ? hero.offsetTop + hero.offsetHeight - header.offsetHeight - 24 : 0;
      header.toggleAttribute('data-past-hero', scrollY > limit);
    };
    syncHeader();
    addEventListener('scroll', syncHeader, { passive: true });
    addEventListener('resize', syncHeader, { passive: true });
  }

  const fine = matchMedia('(pointer: fine) and (hover: hover)');
  const trace = hero && hero.querySelector('.cf-trace');
  const glow = hero && hero.querySelector('.cf-hero-glow');
  const glowB = hero && hero.querySelector('.cf-hero-glow-b');
  const visual = hero && hero.querySelector('.cf-hero-visual');

  // Pointer response across the full product story, with layered parallax and a moving light.
  if (fine.matches && !motionQuery.matches) {
    document.querySelectorAll('.cf-story-scene').forEach(scene => {
      const art = scene.querySelector('.cf-story-art');
      const panel = art.querySelector('.cf-match-window, .cf-review-window, .cf-version-stack');
      const layers = art.querySelectorAll('.cf-match-row, .cf-review-window>* , .cf-version-sheet');
      const title = scene.querySelector('.cf-interactive-title');
      const titleWords = scene.querySelectorAll('.cf-title-word');
      if (!panel) return;
      scene.addEventListener('pointermove', event => {
        const bounds = scene.getBoundingClientRect();
        const x = Math.max(-.5, Math.min(.5, (event.clientX - bounds.left) / bounds.width - .5));
        const y = Math.max(-.5, Math.min(.5, (event.clientY - bounds.top) / bounds.height - .5));
        art.style.setProperty('--pointer-x', `${50 + x * 100}%`);
        art.style.setProperty('--pointer-y', `${50 + y * 100}%`);
        if (title) title.style.translate = `${(-x * 5).toFixed(1)}px ${(-y * 3).toFixed(1)}px`;
        titleWords.forEach(word => word.style.setProperty('--text-glint', `${(x + .5) * 100}%`));
        panel.style.transform = `perspective(1100px) rotateX(${(-y * 5).toFixed(2)}deg) rotateY(${(x * 6).toFixed(2)}deg) translate3d(${(x * 9).toFixed(1)}px,${(y * 8).toFixed(1)}px,0)`;
        layers.forEach((layer, index) => {
          const depth = layer.classList.contains('is-back') ? -.42 : layer.classList.contains('is-front') ? .36 : (index % 2 ? -.2 : .24);
          layer.style.translate = `${(x * 14 * depth).toFixed(1)}px ${(y * 12 * depth).toFixed(1)}px`;
        });
      }, { passive: true });
      scene.addEventListener('pointerleave', () => {
        art.style.removeProperty('--pointer-x');
        art.style.removeProperty('--pointer-y');
        if (title) title.style.translate = '';
        titleWords.forEach(word => word.style.removeProperty('--text-glint'));
        panel.style.transform = '';
        layers.forEach(layer => { layer.style.translate = ''; });
      }, { passive: true });
    });
  }

  if (!hero || !trace || !fine.matches || motionQuery.matches) return;

  // Magnetic primary CTA: leans toward the pointer, springs back on leave.
  const magnet = hero.querySelector('.cf-actions .cf-button');
  if (magnet) {
    magnet.addEventListener('pointermove', event => {
      const box = magnet.getBoundingClientRect();
      const dx = event.clientX - box.left - box.width / 2;
      const dy = event.clientY - box.top - box.height / 2;
      magnet.style.transform = `translate(${(dx * .14).toFixed(1)}px,${(dy * .3).toFixed(1)}px)`;
    }, { passive: true });
    magnet.addEventListener('pointerleave', () => { magnet.style.transform = ''; }, { passive: true });
  }

  // Pointer parallax: one rAF loop, damped interpolation, transform only.
  const MAX_TILT = 4;
  const want = { x: 0, y: 0, tiltX: 0, tiltY: 0, scroll: 0 };
  const now = { x: 0, y: 0, tiltX: 0, tiltY: 0, scroll: 0 };
  let frame = 0;

  const render = () => {
    frame = 0;
    let moving = false;
    for (const key of ['x', 'y', 'tiltX', 'tiltY', 'scroll']) {
      const delta = want[key] - now[key];
      if (Math.abs(delta) > .01) { now[key] += delta * .1; moving = true; } else { now[key] = want[key]; }
    }
    trace.style.transform = `perspective(1100px) rotateX(${now.tiltX.toFixed(2)}deg) rotateY(${now.tiltY.toFixed(2)}deg) translate3d(${(now.x * .35).toFixed(1)}px,${(now.y * .3).toFixed(1)}px,0)`;
    trace.style.setProperty('--mx', `${(50 + now.x * 1.6).toFixed(1)}%`);
    trace.style.setProperty('--my', `${(50 + now.y * 1.9).toFixed(1)}%`);
    if (glow) glow.style.transform = `translate3d(${now.x.toFixed(1)}px,${now.y.toFixed(1)}px,0)`;
    if (glowB) glowB.style.transform = `translate3d(${(-now.x * .7).toFixed(1)}px,${(-now.y * .55).toFixed(1)}px,0)`;
    if (visual) visual.style.translate = `0 ${now.scroll.toFixed(1)}px`;
    if (moving) frame = requestAnimationFrame(render);
  };
  const kick = () => { if (!frame) frame = requestAnimationFrame(render); };

  hero.addEventListener('pointermove', event => {
    const box = hero.getBoundingClientRect();
    const px = (event.clientX - box.left) / box.width - .5;
    const py = (event.clientY - box.top) / box.height - .5;
    want.x = px * 34;
    want.y = py * 22;
    want.tiltY = px * MAX_TILT;
    want.tiltX = -py * MAX_TILT;
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
