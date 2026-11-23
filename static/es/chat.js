/* Aria: floating AI climate analyst chat (analyst and admin pages). */
(function () {
  if (window.__esChat) return; window.__esChat = true;
  var ES = window.ES || {};
  var KEY = 'es-chat-v1', hist = [];
  try { hist = JSON.parse(sessionStorage.getItem(KEY) || '[]'); } catch (e) {}
  var fab = document.createElement('button'); fab.type = 'button'; fab.className = 'ai-fab'; fab.setAttribute('aria-label', 'Ask Aria, the AI climate analyst');
  fab.innerHTML = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 11.5a8.5 8.5 0 01-8.5 8.5c-1.5 0-3-.4-4.2-1.1L3 20l1.1-5.3A8.5 8.5 0 1121 11.5z"/><path d="M8.5 11.5h.01M12.5 11.5h.01M16.5 11.5h.01" stroke-width="3"/></svg><span class="dot"></span>';
  var tip = document.createElement('div'); tip.className = 'ai-fab-tip'; tip.textContent = 'Ask Aria, your climate analyst';
  var panel = document.createElement('section'); panel.className = 'ai-panel'; panel.setAttribute('aria-label', 'AI climate analyst chat'); panel.setAttribute('role', 'dialog');
  panel.innerHTML = '<div class="ai-head"><span class="ai-av">A</span><div><b>Aria &middot; Climate Analyst</b><small><span class="livedot"></span><span id="aiProv">grounded in EarthScape data</span></small></div><button type="button" class="clr" id="aiClr">Clear</button><button type="button" class="x" id="aiX" aria-label="Close chat">&times;</button></div>' +
    '<div class="ai-ctx" id="aiCtx"></div><div class="ai-log" id="aiLog" aria-live="polite"></div><div class="ai-sugg" id="aiSugg"></div>' +
    '<form class="ai-form" id="aiForm"><textarea id="aiIn" rows="1" placeholder="Ask about any country, city or year\u2026" aria-label="Your question"></textarea><button type="submit" aria-label="Send"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><path d="M22 2L11 13"/><path d="M22 2l-7 20-4-9-9-4 20-7z"/></svg></button></form>';
  document.body.appendChild(fab); document.body.appendChild(tip); document.body.appendChild(panel);
  var log = panel.querySelector('#aiLog'), input = panel.querySelector('#aiIn'), form = panel.querySelector('#aiForm'), sugg = panel.querySelector('#aiSugg');
  if (!sessionStorage.getItem('es-chat-tip')) { setTimeout(function () { tip.classList.add('show'); setTimeout(function () { tip.classList.remove('show'); }, 4000); }, 2500); sessionStorage.setItem('es-chat-tip', '1'); }

  function esc(s) { return String(s).replace(/[&<>]/g, function (c) { return { '&': '&amp;', '<': '&lt;', '>': '&gt;' }[c]; }); }
  function md(s) { return esc(s).replace(/\*\*(.+?)\*\*/g, '<b>$1</b>').replace(/(^|\n)[-*] /g, '$1\u2022 '); }
  function bubble(role, text) { var d = document.createElement('div'); d.className = 'ai-msg ' + role; d.innerHTML = role === 'bot' ? md(text) : esc(text); log.appendChild(d); log.scrollTop = log.scrollHeight; return d; }
  function addChart(el, spec) {
    if (!spec || !window.Chart || !ES.specChart) return;
    var w = document.createElement('div'); w.className = 'mchart'; w.innerHTML = '<div class="ct">' + esc(spec.title) + '</div><div class="cb"><canvas></canvas></div>';
    el.appendChild(w); ES.specChart(w.querySelector('canvas'), spec); log.scrollTop = log.scrollHeight;
  }
  function typeOut(el, text, done) {
    if (ES.reduceMotion) { el.innerHTML = md(text); return done(); }
    var words = text.split(/(\s+)/), i = 0;
    (function step() { i += 2; el.innerHTML = md(words.slice(0, i).join('')); log.scrollTop = log.scrollHeight; if (i < words.length) setTimeout(step, 18); else done(); })();
  }
  var SUGG_BASE = ['How has Karachi warmed since 1980?', 'Will Pakistan be hotter by 2035?', "What's the weather in Lahore this week?", 'Compare rain in Islamabad', 'How strong is the CO2 link?'];
  function suggestions() {
    var c = window.ES_CONTEXT, list = SUGG_BASE.slice();
    if (c && c.country) list = ['How has ' + c.place + ' warmed since 1980?', 'What will ' + c.country + ' be like in 2035?', 'Weather in ' + c.place + ' this week?', 'Rainfall pattern in ' + c.place + '?'];
    sugg.style.display = hist.length > 2 ? 'none' : '';
    sugg.innerHTML = list.slice(0, 4).map(function (s) { return '<button type="button">' + esc(s) + '</button>'; }).join('');
    sugg.querySelectorAll('button').forEach(function (b) { b.onclick = function () { send(b.textContent); }; });
    var ctx = panel.querySelector('#aiCtx'); ctx.classList.toggle('on', !!(c && c.country)); if (c && c.country) ctx.textContent = '\ud83d\udccd Talking about: ' + c.place + (c.place !== c.country ? ' (' + c.country + ')' : '');
  }
  function render() {
    log.innerHTML = '';
    if (!hist.length) bubble('bot', "Hi! I'm Aria, EarthScape's climate analyst. Ask me about any country or city: how it has warmed, its rain, this week's weather or where it's heading by 2035. I'll answer from our data and draw a chart when it helps.");
    hist.forEach(function (h) { var d = bubble(h.role === 'user' ? 'user' : 'bot', h.content); if (h.chart) addChart(d, h.chart); });
  }
  function save() { try { sessionStorage.setItem(KEY, JSON.stringify(hist.slice(-12))); } catch (e) {} }
  var busy = false;
  function send(text) {
    text = (text || '').trim(); if (!text || busy) return; busy = true;
    bubble('user', text); input.value = ''; input.style.height = '44px';
    var typing = document.createElement('div'); typing.className = 'ai-typing'; typing.innerHTML = '<i></i><i></i><i></i>'; log.appendChild(typing); log.scrollTop = log.scrollHeight;
    var history = hist.slice(-8).map(function (h) { return { role: h.role, content: h.content }; });
    hist.push({ role: 'user', content: text }); save();
    fetch('/api/chat', { method: 'POST', headers: { 'Content-Type': 'application/json', 'X-Requested-With': 'fetch' }, body: JSON.stringify({ message: text, history: history, context: window.ES_CONTEXT || {} }) })
      .then(function (r) { return r.json(); })
      .then(function (d) {
        typing.remove();
        var reply = d.reply || d.error || 'Sorry, I could not answer that.';
        var el = bubble('bot', '');
        typeOut(el, reply, function () {
          if (d.chart) addChart(el, d.chart);
          var s = document.createElement('span'); s.className = 'src'; s.textContent = d.provider || ''; el.appendChild(s);
          panel.querySelector('#aiProv').textContent = d.provider || 'grounded in EarthScape data';
          hist.push({ role: 'assistant', content: reply, chart: d.chart || null }); save(); busy = false; suggestions();
        });
      })
      .catch(function () { typing.remove(); bubble('bot', 'I lost the connection for a moment. Please send that again.'); busy = false; });
  }
  function open(o) { panel.classList.toggle('open', o); if (o) { suggestions(); setTimeout(function () { input.focus(); }, 200); log.scrollTop = log.scrollHeight; } }
  fab.onclick = function () { tip.classList.remove('show'); open(!panel.classList.contains('open')); };
  panel.querySelector('#aiX').onclick = function () { open(false); };
  panel.querySelector('#aiClr').onclick = function () { hist = []; save(); render(); };
  form.onsubmit = function (e) { e.preventDefault(); send(input.value); };
  input.addEventListener('keydown', function (e) { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); send(input.value); } });
  input.addEventListener('input', function () { input.style.height = '44px'; input.style.height = Math.min(110, input.scrollHeight) + 'px'; });
  addEventListener('keydown', function (e) { if (e.key === 'Escape' && panel.classList.contains('open')) open(false); });
  ES.openChat = function (q) { open(true); if (q) send(q); };
  render();
})();
