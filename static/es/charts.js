/* EarthScape chart kit: Chart.js theme + helpers (sparklines, warming stripes,
   heatmaps, band charts). Charts are built when they scroll into view so their
   entry animation is actually seen. */
(function () {
  var ES = window.ES = window.ES || {};
  var C = ES.C = { blue: '#0E5FE3', sky: '#2E9BFF', cyan: '#3EE0FF', green: '#2BD96B', red: '#FF5266', amber: '#FFB547', violet: '#8B7CFF', pink: '#FF6FB5', text: '#E6EEFC', muted: '#8FA6C8', grid: 'rgba(120,170,255,0.10)' };
  if (window.Chart) {
    var d = Chart.defaults;
    d.color = C.muted; d.borderColor = C.grid; d.font.family = 'Inter, system-ui, Arial, sans-serif'; d.font.size = 11.5;
    d.responsive = true;
    d.animation.duration = ES.reduceMotion ? 0 : 1100; d.animation.easing = 'easeOutQuart';
    d.interaction.mode = 'index'; d.interaction.intersect = false;
    d.plugins.legend.labels.usePointStyle = true; d.plugins.legend.labels.boxWidth = 8; d.plugins.legend.labels.boxHeight = 8; d.plugins.legend.labels.color = '#BFD0EA';
    var tt = d.plugins.tooltip;
    tt.backgroundColor = 'rgba(5,12,28,0.94)'; tt.borderColor = 'rgba(120,170,255,0.3)'; tt.borderWidth = 1; tt.padding = 10; tt.cornerRadius = 10;
    tt.titleColor = '#fff'; tt.bodyColor = '#D6E4FA'; tt.titleFont = { weight: '600', size: 12.5 }; tt.usePointStyle = true; tt.boxPadding = 4;
    d.elements.line.tension = 0.35; d.elements.line.borderWidth = 2; d.elements.point.radius = 0; d.elements.point.hoverRadius = 5; d.elements.point.hitRadius = 10;
    d.elements.bar.borderRadius = 5; d.elements.bar.borderSkipped = false;
    d.scale.grid.color = C.grid; d.scale.border = { display: false }; d.scale.ticks.color = '#7F95B8';
  }

  ES.alpha = function (hex, a) { var n = parseInt(hex.slice(1), 16); return 'rgba(' + (n >> 16) + ',' + ((n >> 8) & 255) + ',' + (n & 255) + ',' + a + ')'; };
  ES.grad = function (color, a1, a2) {
    return function (ctx) {
      var ch = ctx.chart, area = ch.chartArea; if (!area) return ES.alpha(color, a2 || 0.05);
      var g = ch.ctx.createLinearGradient(0, area.top, 0, area.bottom);
      g.addColorStop(0, ES.alpha(color, a1 == null ? 0.35 : a1)); g.addColorStop(1, ES.alpha(color, a2 == null ? 0.0 : a2)); return g;
    };
  };
  /* diverging colour scale (cold blue -> white -> hot red), like Ed Hawkins' stripes */
  var STOPS = [[8, 48, 107], [33, 113, 181], [107, 174, 214], [247, 247, 247], [252, 146, 114], [222, 45, 38], [103, 0, 13]];
  ES.divColor = function (v, lim) {
    var k = Math.max(-1, Math.min(1, v / (lim || 1))); var p = (k + 1) / 2 * (STOPS.length - 1);
    var i = Math.min(STOPS.length - 2, Math.floor(p)), f = p - i, a = STOPS[i], b = STOPS[i + 1];
    return 'rgb(' + Math.round(a[0] + (b[0] - a[0]) * f) + ',' + Math.round(a[1] + (b[1] - a[1]) * f) + ',' + Math.round(a[2] + (b[2] - a[2]) * f) + ')';
  };
  /* temperature colour for absolute temps (chips, maps) */
  ES.tempColor = function (t) {
    var s = [[-20, '#5B8CFF'], [0, '#3EC5FF'], [10, '#3EE0C8'], [18, '#9BE15D'], [24, '#FFD34D'], [30, '#FF9A3D'], [36, '#FF5266'], [44, '#C2185B']];
    if (t == null) return '#556';
    for (var i = 0; i < s.length - 1; i++) if (t < s[i + 1][0]) return s[i][1];
    return s[s.length - 1][1];
  };

  /* lazily create a chart when its canvas becomes visible */
  ES.chart = function (canvas, cfg) {
    if (typeof canvas === 'string') canvas = document.getElementById(canvas);
    if (!canvas || !window.Chart) return null;
    cfg.options = cfg.options || {}; if (cfg.options.maintainAspectRatio == null) cfg.options.maintainAspectRatio = false;
    var holder = { chart: null };
    var make = function () { if (canvas._chart) canvas._chart.destroy(); holder.chart = canvas._chart = new Chart(canvas, cfg); };
    if ('IntersectionObserver' in window && !cfg.eager) {
      var io = new IntersectionObserver(function (es) { if (es[0].isIntersecting) { io.disconnect(); make(); } }, { rootMargin: '60px' });
      io.observe(canvas);
    } else make();
    return holder;
  };
  ES.now = function (canvas, cfg) { cfg.eager = true; return ES.chart(canvas, cfg); };

  ES.spark = function (canvas, values, color, type) {
    color = color || C.sky;
    return ES.chart(canvas, {
      type: type || 'line',
      data: { labels: values.map(function (_, i) { return i; }), datasets: [{ data: values, borderColor: color, backgroundColor: type === 'bar' ? ES.alpha(color, 0.7) : ES.grad(color, 0.35, 0), fill: true, borderWidth: 1.8, tension: 0.4, borderRadius: 2 }] },
      options: { plugins: { legend: { display: false }, tooltip: { enabled: false } }, scales: { x: { display: false }, y: { display: false } }, animation: { duration: ES.reduceMotion ? 0 : 1400 }, events: [] }
    });
  };

  /* warming stripes as an animated bar chart: one full-height bar per year */
  ES.stripes = function (canvas, years, anoms, opts) {
    opts = opts || {};
    var lim = opts.lim || Math.max.apply(null, anoms.map(function (v) { return Math.abs(v || 0); })) || 1;
    return ES.chart(canvas, {
      type: 'bar',
      data: { labels: years, datasets: [{ data: anoms.map(function () { return 1; }), anomaly: anoms, backgroundColor: anoms.map(function (v) { return ES.divColor(v, lim); }), borderRadius: 0, barPercentage: 1, categoryPercentage: 1 }] },
      options: {
        animation: { duration: ES.reduceMotion ? 0 : 900, delay: function (c) { return ES.reduceMotion ? 0 : c.dataIndex * 8; } },
        interaction: { mode: 'index', intersect: false },
        plugins: { legend: { display: false }, tooltip: { displayColors: false, callbacks: { title: function (i) { return String(i[0].label); }, label: function (i) { var v = anoms[i.dataIndex]; return (v > 0 ? '+' : '') + v.toFixed(2) + ' \u00b0C vs ' + (opts.base || 'normal'); } } } },
        scales: { y: { display: false, max: 1 }, x: { grid: { display: false }, ticks: { maxTicksLimit: 10, maxRotation: 0 } } }
      }
    });
  };

  /* month x year heatmap drawn on canvas with hover tooltip. rows: [[year, month(1-12), value]] */
  var tip;
  function tipEl() { if (!tip) { tip = document.createElement('div'); tip.className = 'es-tip'; document.body.appendChild(tip); } return tip; }
  ES.heatmap = function (holder, rows, opts) {
    opts = opts || {};
    if (typeof holder === 'string') holder = document.getElementById(holder);
    if (!holder) return;
    var years = Array.from(new Set(rows.map(function (r) { return String(r[0]); }))).sort();
    var map = {}; rows.forEach(function (r) { map[r[0] + '-' + r[1]] = r[2]; });
    var vals = rows.map(function (r) { return r[2]; }).filter(function (v) { return v != null; });
    var lim = opts.lim || Math.max(1, Math.max.apply(null, vals.map(Math.abs)));
    var canvas = document.createElement('canvas'); holder.innerHTML = ''; holder.appendChild(canvas);
    var M = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
    var padL = 34, padT = 4, padB = 22, prog = ES.reduceMotion ? 1 : 0, geo;
    function draw() {
      var dpr = Math.min(2, devicePixelRatio || 1), W = holder.clientWidth, H = opts.height || 260;
      canvas.width = W * dpr; canvas.height = H * dpr; canvas.style.height = H + 'px';
      var ctx = canvas.getContext('2d'); ctx.setTransform(dpr, 0, 0, dpr, 0, 0); ctx.clearRect(0, 0, W, H);
      var cw = (W - padL) / years.length, chh = (H - padT - padB) / 12;
      geo = { cw: cw, ch: chh };
      ctx.font = '10.5px Inter, Arial'; ctx.fillStyle = '#7F95B8'; ctx.textBaseline = 'middle'; ctx.textAlign = 'right';
      for (var m = 0; m < 12; m++) ctx.fillText(M[m], padL - 6, padT + m * chh + chh / 2);
      ctx.textAlign = 'center';
      var step = Math.ceil(years.length / 12);
      years.forEach(function (y, i) {
        if (i % step === 0) ctx.fillText(y, padL + i * cw + cw / 2, H - 9);
        for (var m = 0; m < 12; m++) {
          var v = map[y + '-' + (m + 1)];
          var k = Math.max(0, Math.min(1, prog * 1.6 - i / years.length * 0.6));
          ctx.globalAlpha = k;
          ctx.fillStyle = v == null ? 'rgba(255,255,255,0.03)' : ES.divColor(v, lim);
          ctx.beginPath(); if (ctx.roundRect) ctx.roundRect(padL + i * cw + 1, padT + m * chh + 1, cw - 2, chh - 2, 3); else ctx.rect(padL + i * cw + 1, padT + m * chh + 1, cw - 2, chh - 2); ctx.fill();
        }
      });
      ctx.globalAlpha = 1;
    }
    function animate() { if (prog >= 1) return draw(); prog = Math.min(1, prog + 0.03); draw(); requestAnimationFrame(animate); }
    canvas.addEventListener('mousemove', function (e) {
      var r = canvas.getBoundingClientRect(), x = e.clientX - r.left - padL, y = e.clientY - r.top - padT;
      var i = Math.floor(x / geo.cw), m = Math.floor(y / geo.ch), t = tipEl();
      if (i < 0 || i >= years.length || m < 0 || m > 11) { t.style.opacity = 0; return; }
      var v = map[years[i] + '-' + (m + 1)];
      t.innerHTML = '<b>' + M[m] + ' ' + years[i] + '</b><br>' + (v == null ? 'no data' : (v > 0 ? '+' : '') + v.toFixed(2) + ' \u00b0C ' + (opts.unit || 'vs normal'));
      t.style.left = (e.clientX + 14) + 'px'; t.style.top = (e.clientY + 12) + 'px'; t.style.opacity = 1;
    });
    canvas.addEventListener('mouseleave', function () { tipEl().style.opacity = 0; });
    addEventListener('resize', draw);
    if ('IntersectionObserver' in window) { var io = new IntersectionObserver(function (es) { if (es[0].isIntersecting) { io.disconnect(); animate(); } }); io.observe(holder); } else animate();
  };

  /* small chart from a server spec (used by the chatbot) */
  ES.specChart = function (canvas, spec) {
    var colors = [C.sky, C.red, C.green, C.amber];
    var type = spec.type === 'bar-range' ? 'bar' : spec.type;
    return ES.now(canvas, {
      type: type,
      data: { labels: spec.labels, datasets: spec.series.map(function (s, i) {
        var c = colors[i % colors.length];
        return { label: s.label, data: s.data, borderColor: c, backgroundColor: type === 'bar' ? ES.alpha(c, 0.75) : ES.grad(c, 0.3, 0), fill: type === 'line' && i === 0, borderDash: s.dash ? [5, 4] : undefined, spanGaps: false };
      }) },
      options: { plugins: { legend: { display: spec.series.length > 1 } }, scales: { x: { ticks: { maxTicksLimit: 7, maxRotation: 0 } }, y: { ticks: { maxTicksLimit: 5 } } } }
    });
  };

  ES.fmt = function (v, d, u) { return v == null || isNaN(v) ? '\u2013' : (+v).toFixed(d == null ? 1 : d) + (u || ''); };
  ES.sign = function (v, d) { return v == null ? '\u2013' : (v > 0 ? '+' : '') + (+v).toFixed(d == null ? 2 : d); };
  ES.getJSON = function (url, ttlMin) {
    var key = 'es:' + url;
    try { var hit = JSON.parse(localStorage.getItem(key) || 'null'); if (hit && Date.now() - hit.t < (ttlMin || 15) * 60000) return Promise.resolve(hit.d); } catch (e) {}
    return fetch(url, { headers: { 'X-Requested-With': 'fetch' } }).then(function (r) {
      return r.json().then(function (d) {
        if (!r.ok || d.error) throw new Error(d.error || ('Request failed (' + r.status + ')'));
        try { localStorage.setItem(key, JSON.stringify({ t: Date.now(), d: d })); } catch (e) { try { Object.keys(localStorage).forEach(function (k) { if (k.indexOf('es:') === 0) localStorage.removeItem(k); }); } catch (e2) {} }
        return d;
      });
    });
  };
})();
