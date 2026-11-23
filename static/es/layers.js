/* Weather layers for the Live Globe.
   Rain   - NASA GPM IMERG precipitation, latest processed day (NASA GIBS, no key)
   Clouds - NASA MODIS Terra true-colour satellite mosaic, yesterday (NASA GIBS)
   Fires  - NASA VIIRS NOAA-20 active fire detections, latest day (NASA GIBS / FIRMS)
   Storms - active tropical cyclones and erupting volcanoes (NASA EONET, via /api/globe/events)
   Wind   - wind at 10 m right now, animated flow lines (Open-Meteo, via /api/globe/wind)
   Image layers are painted onto the globe's own texture, so they rotate and zoom with it. */
(function () {
  var ES = window.ES, on = {}, base = null, imgs = {}, evts = null, wind = null;
  var GIBS = 'https://gibs.earthdata.nasa.gov/wms/epsg4326/best/wms.cgi?SERVICE=WMS&REQUEST=GetMap&VERSION=1.1.1&STYLES=&SRS=EPSG:4326&BBOX=-180,-90,180,90&WIDTH=2048&HEIGHT=1024&TRANSPARENT=TRUE';
  function ymd(daysAgo) { var d = new Date(Date.now() - daysAgo * 864e5); return d.toISOString().slice(0, 10); }
  var LAYERS = {
    clouds: { url: function () { return '/api/globe/layer/clouds'; }, alpha: 0.9, when: 'Satellite photo, ' + ymd(1) + ' (NASA MODIS)' },
    rain: { url: function () { return '/api/globe/layer/rain'; }, alpha: 0.95, when: 'Latest day NASA has processed (GPM IMERG)' },
    fires: { url: function () { return '/api/globe/layer/fires'; }, alpha: 0.85, when: 'Fire detections, ' + ymd(1) + ' (NASA VIIRS)' }
  };
  var ORDER = ['clouds', 'rain', 'fires'];

  function S() { return ES.globeState; }
  function load(src) { return new Promise(function (res, rej) { var i = new Image(); i.onload = function () { res(i); }; i.onerror = function () { rej(new Error('image')); }; i.src = src; }); }
  function legend() {
    var h = [];
    if (on.rain) h.push('<div class="ll"><b>Rain</b> &middot; ' + LAYERS.rain.when + '<div class="lbar" style="background:linear-gradient(90deg,#1a9e2b,#7ad21c,#f2e60f,#ff8a00,#e3121b,#a1005e)"></div><div class="lrow"><span>Light</span><span>Moderate</span><span>Heavy</span></div><div style="margin-top:3px"><span class="dot" style="background:#7fb6ff"></span>Blue/white = snow</div></div>');
    if (on.clouds) h.push('<div class="ll"><b>Clouds</b> &middot; ' + LAYERS.clouds.when + '. Dark diagonal strips are gaps between satellite passes.</div>');
    if (on.fires) h.push('<div class="ll"><b>Fires</b> &middot; <span class="dot" style="background:#ff3b30"></span>' + LAYERS.fires.when + '. Each speck is a heat source the satellite flagged.</div>');
    if (on.storms) h.push('<div class="ll"><b>Storms &amp; volcanoes</b> &middot; ' + (evts ? '<span class="dot" style="background:#b18cff"></span>' + evts.events.filter(function (e) { return e.kind === 'storm'; }).length + ' storms <span class="dot" style="background:#ff7a2f;margin-left:6px"></span>' + evts.events.filter(function (e) { return e.kind === 'volcano'; }).length + ' volcanoes (NASA EONET)' : '<span class="busy">loading&hellip;</span>') + '</div>');
    if (on.wind) h.push('<div class="ll"><b>Wind now</b> &middot; ' + (wind ? 'flow lines at 10 m, ' + (wind.time || '').replace('T', ' ') + ' UTC' : '<span class="busy">loading&hellip;</span>') + '<div class="lbar" style="background:linear-gradient(90deg,#9ad8ff,#3EE0FF,#2BD96B,#FFB547,#FF5266)"></div><div class="lrow"><span>0</span><span>20</span><span>40</span><span>60+ km/h</span></div></div>');
    document.getElementById('legLayers').innerHTML = h.join('') + (paintErr ? '<div class="ll err">' + paintErr + '</div>' : '');
  }
  var paintErr = '', paintN = 0;
  function paint() {
    var s = S(); if (!s || !s.g) return;
    var want = ORDER.filter(function (k) { return on[k]; });
    var n = ++paintN; paintErr = '';
    if (!want.length) { s.g.globeImageUrl(ES.staticBase + 'img/earth-blue-marble.jpg'); legend(); return; }
    var need = [base ? Promise.resolve(base) : load(ES.staticBase + 'img/earth-blue-marble.jpg').then(function (i) { return base = i; })].concat(want.map(function (k) {
      return imgs[k] ? Promise.resolve(imgs[k]) : load(LAYERS[k].url()).then(function (i) { return imgs[k] = i; }).catch(function () { paintErr = 'NASA did not send the ' + k + ' image just now. Toggle it again in a minute.'; return null; });
    }));
    Promise.all(need).then(function (r) {
      if (n !== paintN) return;
      var c = document.createElement('canvas'); c.width = 4096; c.height = 2048; var x = c.getContext('2d');
      x.drawImage(r[0], 0, 0, c.width, c.height);
      if (on.clouds || on.rain) { x.fillStyle = 'rgba(0,10,30,' + (on.clouds ? 0 : 0.25) + ')'; x.fillRect(0, 0, c.width, c.height); }
      want.forEach(function (k, i) { var im = r[i + 1]; if (!im) return; x.globalAlpha = LAYERS[k].alpha; x.drawImage(im, 0, 0, c.width, c.height); x.globalAlpha = 1; });
      s.g.globeImageUrl(c.toDataURL('image/jpeg', 0.9));
      legend();
    });
  }

  /* ---- storms and volcanoes ---- */
  function drawEvents() {
    var s = S(); if (!s || !s.g) return;
    var list = on.storms && evts ? evts.events : [];
    s.g.ringsData(list).ringLat('lat').ringLng('lon').ringAltitude(0.015)
      .ringColor(function (e) { var c = e.kind === 'storm' ? '177,140,255' : '255,122,47'; return function (t) { return 'rgba(' + c + ',' + (1 - t) + ')'; }; })
      .ringMaxRadius(function (e) { return e.kind === 'storm' ? 6 : 2.5; }).ringPropagationSpeed(2).ringRepeatPeriod(1100);
    s.g.labelsData(list).labelLat('lat').labelLng('lon').labelAltitude(0.02).labelSize(1.6).labelDotRadius(0.6)
      .labelText(function (e) { return e.title.replace('Tropical Cyclone ', 'Cyclone ') + (e.wind ? ' (' + e.wind + ' ' + (e.unit || '') + ')' : ''); })
      .labelColor(function (e) { return e.kind === 'storm' ? '#d8c8ff' : '#ffb27a'; }).labelResolution(3);
    var tracks = on.storms && evts ? evts.events.filter(function (e) { return e.track && e.track.length > 1; }).map(function (e) { return { pts: e.track, kind: 'track' }; }) : [];
    setPaths(tracks, 'track');
  }

  /* ---- wind: streamlines traced through the grid, animated with dashed paths ---- */
  var paths = { track: [], wind: [] };
  function setPaths(list, key) {
    paths[key] = list; var s = S(); if (!s || !s.g) return;
    var all = paths.track.concat(paths.wind);
    s.g.pathsData(all).pathPoints('pts').pathPointLat(function (p) { return p[0]; }).pathPointLng(function (p) { return p[1]; })
      .pathPointAlt(function () { return 0.01; })
      .pathColor(function (d) { return d.kind === 'track' ? ['rgba(177,140,255,0.15)', 'rgba(177,140,255,0.95)'] : [hexA(d.color, 0), hexA(d.color, 0.95)]; })
      .pathStroke(function (d) { return d.kind === 'track' ? 1.6 : 0.9; })
      .pathDashLength(function (d) { return d.kind === 'track' ? 1 : 0.35; }).pathDashGap(function (d) { return d.kind === 'track' ? 0 : 0.25; })
      .pathDashAnimateTime(function (d) { return d.kind === 'track' ? 0 : d.anim; }).pathTransitionDuration(0);
  }
  function hexA(h, a) { var n = parseInt(h.slice(1), 16); return 'rgba(' + (n >> 16) + ',' + (n >> 8 & 255) + ',' + (n & 255) + ',' + a + ')'; }
  function speedColor(v) { return v < 10 ? '#9ad8ff' : v < 20 ? '#3EE0FF' : v < 32 ? '#2BD96B' : v < 48 ? '#FFB547' : '#FF5266'; }
  function buildWind() {
    if (!on.wind || !wind || !wind.points.length) { setPaths([], 'wind'); return; }
    var step = wind.step, grid = {};
    wind.points.forEach(function (p) { var r = (p[3] + 180) * Math.PI / 180; grid[p[0] + ',' + p[1]] = [p[2] * Math.sin(r), p[2] * Math.cos(r)]; });
    var lat0 = Math.min.apply(null, wind.points.map(function (p) { return p[0]; })), lat1 = Math.max.apply(null, wind.points.map(function (p) { return p[0]; }));
    function g(la, lo) { lo = ((lo + 180) % 360 + 360) % 360 - 180; return grid[la + ',' + lo]; }
    function uv(la, lo) {
      if (la < lat0 || la > lat1) return null;
      var a = Math.floor((la - lat0) / step) * step + lat0, b = Math.floor((lo + 180) / step) * step - 180;
      var a2 = Math.min(a + step, lat1), fy = (la - a) / step, fx = (lo - b) / step;
      var q = [g(a, b), g(a, b + step), g(a2, b), g(a2, b + step)]; if (q.some(function (v) { return !v; })) return null;
      return [0, 1].map(function (k) { return (q[0][k] * (1 - fx) + q[1][k] * fx) * (1 - fy) + (q[2][k] * (1 - fx) + q[3][k] * fx) * fy; });
    }
    var out = [];
    for (var la = lat0 + 3; la <= lat1 - 3; la += 8) for (var lo = -180; lo < 180; lo += 8) {
      var sla = la + (Math.random() - .5) * 4, slo = lo + (Math.random() - .5) * 4, pts = [[sla, slo]], sp = 0, n = 0;
      for (var i = 0; i < 14; i++) {
        var v = uv(sla, slo); if (!v) break; var m = Math.hypot(v[0], v[1]); if (m < 1) break;
        sp += m; n++; var h = 0.5 + Math.min(m, 60) * 0.025;
        sla += v[1] / m * h; slo += v[0] / m * h / Math.max(Math.cos(sla * Math.PI / 180), 0.3);
        pts.push([sla, slo]);
      }
      if (pts.length > 4) { var avg = sp / n; out.push({ pts: pts, kind: 'wind', color: speedColor(avg), anim: Math.max(900, 4200 - avg * 55) }); }
    }
    setPaths(out, 'wind');
  }

  function toggle(k, b) {
    on[k] = !on[k]; b.classList.toggle('on', on[k]);
    var s = S();
    if ((k === 'rain' || k === 'clouds' || k === 'fires') && on[k] && s && s.mode === 'warming') { var p = document.querySelector('#segMode [data-v=plain]'); if (p) p.click(); }
    if (s && s.view === 'flat' && on[k]) { var gb = document.querySelector('#segView [data-v=globe]'); if (gb) gb.click(); }
    if (k in LAYERS) paint();
    if (k === 'storms') { legend(); if (on.storms && !evts) ES.getJSON('/api/globe/events', 60).then(function (d) { evts = d; drawEvents(); legend(); }).catch(function (e) { paintErr = 'Storm feed: ' + e.message; legend(); }); else drawEvents(); }
    if (k === 'wind') { legend(); if (on.wind && !wind) ES.getJSON('/api/globe/wind', 60).then(function (d) { wind = d; buildWind(); legend(); }).catch(function (e) { paintErr = 'Wind: ' + e.message; legend(); }); else buildWind(); }
  }
  function init() {
    document.querySelectorAll('#segLayers button').forEach(function (b) { b.onclick = function () { toggle(b.dataset.l, b); }; });
    var q = new URLSearchParams(location.search).get('layers');
    if (q) q.split(',').forEach(function (k) { var b = document.querySelector('#segLayers [data-l=' + k + ']'); if (b) b.click(); });
  }
  document.addEventListener('es:globe', init);
})();
