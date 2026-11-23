/* Renderers for one place: Past (ERA5 history), Present (now + 16 days) and
   Future (2-10 year climate projection with backtest and CMIP6 cross-check).
   Shared by the Globe country panel and the Projections page. */
(function () {
  var ES = window.ES = window.ES || {}, C = ES.C, uid = 0;
  var M = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
  function id(p) { return (p || 'c') + (++uid); }
  function esc(s) { return String(s == null ? '' : s).replace(/[&<>"]/g, function (c) { return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]; }); }
  function mini(lab, val, sub, color) { return '<div class="kpi" style="--c:' + (color || 'var(--sky)') + '"><div class="k-lab"><i></i>' + lab + '</div><div class="k-num">' + val + '</div>' + (sub ? '<div class="k-sub">' + sub + '</div>' : '') + '</div>'; }
  function box(title, sub, canvasId, size, extra) { return '<div class="panel"><div class="phead"><div><h2>' + title + '</h2>' + (sub ? '<p class="sub">' + sub + '</p>' : '') + '</div>' + (extra || '') + '</div><div class="chartbox ' + (size || '') + '"><canvas id="' + canvasId + '"></canvas></div></div>'; }
  var ICONS = { sun: '\u2600\ufe0f', partly: '\u26c5', cloud: '\u2601\ufe0f', fog: '\ud83c\udf2b\ufe0f', drizzle: '\ud83c\udf26\ufe0f', rain: '\ud83c\udf27\ufe0f', snow: '\u2744\ufe0f', storm: '\u26c8\ufe0f' };
  ES.skyIcon = function (k) { return ICONS[k] || '\u2601\ufe0f'; };

  ES.loading = function (el, text) { el.innerHTML = '<div class="kpis">' + '<div class="skeleton" style="height:86px"></div>'.repeat(3) + '</div><div class="skeleton" style="height:240px;margin-bottom:14px"></div><div class="skeleton" style="height:200px"></div><p class="note" style="margin-top:10px"><span class="spinner"></span>&nbsp; ' + (text || 'Loading climate data\u2026') + '</p>'; };
  ES.failed = function (el, msg, retry) { el.innerHTML = '<div class="errbox">' + esc(msg) + (retry ? ' <button type="button" class="chip" style="margin-left:8px">Retry</button>' : '') + '</div>'; if (retry) el.querySelector('button').onclick = retry; };

  /* ---------------- PAST ---------------- */
  ES.renderPast = function (el, d, name) {
    var ids = { m: id('pm'), s: id('ps'), c: id('pc'), r: id('pr'), a: id('pa'), seg: id('seg') };
    var ex = d.extremes;
    el.innerHTML =
      '<div class="kpis">' +
      mini('Warming trend', ES.sign(d.trend_per_decade, 2) + '<small>\u00b0C/dec</small>', 'since 1980', 'var(--red)') +
      mini('Last 10 yrs vs ' + d.base_label.replace('-', '\u2013'), ES.sign(d.warming_vs_base, 2) + '<small>\u00b0C</small>', 'average difference', 'var(--amber)') +
      mini('Hottest year', ex.hottest_year ? ex.hottest_year[0] : '\u2013', ex.hottest_year ? ES.fmt(ex.hottest_year[1], 2, ' \u00b0C mean') : '', 'var(--pink)') +
      mini('Wettest year', ex.wettest_year ? ex.wettest_year[0] : '\u2013', ex.wettest_year ? ES.fmt(ex.wettest_year[1], 0, ' mm') : '', 'var(--sky)') +
      '</div>' +
      box('Monthly temperature &amp; rain', d.range[0] + ' to ' + d.range[1] + ' \u00b7 ' + esc(d.source), ids.m, 'lg', '<div class="seg" id="' + ids.seg + '"><button data-n="12">1Y</button><button data-n="60" class="on">5Y</button><button data-n="360">30Y</button><button data-n="9999">All</button></div>') +
      '<div class="panel"><div class="phead"><div><h2>Warming stripes</h2><p class="sub">Each year vs the ' + d.base_label.replace('-', '\u2013') + ' average</p></div></div><div class="chartbox sm"><canvas id="' + ids.s + '"></canvas></div></div>' +
      '<div class="grid2">' + box('Seasonal cycle', 'Normal 1991\u20132020 vs ' + d.base_label.replace('-', '\u2013') + ' vs the last 10 years', ids.c) + box('Yearly rainfall', 'Total per year, mm', ids.r) + '</div>' +
      box('Anomaly heatmap', 'Every month vs its 1991\u20132020 normal', null) +
      '<div class="panel"><div class="phead"><div><h2>Extremes</h2></div></div><div class="insights-row">' +
      '<div class="insight"><span class="ico" style="color:var(--red);background:rgba(255,82,102,.14)">\u2191</span><div><b>' + ES.fmt(ex.hottest_month[1], 1, ' \u00b0C') + '</b><span>hottest month, ' + ex.hottest_month[0] + '</span></div></div>' +
      '<div class="insight"><span class="ico">\u2193</span><div><b>' + ES.fmt(ex.coldest_month[1], 1, ' \u00b0C') + '</b><span>coldest month, ' + ex.coldest_month[0] + '</span></div></div>' +
      (ex.biggest_anomaly ? '<div class="insight"><span class="ico" style="color:var(--amber);background:rgba(255,181,71,.14)">!</span><div><b>' + ES.sign(ex.biggest_anomaly[1]) + ' \u00b0C</b><span>biggest anomaly, ' + ex.biggest_anomaly[0] + '</span></div></div>' : '') +
      (ex.wettest_month ? '<div class="insight"><span class="ico" style="color:var(--cyan);background:rgba(62,224,255,.14)">\u2614</span><div><b>' + ES.fmt(ex.wettest_month[1], 0, ' mm') + '</b><span>wettest month, ' + ex.wettest_month[0] + '</span></div></div>' : '') +
      (ex.driest_year ? '<div class="insight"><span class="ico" style="color:var(--amber);background:rgba(255,181,71,.14)">\u2600</span><div><b>' + ES.fmt(ex.driest_year[1], 0, ' mm') + '</b><span>driest year, ' + ex.driest_year[0] + '</span></div></div>' : '') +
      '</div></div><p class="note">Source: ' + esc(d.source) + '. Grid point elevation ' + (d.elevation != null ? d.elevation + ' m' : 'n/a') + '.</p>';
    // heatmap panel: replace the canvas box we created with a div
    var hm = el.querySelectorAll('.panel')[4]; hm.querySelector('.chartbox').outerHTML = '<div class="heatmap" id="' + ids.a + '"></div><div class="legendbar"></div><div class="legendrow"><span>colder</span><span>normal</span><span>warmer</span></div>';
    var mon = d.monthly, chart;
    function drawMonthly(n) {
      var part = mon.slice(-n);
      if (chart && chart.chart) chart.chart.destroy();
      chart = ES.now(ids.m, { type: 'bar', data: { labels: part.map(function (r) { return r[0]; }), datasets: [
        { type: 'line', label: 'Mean temperature \u00b0C', data: part.map(function (r) { return r[1]; }), borderColor: C.amber, backgroundColor: ES.grad(C.amber, .22, 0), fill: true, yAxisID: 'y', borderWidth: n > 400 ? 1 : 2 },
        { label: 'Rain mm', data: part.map(function (r) { return r[2]; }), backgroundColor: ES.alpha(C.sky, .55), yAxisID: 'y1', borderRadius: 2 }] },
        options: { scales: { x: { ticks: { maxTicksLimit: 10, maxRotation: 0 } }, y: { title: { display: true, text: '\u00b0C' } }, y1: { position: 'right', grid: { display: false }, title: { display: true, text: 'mm' } } } } });
    }
    drawMonthly(60);
    el.querySelectorAll('#' + ids.seg + ' button').forEach(function (b) { b.onclick = function () { el.querySelectorAll('#' + ids.seg + ' button').forEach(function (x) { x.classList.toggle('on', x === b); }); drawMonthly(+b.dataset.n); }; });
    ES.stripes(ids.s, d.stripes.map(function (r) { return r[0]; }), d.stripes.map(function (r) { return r[1]; }), { base: d.base_label });
    ES.chart(ids.c, { type: 'line', data: { labels: M, datasets: [
      { label: 'Last 10 years', data: d.climatology.t_recent10, borderColor: C.red, pointRadius: 3 },
      { label: 'Normal 1991-2020', data: d.climatology.t, borderColor: C.amber, backgroundColor: ES.grad(C.amber, .2, 0), fill: true },
      { label: d.base_label, data: d.climatology.t_base, borderColor: C.sky, borderDash: [5, 4] }] } });
    ES.chart(ids.r, { type: 'bar', data: { labels: d.annual_p.map(function (r) { return r[0]; }), datasets: [{ label: 'Rain mm', data: d.annual_p.map(function (r) { return r[1]; }), backgroundColor: ES.grad(C.sky, .95, .35) }] }, options: { plugins: { legend: { display: false } }, scales: { x: { ticks: { maxTicksLimit: 8, maxRotation: 0 } } } } });
    ES.heatmap(ids.a, d.anomalies.map(function (a) { return [a[0].slice(0, 4), +a[0].slice(5, 7), a[1]]; }), { lim: 3, height: 230 });
  };

  /* ---------------- PRESENT ---------------- */
  ES.renderPresent = function (el, d, name) {
    var c = d.current, ids = { r: id('dr'), h: id('hh') };
    el.innerHTML =
      '<div class="nowcard"><div class="nc-main"><span class="nc-ico">' + ES.skyIcon(c.icon) + '</span><div><div class="nc-t">' + ES.fmt(c.temp, 1) + '<small>\u00b0C</small></div><div class="nc-s">' + esc(c.sky) + ' \u00b7 feels like ' + ES.fmt(c.feels, 1) + '\u00b0</div><div class="note">Local time ' + esc((c.time || '').replace('T', ' ')) + ' (' + esc(d.timezone) + ')</div></div></div>' +
      '<div class="nc-grid"><div><span>Humidity</span><b>' + ES.fmt(c.humidity, 0, '%') + '</b></div><div><span>Wind</span><b>' + ES.fmt(c.wind, 0, ' km/h') + '</b></div><div><span>Pressure</span><b>' + ES.fmt(c.pressure, 0, ' hPa') + '</b></div><div><span>Cloud</span><b>' + ES.fmt(c.cloud, 0, '%') + '</b></div><div><span>Rain now</span><b>' + ES.fmt(c.rain, 1, ' mm') + '</b></div><div><span>UV today</span><b>' + ES.fmt(d.days[0] && d.days[0].uv, 1) + '</b></div></div></div>' +
      '<div class="panel"><div class="phead"><div><h2>' + d.days.length + '-day forecast</h2><p class="sub">Daily high / low, rain chance and sky \u00b7 Open-Meteo forecast models</p></div></div><div class="daystrip">' +
      d.days.map(function (x, i) {
        var dt = new Date(x.date + 'T12:00:00'), wd = i === 0 ? 'Today' : dt.toLocaleDateString('en-GB', { weekday: 'short' });
        return '<div class="day"><span class="wd">' + wd + '</span><span class="dd">' + dt.getDate() + ' ' + M[dt.getMonth()] + '</span><span class="di">' + ES.skyIcon(x.icon) + '</span><b>' + ES.fmt(x.tmax, 0, '\u00b0') + '</b><span class="lo">' + ES.fmt(x.tmin, 0, '\u00b0') + '</span><span class="pp">\ud83d\udca7' + ES.fmt(x.pop, 0, '%') + '</span></div>';
      }).join('') + '</div><div class="chartbox"><canvas id="' + ids.r + '"></canvas></div></div>' +
      box('Next 48 hours', 'Hourly temperature and chance of rain', ids.h, 'sm') +
      '<p class="note">Beyond about 10 days, any weather forecast loses skill quickly; for years ahead see the Future tab, which forecasts the climate (averages), not daily weather.</p>';
    ES.now(ids.r, { type: 'bar', data: { labels: d.days.map(function (x) { return x.date.slice(5); }), datasets: [
      { label: 'Low \u2192 high \u00b0C', data: d.days.map(function (x) { return [x.tmin, x.tmax]; }), backgroundColor: d.days.map(function (x) { return ES.alpha(ES.tempColor(x.tmax), .85); }), borderRadius: 8, barPercentage: .5, yAxisID: 'y' },
      { type: 'line', label: 'Rain mm', data: d.days.map(function (x) { return x.rain; }), borderColor: C.cyan, backgroundColor: ES.grad(C.cyan, .25, 0), fill: true, yAxisID: 'y1', pointRadius: 2 }] },
      options: { plugins: { tooltip: { callbacks: { label: function (i) { return i.datasetIndex === 0 ? ' ' + i.raw[0] + '\u00b0 to ' + i.raw[1] + '\u00b0C' : ' ' + i.parsed.y + ' mm rain'; } } } }, scales: { y: { title: { display: true, text: '\u00b0C' } }, y1: { position: 'right', grid: { display: false }, beginAtZero: true, title: { display: true, text: 'mm' } } } } });
    ES.now(ids.h, { type: 'line', data: { labels: d.hours.map(function (h) { return h[0].slice(5).replace('T', ' '); }), datasets: [
      { label: 'Temperature \u00b0C', data: d.hours.map(function (h) { return h[1]; }), borderColor: C.amber, backgroundColor: ES.grad(C.amber, .3, 0), fill: true, yAxisID: 'y' },
      { type: 'bar', label: 'Rain chance %', data: d.hours.map(function (h) { return h[2]; }), backgroundColor: ES.alpha(C.sky, .45), yAxisID: 'y1' }] },
      options: { scales: { x: { ticks: { maxTicksLimit: 8, maxRotation: 0 } }, y1: { position: 'right', min: 0, max: 100, grid: { display: false } } } } });
  };

  /* projection + CMIP6 fetched in parallel; CMIP6 failing never blocks the projection */
  ES.loadFuture = function (lat, lon, years) {
    var q = '?lat=' + lat + '&lon=' + lon + '&years=' + (years || 10);
    return Promise.all([ES.getJSON('/api/place/projection' + q, 720), ES.getJSON('/api/place/cmip6' + q, 1440).catch(function (e) { return { error: e.message }; })])
      .then(function (r) { r[0].cmip6 = r[1]; return r[0]; });
  };

  /* ---------------- FUTURE ---------------- */
  ES.renderFuture = function (el, d, name, opts) {
    opts = opts || {};
    var ids = { a: id('fa'), m: id('fm'), p: id('fp'), s: id('fs'), b: id('fb'), e: id('fe') };
    var A = d.annual, last = A[A.length - 1], first = A[0], bt = d.backtest.metrics, cm = d.cmip6 || {};
    var cmLast = (cm.ensemble || []).filter(function (e) { return e.year === last.year; })[0];
    var hist = d.history_annual_t.slice(-25);
    el.innerHTML =
      '<div class="kpis">' +
      mini('Projected ' + last.year, ES.fmt(last.t, 2) + '<small>\u00b0C</small>', '80% range ' + ES.fmt(last.lo80, 1) + '\u2013' + ES.fmt(last.hi80, 1) + ' \u00b0C', 'var(--red)') +
      mini('Change vs last year obs.', ES.sign(last.t - hist[hist.length - 1][1]) + '<small>\u00b0C</small>', hist[hist.length - 1][0] + ' observed ' + ES.fmt(hist[hist.length - 1][1], 2) + ' \u00b0C', 'var(--amber)') +
      mini('CMIP6 models ' + last.year, cmLast ? ES.fmt(cmLast.t, 2) + '<small>\u00b0C</small>' : '\u2013', cmLast ? 'model spread ' + ES.fmt(cmLast.t_min, 1) + '\u2013' + ES.fmt(cmLast.t_max, 1) + ' \u00b0C' : (cm.error || 'not available'), 'var(--violet)') +
      mini('Backtest error', ES.fmt(bt.annual_mae, 2) + '<small>\u00b0C</small>', 'yearly MAE, 2016\u2192 (monthly ' + ES.fmt(bt.mae, 2) + ')', 'var(--green)') +
      '</div>' +
      box('Yearly mean temperature: observed, projected, CMIP6', 'Shaded: 80% and 95% prediction intervals. They widen with the horizon.', ids.a, 'lg') +
      '<div class="grid2">' + box('Monthly projection, next ' + d.horizon_years + ' years', 'Monthly mean with 80% band', ids.m) + box('Rainfall outlook', 'Projected monthly rain with typical (10th\u201390th percentile) range', ids.p) + '</div>' +
      '<div class="grid2">' + box('Seasonal cycle: normal vs ' + last.year, 'How the average year shifts', ids.s) + box('Backtest: trained to 2015, predicted 2016\u2192', 'Yearly mean, actual vs our model vs climatology only', ids.b) + '</div>' +
      box('Backtest error by month', 'Predicted minus actual, \u00b0C. ' + (bt.coverage80 != null ? bt.coverage80 + '% of months fell inside the 80% band.' : ''), ids.e, 'sm') +
      '<div class="panel howit"><h2>How this projection works</h2><ol>' +
      '<li><b>History:</b> monthly mean temperature and rain from ' + esc(d.source) + ', ' + esc(d.history_annual_t[0][0]) + ' to ' + esc(d.last_observed) + '.</li>' +
      '<li><b>Seasonality:</b> the normal value of each calendar month (' + esc(d.model.climatology_years) + ').</li>' +
      '<li><b>Trend:</b> a straight line fitted to the monthly anomalies from ' + esc(d.model.train_years) + ': ' + ES.sign(d.model.trend_per_decade, 3) + ' \u00b1 ' + ES.fmt(d.model.trend_se_per_decade, 3) + ' \u00b0C per decade.</li>' +
      '<li><b>Uncertainty:</b> month-to-month noise (\u03c3 ' + ES.fmt(d.model.residual_sd, 2) + ' \u00b0C) + slow natural swings (\u03c3 ' + ES.fmt(d.model.decadal_sd, 2) + ' \u00b0C) + trend uncertainty (autocorrelation-corrected), so the bands widen the further ahead we look.</li>' +
      '<li><b>Backtest:</b> the same method trained only to 2015 predicted 2016\u2013' + esc(d.last_observed.slice(0, 4)) + ' with a yearly MAE of ' + ES.fmt(bt.annual_mae, 2) + ' \u00b0C (climatology alone: ' + ES.fmt(bt.annual_mae_climatology_only, 2) + ' \u00b0C).</li>' +
      '<li><b>Cross-check:</b> ' + esc(cm.note || 'CMIP6 models unavailable right now.') + '</li></ol>' +
      '<p class="note" style="margin-top:8px"><b>Honest limits:</b> this is a climate projection of monthly and yearly averages. Day-to-day weather cannot be predicted years ahead by any model. A single year can easily land outside the 80% band (El Ni\u00f1o, volcanoes, a monsoon failure).</p></div>';

    var hy = hist.map(function (r) { return r[0]; }), fy = A.map(function (a) { return a.year; }), labels = hy.concat(fy);
    var pad = function (arr, before) { return new Array(before).fill(null).concat(arr); };
    var cmMap = {}; (cm.ensemble || []).forEach(function (e) { cmMap[e.year] = e; });
    var lastObs = hist[hist.length - 1][1];
    ES.chart(ids.a, { type: 'line', data: { labels: labels, datasets: [
      { label: '95% band', data: pad(A.map(function (a) { return a.hi95; }), hy.length), borderWidth: 0, pointRadius: 0, backgroundColor: 'transparent', fill: false },
      { label: '95% band low', data: pad(A.map(function (a) { return a.lo95; }), hy.length), borderWidth: 0, pointRadius: 0, backgroundColor: ES.alpha(C.red, .10), fill: '-1' },
      { label: '80% band', data: pad(A.map(function (a) { return a.hi80; }), hy.length), borderWidth: 0, pointRadius: 0, fill: false },
      { label: '80% band low', data: pad(A.map(function (a) { return a.lo80; }), hy.length), borderWidth: 0, pointRadius: 0, backgroundColor: ES.alpha(C.red, .18), fill: '-1' },
      { label: 'Observed', data: hist.map(function (r) { return r[1]; }), borderColor: C.sky, pointRadius: 2.5, pointBackgroundColor: C.sky },
      { label: 'Our projection', data: pad([lastObs].concat(A.map(function (a) { return a.t; })), hy.length - 1), borderColor: C.red, borderDash: [6, 4], pointRadius: 2.5, pointBackgroundColor: C.red },
      { label: 'CMIP6 ensemble', data: labels.map(function (y) { return cmMap[y] ? cmMap[y].t : null; }), borderColor: C.violet, pointRadius: 0, borderWidth: 2 }] },
      options: { plugins: { legend: { labels: { filter: function (i) { return i.text.indexOf('low') < 0 && i.text.indexOf('band') < 0; } } }, tooltip: { filter: function (i) { return i.dataset.label.indexOf('band') < 0; }, callbacks: { label: function (i) { return ' ' + i.dataset.label + ': ' + ES.fmt(i.parsed.y, 2) + ' \u00b0C'; }, afterBody: function (it) { var y = +it[0].label, a = A.filter(function (x) { return x.year === y; })[0]; return a ? ['80% range: ' + a.lo80 + ' to ' + a.hi80 + ' \u00b0C', 'Rain: ~' + a.p + ' mm/yr'] : []; } } } }, scales: { x: { ticks: { maxRotation: 0, autoSkip: true, maxTicksLimit: 12 } }, y: { title: { display: true, text: '\u00b0C' } } } } });

    var Mo = d.monthly, recent = d.history_monthly_recent.slice(-24);
    var ml = recent.map(function (r) { return r[0]; }).concat(Mo.map(function (r) { return r.ym; }));
    ES.chart(ids.m, { type: 'line', data: { labels: ml, datasets: [
      { label: 'hi', data: pad(Mo.map(function (r) { return r.hi80; }), recent.length), borderWidth: 0, pointRadius: 0, fill: false },
      { label: 'lo', data: pad(Mo.map(function (r) { return r.lo80; }), recent.length), borderWidth: 0, pointRadius: 0, backgroundColor: ES.alpha(C.amber, .18), fill: '-1' },
      { label: 'Observed', data: recent.map(function (r) { return r[1]; }), borderColor: C.sky, borderWidth: 1.6 },
      { label: 'Projected', data: pad(Mo.map(function (r) { return r.t; }), recent.length), borderColor: C.amber, borderWidth: 1.6 }] },
      options: { plugins: { legend: { labels: { filter: function (i) { return i.text.length > 2; } } }, tooltip: { filter: function (i) { return i.dataset.label.length > 2; }, callbacks: { afterBody: function (it) { var m = Mo.filter(function (x) { return x.ym === it[0].label; })[0]; return m ? ['80% range ' + m.lo80 + ' to ' + m.hi80 + ' \u00b0C'] : []; } } } }, scales: { x: { ticks: { maxTicksLimit: 8, maxRotation: 0 } } } } });

    var first12 = Mo.slice(0, Math.min(Mo.length, 36));
    ES.chart(ids.p, { type: 'bar', data: { labels: first12.map(function (r) { return r.ym; }), datasets: [
      { label: 'Typical range (p10\u2013p90)', data: first12.map(function (r) { return [r.p_lo, r.p_hi]; }), backgroundColor: ES.alpha(C.sky, .18), borderRadius: 4, grouped: false, barPercentage: .9 },
      { label: 'Projected rain mm', data: first12.map(function (r) { return r.p; }), backgroundColor: ES.alpha(C.cyan, .85), borderRadius: 4, grouped: false, barPercentage: .45 }] },
      options: { scales: { x: { ticks: { maxTicksLimit: 9, maxRotation: 0 } }, y: { beginAtZero: true, title: { display: true, text: 'mm' } } } } });

    var lastYearMonths = Mo.filter(function (r) { return +r.ym.slice(0, 4) === last.year; });
    ES.chart(ids.s, { type: 'line', data: { labels: M, datasets: [
      { label: 'Normal (' + d.model.climatology_years + ')', data: d.model.climatology_t, borderColor: C.sky, backgroundColor: ES.grad(C.sky, .18, 0), fill: true },
      { label: 'Projected ' + last.year, data: M.map(function (_, i) { var r = lastYearMonths[i]; return r ? r.t : null; }), borderColor: C.red, pointRadius: 3 }] } });

    var BA = d.backtest.annual;
    ES.chart(ids.b, { type: 'line', data: { labels: BA.map(function (b) { return b.year; }), datasets: [
      { label: 'Actual', data: BA.map(function (b) { return b.actual; }), borderColor: C.sky, pointRadius: 3 },
      { label: 'Our model', data: BA.map(function (b) { return b.pred; }), borderColor: C.red, borderDash: [5, 4], pointRadius: 3 },
      { label: 'Climatology only', data: BA.map(function (b) { return b.clim_only; }), borderColor: 'rgba(200,210,230,.5)', borderDash: [2, 3] }] } });
    var BM = d.backtest.monthly;
    ES.chart(ids.e, { type: 'bar', data: { labels: BM.map(function (b) { return b.ym; }), datasets: [{ label: 'Error \u00b0C', data: BM.map(function (b) { return b.err; }), backgroundColor: BM.map(function (b) { return b.inside80 ? ES.alpha(C.green, .7) : ES.alpha(C.red, .8); }), barPercentage: 1, categoryPercentage: .9, borderRadius: 1 }] },
      options: { plugins: { legend: { display: false }, tooltip: { callbacks: { label: function (i) { var b = BM[i.dataIndex]; return [' predicted ' + b.pred + ' \u00b0C, actual ' + b.actual + ' \u00b0C', ' error ' + ES.sign(b.err) + ' \u00b0C' + (b.inside80 ? ' (inside 80% band)' : ' (outside band)')]; } } } }, scales: { x: { ticks: { maxTicksLimit: 10, maxRotation: 0 } } } } });
  };
})();
