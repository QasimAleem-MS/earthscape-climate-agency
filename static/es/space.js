/* EarthScape space scene: parallax starfield + lazy 3D Earth with an orbiting satellite.
   - three.js/globe.gl is only downloaded when an Earth container is on screen
   - everything pauses while the tab is hidden
   - prefers-reduced-motion: stars are static and the Earth does not spin */
(function () {
  var ES = window.ES = window.ES || {};
  var reduce = window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  ES.reduceMotion = reduce;
  var STATIC = document.currentScript ? document.currentScript.src.replace(/\/es\/space\.js.*$/, '/') : '/static/';
  ES.staticBase = STATIC;

  /* ---------------- starfield ---------------- */
  function starfield() {
    var c = document.getElementById('es-stars');
    if (!c) return;
    var ctx = c.getContext('2d'), dpr = Math.min(window.devicePixelRatio || 1, 2);
    var W, H, layers = [], mx = 0, my = 0, tx = 0, ty = 0, t0 = performance.now(), running = true, raf;
    function build() {
      W = c.width = innerWidth * dpr; H = c.height = innerHeight * dpr;
      c.style.width = innerWidth + 'px'; c.style.height = innerHeight + 'px';
      var area = innerWidth * innerHeight / 1e4;
      layers = [[0.15, 0.6, Math.round(area * 1.6)], [0.35, 1.0, Math.round(area * 0.7)], [0.7, 1.5, Math.round(area * 0.22)]].map(function (L) {
        var stars = [];
        for (var i = 0; i < L[2]; i++) stars.push({ x: Math.random() * W, y: Math.random() * H, r: (Math.random() * 0.8 + 0.4) * L[1] * dpr, a: Math.random() * 0.6 + 0.35, tw: Math.random() * 6.28, hue: Math.random() < 0.12 ? (Math.random() < 0.5 ? '170,200,255' : '255,220,190') : '255,255,255' });
        return { depth: L[0], stars: stars };
      });
    }
    function draw(now) {
      var t = (now - t0) / 1000;
      tx += (mx - tx) * 0.04; ty += (my - ty) * 0.04;
      ctx.clearRect(0, 0, W, H);
      for (var l = 0; l < layers.length; l++) {
        var L = layers[l], drift = reduce ? 0 : t * 6 * L.depth * dpr;
        var ox = tx * 26 * L.depth * dpr, oy = ty * 18 * L.depth * dpr;
        for (var i = 0; i < L.stars.length; i++) {
          var s = L.stars[i];
          var x = ((s.x - drift - ox) % W + W) % W, y = ((s.y - oy) % H + H) % H;
          var a = reduce ? s.a : s.a * (0.65 + 0.35 * Math.sin(t * 1.4 + s.tw));
          ctx.fillStyle = 'rgba(' + s.hue + ',' + a.toFixed(3) + ')';
          ctx.beginPath(); ctx.arc(x, y, s.r, 0, 6.283); ctx.fill();
        }
      }
      // an occasional shooting star
      if (!reduce && Math.sin(t * 0.37) > 0.995) {
        var sx = (t * 211 % 1) * W, sy = (t * 97 % 1) * H * 0.5;
        var g = ctx.createLinearGradient(sx, sy, sx - 120 * dpr, sy - 40 * dpr);
        g.addColorStop(0, 'rgba(255,255,255,.9)'); g.addColorStop(1, 'rgba(255,255,255,0)');
        ctx.strokeStyle = g; ctx.lineWidth = 1.2 * dpr; ctx.beginPath(); ctx.moveTo(sx, sy); ctx.lineTo(sx - 120 * dpr, sy - 40 * dpr); ctx.stroke();
      }
      if (running && !reduce) raf = requestAnimationFrame(draw);
    }
    build(); draw(performance.now());
    addEventListener('resize', function () { build(); if (reduce) draw(performance.now()); });
    addEventListener('pointermove', function (e) { mx = e.clientX / innerWidth - 0.5; my = e.clientY / innerHeight - 0.5; }, { passive: true });
    document.addEventListener('visibilitychange', function () {
      running = !document.hidden;
      if (running && !reduce) { cancelAnimationFrame(raf); raf = requestAnimationFrame(draw); }
    });
  }

  /* ---------------- lazy loader for globe.gl (three.js bundled inside) ---------------- */
  var globeLib = null;
  ES.loadGlobe = function () {
    if (window.Globe) return Promise.resolve(window.Globe);
    if (globeLib) return globeLib;
    globeLib = new Promise(function (res, rej) {
      var s = document.createElement('script');
      s.src = STATIC + 'vendor/globe.gl.min.js'; s.async = true;
      s.onload = function () { res(window.Globe); }; s.onerror = rej;
      document.head.appendChild(s);
    });
    return globeLib;
  };
  ES.webgl = (function () {
    try { var c = document.createElement('canvas'); return !!(c.getContext('webgl2') || c.getContext('webgl')); } catch (e) { return false; }
  })();

  function satelliteEl() {
    var d = document.createElement('div');
    d.innerHTML = '<svg class="satellite" viewBox="0 0 64 64" aria-hidden="true"><g fill="none" stroke-linejoin="round">' +
      '<rect x="24" y="24" width="16" height="16" rx="3" fill="#dfe9ff" stroke="#8fb6ff" stroke-width="2"/>' +
      '<rect x="2" y="26" width="18" height="12" fill="#1a5fd6" stroke="#6fb2ff" stroke-width="1.5"/><path d="M8 26v12M14 26v12" stroke="#6fb2ff"/>' +
      '<rect x="44" y="26" width="18" height="12" fill="#1a5fd6" stroke="#6fb2ff" stroke-width="1.5"/><path d="M50 26v12M56 26v12" stroke="#6fb2ff"/>' +
      '<path d="M20 32h4M40 32h4" stroke="#c9d8f5" stroke-width="2"/><circle cx="32" cy="20" r="3" fill="#3EE0FF"/><path d="M32 23v1" stroke="#3EE0FF" stroke-width="2"/></g></svg>';
    return d;
  }

  /* ES.earth(container, opts): decorative rotating Earth + satellite */
  ES.earth = function (el, opts) {
    opts = opts || {};
    if (!el) return;
    var fallback = function () { el.innerHTML = '<div class="earth-fallback"><div class="ball"></div></div>'; };
    if (!ES.webgl) { fallback(); return; }
    var started = false;
    var start = function () {
      if (started) return; started = true;
      ES.loadGlobe().then(function (Globe) {
        var w = el.clientWidth || 600, h = el.clientHeight || 500;
        var g = Globe({ animateIn: !reduce, rendererConfig: { antialias: true, alpha: true, powerPreference: 'low-power' } })(el)
          .width(w).height(h).backgroundColor('rgba(0,0,0,0)')
          .globeImageUrl(STATIC + 'img/earth-blue-marble.jpg').bumpImageUrl(STATIC + 'img/earth-topology.png')
          .showAtmosphere(true).atmosphereColor('#4da3ff').atmosphereAltitude(0.2)
          .showGraticules(!!opts.graticules);
        var ctl = g.controls();
        ctl.enableZoom = false; ctl.enablePan = false; ctl.enableRotate = opts.interactive !== false;
        ctl.autoRotate = !reduce; ctl.autoRotateSpeed = opts.speed || 0.45;
        g.pointOfView({ lat: opts.lat != null ? opts.lat : 22, lng: opts.lng != null ? opts.lng : 67, altitude: opts.altitude || 2.1 }, 0);
        // satellite on an inclined orbit, plus its dashed orbit ring
        var inc = 51.6 * Math.PI / 180, alt = opts.satAlt || 0.42, phase = 0, nodeLng = (opts.lng != null ? opts.lng : 67) + 18;
        function satPos(p) {
          var x = Math.cos(p), y = Math.sin(p) * Math.cos(inc), z = Math.sin(p) * Math.sin(inc);
          return { lat: Math.asin(z) * 180 / Math.PI, lng: Math.atan2(y, x) * 180 / Math.PI + nodeLng, alt: alt };
        }
        var ring = []; for (var i = 0; i <= 120; i++) { var q = satPos(i / 120 * 2 * Math.PI); ring.push([q.lat, q.lng, alt]); }
        var sat = satPos(0);
        g.pathsData([{ pts: ring }]).pathPoints('pts').pathPointLat(function (p) { return p[0]; }).pathPointLng(function (p) { return p[1]; })
          .pathPointAlt(function (p) { return p[2]; }).pathColor(function () { return ['rgba(62,224,255,0.55)', 'rgba(62,224,255,0.08)']; })
          .pathStroke(1.2).pathDashLength(0.02).pathDashGap(0.012).pathDashAnimateTime(reduce ? 0 : 60000).pathTransitionDuration(0);
        if (opts.satellite !== false) {
          g.htmlElementsData([sat]).htmlLat('lat').htmlLng('lng').htmlAltitude('alt').htmlElement(function () { return satelliteEl(); }).htmlTransitionDuration(0);
        }
        if (opts.onReady) opts.onReady(g);
        var last = performance.now(), visible = true, raf;
        function tick(now) {
          var dt = Math.min(0.05, (now - last) / 1000); last = now;
          if (!reduce) {
            phase += dt * 0.32;
            var p = satPos(phase); sat.lat = p.lat; sat.lng = p.lng;
            g.htmlElementsData([sat]);
          }
          if (visible) raf = requestAnimationFrame(tick);
        }
        if (!reduce && opts.satellite !== false) raf = requestAnimationFrame(tick);
        function pause() { visible = false; cancelAnimationFrame(raf); g.pauseAnimation(); }
        function resume() { if (visible) return; visible = true; g.resumeAnimation(); last = performance.now(); if (!reduce) raf = requestAnimationFrame(tick); }
        document.addEventListener('visibilitychange', function () { document.hidden ? pause() : resume(); });
        if ('IntersectionObserver' in window) new IntersectionObserver(function (es) { es[0].isIntersecting && !document.hidden ? resume() : pause(); }).observe(el);
        new ResizeObserver(function () { g.width(el.clientWidth).height(el.clientHeight); }).observe(el);
        el._globe = g;
      }).catch(fallback);
    };
    if ('IntersectionObserver' in window) {
      var io = new IntersectionObserver(function (es) { if (es[0].isIntersecting) { io.disconnect(); setTimeout(start, 30); } });
      io.observe(el);
    } else start();
  };

  /* reveal-on-scroll for .reveal blocks */
  function reveals() {
    var els = document.querySelectorAll('.reveal');
    if (!('IntersectionObserver' in window) || reduce) { els.forEach(function (e) { e.classList.add('in'); }); return; }
    var io = new IntersectionObserver(function (es) { es.forEach(function (e) { if (e.isIntersecting) { e.target.classList.add('in'); io.unobserve(e.target); } }); }, { rootMargin: '0px 0px -40px 0px' });
    els.forEach(function (e) { io.observe(e); });
  }

  /* count-up numbers: <span data-count="22.07" data-dec="2"> */
  ES.countUp = function (root) {
    (root || document).querySelectorAll('[data-count]').forEach(function (el) {
      var end = parseFloat(el.getAttribute('data-count')), dec = +(el.getAttribute('data-dec') || 0), pre = el.getAttribute('data-prefix') || '', t0 = null;
      if (isNaN(end)) return;
      var fmt = function (v) { var s = v.toFixed(dec); if (dec === 0) s = Math.round(v).toLocaleString('en-US'); return pre + s; };
      if (reduce) { el.textContent = fmt(end); return; }
      function step(ts) { if (!t0) t0 = ts; var k = Math.min(1, (ts - t0) / 1400), e = 1 - Math.pow(1 - k, 3); el.textContent = fmt(end * e); if (k < 1) requestAnimationFrame(step); }
      requestAnimationFrame(step);
    });
  };

  document.addEventListener('DOMContentLoaded', function () {
    starfield(); reveals(); ES.countUp();
    document.querySelectorAll('[data-earth]').forEach(function (el) {
      var o = {}; try { o = JSON.parse(el.getAttribute('data-earth') || '{}'); } catch (e) {}
      ES.earth(el, o);
    });
  });
})();
