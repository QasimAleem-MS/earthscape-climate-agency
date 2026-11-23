/* Live Globe: 177 Natural Earth countries on a 3D globe (globe.gl / three.js),
   a flat-map fallback, search, live city temperature labels, and a country
   panel with Past / Present / Future tabs. */
(function () {
  var ES = window.ES, C = ES.C;
  var page = document.getElementById('globePage'), wrap = document.getElementById('globeWrap'), flatWrap = document.getElementById('flatWrap');
  var hoverEl = document.getElementById('gHover'), drawer = document.getElementById('drawer');
  var S = { features: [], warming: {}, cities: [], mode: 'warming', labels: true, hover: null, selected: null, view: 'globe', g: null };
  ES.globeState = S;
  var mouse = { x: 0, y: 0 };
  page.addEventListener('pointermove', function (e) { var r = page.getBoundingClientRect(); mouse.x = e.clientX - r.left; mouse.y = e.clientY - r.top; hoverEl.style.left = mouse.x + 'px'; hoverEl.style.top = mouse.y + 'px'; });

  function flag(iso) { if (!iso || iso.length !== 2 || iso === '-9') return '\ud83c\udf0d'; return String.fromCodePoint.apply(null, iso.toUpperCase().split('').map(function (c) { return 127397 + c.charCodeAt(0); })); }
  function capColor(f) {
    var p = f.properties;
    if (S.selected === f) return 'rgba(43,217,107,0.85)';
    if (S.hover === f) return 'rgba(62,224,255,0.75)';
    if (S.mode === 'warming') { var w = S.warming[p.name]; return w ? ES.divColor(w.warming, 2.5).replace('rgb', 'rgba').replace(')', ',0.72)') : 'rgba(120,140,170,0.25)'; }
    return 'rgba(46,155,255,0.10)';
  }
  function hoverHtml(f) {
    var p = f.properties, w = S.warming[p.name];
    return '<b>' + flag(p.iso) + ' ' + p.name + '</b><br><span style="color:#8FA6C8">' + (w ? 'Warming ' + ES.sign(w.warming) + ' \u00b0C (' + (w.period || '2004\u201313') + ' vs 1951\u201380) \u00b7 ' + ES.sign(w.per_decade, 2) + ' \u00b0C/dec' + (w.dataset_name && w.dataset_name !== p.name ? ' (series: ' + w.dataset_name + ')' : '') : 'No Berkeley Earth series') + '</span><br><span style="color:#3EE0FF">Click for past \u00b7 present \u00b7 future</span>';
  }
  function setHover(f) {
    if (S.hover === f) return; S.hover = f;
    hoverEl.style.opacity = f ? 1 : 0; if (f) hoverEl.innerHTML = hoverHtml(f);
    page.style.cursor = f ? 'pointer' : '';
    refresh();
  }
  function refresh() {
    if (S.g) S.g.polygonCapColor(capColor).polygonAltitude(function (f) { return f === S.selected ? 0.05 : f === S.hover ? 0.03 : 0.006; });
    if (S.view === 'flat') drawFlat();
  }

  /* ---------------- 3D globe ---------------- */
  function buildGlobe(Globe) {
    var g = S.g = Globe({ rendererConfig: { antialias: true, alpha: true } })(wrap)
      .width(wrap.clientWidth).height(wrap.clientHeight).backgroundColor('rgba(0,0,0,0)')
      .globeImageUrl(ES.staticBase + 'img/earth-blue-marble.jpg').bumpImageUrl(ES.staticBase + 'img/earth-topology.png')
      .atmosphereColor('#4da3ff').atmosphereAltitude(0.18)
      .polygonsData(S.features).polygonCapColor(capColor).polygonSideColor(function () { return 'rgba(10,60,140,0.25)'; })
      .polygonStrokeColor(function () { return 'rgba(190,220,255,0.35)'; }).polygonAltitude(0.006).polygonsTransitionDuration(250)
      .onPolygonHover(function (f) { setHover(f); })
      .onPolygonClick(function (f) { openCountry(f); })
      .htmlElementsData(S.labels ? S.cities : []).htmlLat('lat').htmlLng('lon').htmlAltitude(0.012).htmlElement(cityEl);
    var ctl = g.controls(); ctl.autoRotate = !ES.reduceMotion; ctl.autoRotateSpeed = 0.35; ctl.minDistance = 130; ctl.maxDistance = 600;
    g.pointOfView({ lat: 25, lng: 68, altitude: 2.2 }, 0);
    wrap.addEventListener('pointerdown', function () { ctl.autoRotate = false; });
    ctl.addEventListener('change', queueDeclutter);
    new ResizeObserver(function () { g.width(wrap.clientWidth).height(wrap.clientHeight); }).observe(wrap);
    document.addEventListener('visibilitychange', function () { document.hidden ? g.pauseAnimation() : g.resumeAnimation(); });
    document.dispatchEvent(new Event('es:globe'));
  }
  function cityEl(c) {
    var el = c._el = document.createElement('div'); el.className = 'citylabel hid'; el.style.background = ES.tempColor(c.temp);
    el.innerHTML = Math.round(c.temp) + '\u00b0<span>' + c.city + '</span>';
    el.title = c.city + ', ' + c.country + ': ' + ES.fmt(c.temp, 1) + ' \u00b0C, ' + c.sky;
    el.onclick = function (e) { e.stopPropagation(); openPlace({ name: c.city, country: c.country, lat: c.lat, lon: c.lon, kind: 'city' }); };
    return el;
  }

  /* ---------------- label declutter ----------------
     Chips are shown only on the front of the globe and away from its limb,
     never under the open panel or outside the frame, and never on top of each
     other: a greedy pass keeps the highest-priority chip in each spot
     (Pakistan first, then the most extreme temperatures). Zoom in to see more. */
  var PRIO_PK = { Pakistan: 1 };
  function priority(c) { return (PRIO_PK[c.country] ? 100 : 0) + Math.abs((c.temp || 0) - 15) + (c.city === 'Karachi' || c.city === 'Islamabad' ? 50 : 0); }
  var declutterQueued = false;
  function queueDeclutter() { if (declutterQueued) return; declutterQueued = true; requestAnimationFrame(function () { declutterQueued = false; declutter(); }); }
  function declutter() {
    var g = S.g; if (!g || !S.labels) return;
    var pov = g.pointOfView(), rad = Math.PI / 180;
    var cl = Math.cos(pov.lat * rad), sl = Math.sin(pov.lat * rad);
    var wr = wrap.getBoundingClientRect(), pr = page.getBoundingClientRect(), dr = drawer.classList.contains('open') ? drawer.getBoundingClientRect() : null;
    var limb = pov.altitude > 2.6 ? 0.45 : pov.altitude > 1.6 ? 0.32 : 0.2;   // how far from the edge a chip must be
    var placed = [];
    S.cities.slice().sort(function (a, b) { return priority(b) - priority(a); }).forEach(function (c) {
      if (!c._el) return;
      var dot = cl * Math.cos(c.lat * rad) * Math.cos((c.lon - pov.lng) * rad) + sl * Math.sin(c.lat * rad);
      var show = dot > limb;
      if (show) {
        var sc = g.getScreenCoords(c.lat, c.lon, 0.012), x = wr.left + sc.x, y = wr.top + sc.y;
        var w = 34 + c.city.length * 6.2, h = 20, box = [x - w / 2 - 2, y - h / 2 - 2, x + w / 2 + 2, y + h / 2 + 2];
        if (box[0] < pr.left + 4 || box[2] > pr.right - 4 || box[1] < pr.top + 60 || box[3] > pr.bottom - 4) show = false;
        if (show && dr && box[2] > dr.left) show = false;
        if (show && placed.some(function (b) { return !(box[2] < b[0] || box[0] > b[2] || box[3] < b[1] || box[1] > b[3]); })) show = false;
        if (show) placed.push(box);
      }
      c._el.classList.toggle('hid', !show);
    });
  }
  setInterval(function () { if (!document.hidden) queueDeclutter(); }, 400);

  /* ---------------- flat map (2D canvas, equirectangular) ---------------- */
  var fcv = document.createElement('canvas'); flatWrap.appendChild(fcv); var paths = [];
  function proj(lon, lat, W, H) { return [(lon + 180) / 360 * W, (90 - lat) / 180 * H]; }
  function drawFlat() {
    var dpr = Math.min(2, devicePixelRatio || 1), W = flatWrap.clientWidth - 40, H = Math.min(flatWrap.clientHeight - 130, W / 2);
    fcv.width = W * dpr; fcv.height = H * dpr; fcv.style.width = W + 'px'; fcv.style.height = H + 'px'; fcv.style.margin = '0 auto';
    var ctx = fcv.getContext('2d'); ctx.setTransform(dpr, 0, 0, dpr, 0, 0); ctx.clearRect(0, 0, W, H);
    ctx.fillStyle = 'rgba(14,40,86,0.35)'; ctx.fillRect(0, 0, W, H);
    ctx.strokeStyle = 'rgba(120,170,255,0.08)'; ctx.lineWidth = 1;
    for (var lo = -150; lo <= 150; lo += 30) { var a = proj(lo, 0, W, H)[0]; ctx.beginPath(); ctx.moveTo(a, 0); ctx.lineTo(a, H); ctx.stroke(); }
    for (var la = -60; la <= 60; la += 30) { var b = proj(0, la, W, H)[1]; ctx.beginPath(); ctx.moveTo(0, b); ctx.lineTo(W, b); ctx.stroke(); }
    paths = S.features.map(function (f) {
      var p = new Path2D(), polys = f.geometry.type === 'Polygon' ? [f.geometry.coordinates] : f.geometry.coordinates;
      polys.forEach(function (poly) { poly.forEach(function (ring) { ring.forEach(function (pt, i) { var q = proj(pt[0], pt[1], W, H); i ? p.lineTo(q[0], q[1]) : p.moveTo(q[0], q[1]); }); p.closePath(); }); });
      ctx.fillStyle = capColor(f); ctx.fill(p); ctx.strokeStyle = 'rgba(190,220,255,0.35)'; ctx.lineWidth = 0.6; ctx.stroke(p);
      return [f, p];
    });
    if (S.labels) S.cities.forEach(function (c) {
      var q = proj(c.lon, c.lat, W, H); ctx.fillStyle = ES.tempColor(c.temp); ctx.beginPath(); ctx.arc(q[0], q[1], 3.5, 0, 6.3); ctx.fill();
      ctx.font = '600 10px Inter, Arial'; ctx.fillStyle = '#fff'; ctx.fillText(Math.round(c.temp) + '\u00b0', q[0] + 5, q[1] + 3);
    });
  }
  function flatHit(e) {
    var r = fcv.getBoundingClientRect(), x = e.clientX - r.left, y = e.clientY - r.top, ctx = fcv.getContext('2d');
    var dpr = Math.min(2, devicePixelRatio || 1);
    for (var i = paths.length - 1; i >= 0; i--) { ctx.setTransform(dpr, 0, 0, dpr, 0, 0); if (ctx.isPointInPath(paths[i][1], x * dpr, y * dpr)) return paths[i][0]; }
    return null;
  }
  fcv.addEventListener('mousemove', function (e) { setHover(flatHit(e)); });
  fcv.addEventListener('mouseleave', function () { setHover(null); });
  fcv.addEventListener('click', function (e) { var f = flatHit(e); if (f) openCountry(f); });
  addEventListener('resize', function () { if (S.view === 'flat') drawFlat(); });

  /* ---------------- toolbar ---------------- */
  function seg(id, fn) { document.querySelectorAll('#' + id + ' button').forEach(function (b) { b.onclick = function () { document.querySelectorAll('#' + id + ' button').forEach(function (x) { x.classList.toggle('on', x === b); }); fn(b.dataset.v); }; }); }
  seg('segView', function (v) { S.view = v; page.classList.toggle('flat', v === 'flat'); if (v === 'flat') drawFlat(); });
  seg('segMode', function (v) { S.mode = v; document.getElementById('legWarm').style.display = v === 'warming' ? '' : 'none'; refresh(); });
  seg('segLabels', function (v) { S.labels = v === 'on'; if (S.g) S.g.htmlElementsData(S.labels ? S.cities : []); refresh(); });

  var q = document.getElementById('gSearch'), sug = document.getElementById('gSugg'), act = -1, items = [];
  function suggest() {
    var t = q.value.trim().toLowerCase(); act = -1;
    if (!t) { sug.classList.remove('open'); return; }
    items = S.features.filter(function (f) { return f.properties.name.toLowerCase().indexOf(t) >= 0 || f.properties.long.toLowerCase().indexOf(t) >= 0; }).slice(0, 7).map(function (f) { return { label: flag(f.properties.iso) + ' ' + f.properties.name, sub: f.properties.cont, f: f }; })
      .concat(S.cities.filter(function (c) { return c.city.toLowerCase().indexOf(t) >= 0; }).slice(0, 4).map(function (c) { return { label: '\ud83d\udccd ' + c.city, sub: c.country, c: c }; }));
    items.push({ label: '\ud83d\udd0e Search "' + q.value.trim() + '" anywhere', sub: 'Open-Meteo geocoding', geo: q.value.trim() });
    sug.innerHTML = items.map(function (it, i) { return '<div data-i="' + i + '">' + it.label + '<small>' + it.sub + '</small></div>'; }).join('');
    sug.classList.add('open');
    sug.querySelectorAll('div').forEach(function (d) { d.onmousedown = function (e) { e.preventDefault(); pick(items[+d.dataset.i]); }; });
  }
  function pick(it) {
    sug.classList.remove('open'); q.blur();
    if (it.f) openCountry(it.f);
    else if (it.c) openPlace({ name: it.c.city, country: it.c.country, lat: it.c.lat, lon: it.c.lon, kind: 'city' });
    else if (it.geo) ES.getJSON('/api/geocode?q=' + encodeURIComponent(it.geo), 1440).then(function (p) { openPlace({ name: p.name, country: p.country, lat: p.lat, lon: p.lon, kind: 'city' }); }).catch(function (e) { q.value = ''; q.placeholder = e.message; });
  }
  q.addEventListener('input', suggest);
  q.addEventListener('keydown', function (e) {
    var ds = sug.querySelectorAll('div');
    if (e.key === 'ArrowDown' || e.key === 'ArrowUp') { e.preventDefault(); act = (act + (e.key === 'ArrowDown' ? 1 : -1) + ds.length) % ds.length; ds.forEach(function (d, i) { d.classList.toggle('act', i === act); }); }
    else if (e.key === 'Enter') { e.preventDefault(); if (items.length) pick(items[act >= 0 ? act : 0]); }
    else if (e.key === 'Escape') sug.classList.remove('open');
  });
  q.addEventListener('blur', function () { setTimeout(function () { sug.classList.remove('open'); }, 150); });

  /* ---------------- country / place panel ---------------- */
  var cache = {}, cur = null;
  function openCountry(f) {
    var p = f.properties; S.selected = f; refresh();
    openPlace({ name: p.name, country: p.name, lat: p.lat, lon: p.lon, kind: p.kind, place: p.place, iso: p.iso, cont: p.cont, pop: p.pop, feature: f });
  }
  function openPlace(pl) {
    cur = pl;
    if (!pl.feature) { S.selected = null; refresh(); }
    if (S.g) { S.g.controls().autoRotate = false; S.g.pointOfView({ lat: pl.lat, lng: pl.lon, altitude: 1.6 }, ES.reduceMotion ? 0 : 1400); }
    page.classList.add('panel-open');
    window.ES_CONTEXT = { country: pl.country, place: pl.place || pl.name, lat: pl.lat, lon: pl.lon };
    document.getElementById('drFlag').textContent = pl.iso ? flag(pl.iso) : '\ud83d\udccd';
    document.getElementById('drName').textContent = pl.name;
    var w = S.warming[pl.name];
    document.getElementById('drSub').innerHTML = (pl.kind === 'city' ? (pl.country || '') + ' \u00b7 ' : (pl.kind === 'capital' ? 'Data point: capital, ' + pl.place + ' \u00b7 ' : 'Data point: country centre \u00b7 ')) +
      pl.lat.toFixed(2) + '\u00b0, ' + pl.lon.toFixed(2) + '\u00b0' + (w ? ' \u00b7 Berkeley Earth warming ' + ES.sign(w.warming) + ' \u00b0C' : '');
    var qs = 'lat=' + pl.lat + '&lon=' + pl.lon + '&name=' + encodeURIComponent(pl.kind === 'capital' ? pl.place + ', ' + pl.name : pl.name);
    document.getElementById('drProj').href = '/projections?' + qs;
    document.getElementById('drExplore').style.display = w ? '' : 'none';
    if (w) document.getElementById('drExplore').href = '/explorer?country=' + encodeURIComponent(w.dataset_name);
    drawer.classList.add('open');
    history.replaceState(null, '', '/globe?' + qs);
    tab(document.querySelector('#drTabs button.on').dataset.t);
  }
  function tab(t) {
    document.querySelectorAll('#drTabs button').forEach(function (b) { b.classList.toggle('on', b.dataset.t === t); });
    var body = document.getElementById('drBody'), pl = cur, key = t + ':' + pl.lat + ',' + pl.lon;
    var url = { past: '/api/place/past', present: '/api/place/present', future: '/api/place/projection' }[t] + '?lat=' + pl.lat + '&lon=' + pl.lon + (t === 'future' ? '&years=10' : '');
    var render = { past: ES.renderPast, present: ES.renderPresent, future: ES.renderFuture }[t];
    ES.loading(body, { past: 'Loading 55+ years of monthly ERA5 history\u2026', present: 'Loading current conditions and the 16-day forecast\u2026', future: 'Fitting the projection, running the backtest and fetching CMIP6 models\u2026' }[t]);
    var p = cache[key] ? Promise.resolve(cache[key]) : (t === 'future' ? ES.loadFuture(pl.lat, pl.lon, 10) : ES.getJSON(url, t === 'present' ? 15 : 720));
    p.then(function (d) { cache[key] = d; if (cur !== pl) return; render(body, d, pl.name); body.scrollTop = 0; })
     .catch(function (e) { if (cur === pl) ES.failed(body, e.message, function () { tab(t); }); });
  }
  document.querySelectorAll('#drTabs button').forEach(function (b) { b.onclick = function () { if (cur) tab(b.dataset.t); }; });
  document.getElementById('drClose').onclick = function () { drawer.classList.remove('open'); page.classList.remove('panel-open'); S.selected = null; refresh(); window.ES_CONTEXT = null; if (S.g) S.g.controls().autoRotate = !ES.reduceMotion; };
  addEventListener('keydown', function (e) { if (e.key === 'Escape' && drawer.classList.contains('open')) document.getElementById('drClose').click(); });

  /* ---------------- boot ---------------- */
  Promise.all([
    fetch(ES.staticBase + 'es/countries.geojson').then(function (r) { return r.json(); }),
    ES.getJSON('/api/warming-map', 1440).catch(function () { return {}; }),
  ]).then(function (res) {
    S.features = res[0].features; S.warming = res[1];
    document.getElementById('gCount').textContent = S.features.length + ' countries \u00b7 ' + Object.keys(S.warming).length + ' with Berkeley Earth trends';
    var start = function () {
      var params = new URLSearchParams(location.search);
      if (params.get('lat') && params.get('lon')) openPlace({ name: params.get('name') || 'Selected place', lat: +params.get('lat'), lon: +params.get('lon'), kind: 'city' });
      else if (params.get('country')) { var f = S.features.filter(function (x) { return x.properties.name.toLowerCase() === params.get('country').toLowerCase(); })[0]; if (f) openCountry(f); }
    };
    if (ES.webgl) ES.loadGlobe().then(function (Globe) { buildGlobe(Globe); start(); }).catch(function () { page.classList.add('flat'); S.view = 'flat'; drawFlat(); start(); });
    else { page.classList.add('flat'); S.view = 'flat'; document.querySelector('#segView [data-v=flat]').click(); start(); }
    ES.getJSON('/api/live-cities', 10).then(function (d) { S.cities = d.cities.filter(function (c) { return c.temp != null; }); if (S.g && S.labels) S.g.htmlElementsData(S.cities); if (S.view === 'flat') drawFlat(); }).catch(function () {});
  });
})();
