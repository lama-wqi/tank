/* تانك TANK — منطق التطبيق (متصل بالسيرفر عبر /api) */
const CONFIG = { API: '/api', POLL_MS: 3000 };
const DEFAULTS = { deviceId: '', tankHeight: 150, deadZone: 20, capacity: 1000, low: 40, crit: 20, repeatMin: 1, vibrate: true, suppliers: [] };

/* ---------- أدوات ---------- */
const $ = id => document.getElementById(id);
const phone = document.querySelector('.phone');
const memStore = {};
const store = {
  get: k => { try { const v = localStorage.getItem(k); return v == null ? (memStore[k] ?? null) : JSON.parse(v); } catch { return memStore[k] ?? null; } },
  set: (k, v) => { memStore[k] = v; try { localStorage.setItem(k, JSON.stringify(v)); } catch {} },
  del: k => { delete memStore[k]; try { localStorage.removeItem(k); } catch {} }
};
const clamp = (n, a, b) => Math.max(a, Math.min(b, n));
const h = (tag, props = {}, ...kids) => {
  const e = document.createElement(tag);
  for (const [k, v] of Object.entries(props)) {
    if (k === 'class') e.className = v; else if (k.startsWith('on')) e[k] = v; else e.setAttribute(k, v);
  }
  e.append(...kids); return e;
};
const fmtTime = ts => new Date(ts).toLocaleString('ar-SA', { hour: '2-digit', minute: '2-digit', day: 'numeric', month: 'short' });
const ago = ts => { const s = (Date.now() - ts) / 1000; return s < 60 ? 'الآن' : s < 3600 ? `قبل ${Math.floor(s / 60)} دقيقة` : s < 86400 ? `قبل ${Math.floor(s / 3600)} ساعة` : fmtTime(ts); };
const fmtDur = hrs => hrs < 1 ? 'أقل من ساعة' : hrs < 48 ? `${Math.round(hrs)} ساعة` : `${Math.round(hrs / 24)} يوم`;
const waNum = p => { let d = p.replace(/\D/g, ''); if (d.startsWith('00')) d = d.slice(2); else if (d.startsWith('0')) d = '966' + d.slice(1); return d; };

let toastTimer;
function toast(msg, kind = '') {
  const t = $('toast'); t.textContent = msg; t.className = 'toast show ' + kind;
  clearTimeout(toastTimer); toastTimer = setTimeout(() => t.classList.remove('show'), 4200);
}
window.addEventListener('error', e => toast('خطأ: ' + e.message, 'crit'));

/* ---------- الاتصال بالسيرفر ---------- */
async function api(path, method = 'GET', body) {
  const token = store.get('token');
  let res;
  try {
    res = await fetch(CONFIG.API + path, {
      method,
      headers: { 'Content-Type': 'application/json', ...(token ? { Authorization: 'Bearer ' + token } : {}) },
      body: body ? JSON.stringify(body) : undefined
    });
  } catch { throw new Error('تعذّر الاتصال بالسيرفر. تأكد إنه شغّال.'); }
  const data = await res.json().catch(() => ({}));
  if (res.status === 401 && token) { logout(); throw new Error('انتهت الجلسة، سجّل دخولك من جديد'); }
  if (!res.ok) throw new Error(data.message || 'حدث خطأ، حاول مرة ثانية');
  return data;
}

/* ---------- الحالة ---------- */
let settings = { ...DEFAULTS }, alerts = [], hist = [], ana = { rate: 0, drop: 0, fills: 0 };
let last = { level: null, pump: null, ts: 0 }, unread = 0, filter = 'all', range = 24, pollTimer = null, ticks = 0;
const mem = { zone: null, critAt: 0, protectAt: 0, pump: null };

/* ---------- البداية + التعريف ---------- */
const SLIDES = [
  ['💧', 'اعرف مستوى مياهك', 'حساس داخل الخزان يرسل القراءة لحظة بلحظة إلى جوالك.'],
  ['🔔', 'تنبيه قبل ما تنقطع', 'تذكيرات متكررة عند المستوى الحرج لتطلب الصهريج بدري.'],
  ['⚙️', 'احمِ الدينمو', 'نبّهك عند تشغيله وإيقافه ونحذّرك لو اشتغل على خزان فاضي.']
];
let oi = 0;
function drawOnb() {
  $('oIcon').textContent = SLIDES[oi][0]; $('oTitle').textContent = SLIDES[oi][1]; $('oText').textContent = SLIDES[oi][2];
  $('dots').replaceChildren(...SLIDES.map((_, i) => h('i', { class: i === oi ? 'on' : '' })));
  $('oNext').textContent = oi === SLIDES.length - 1 ? 'ابدأ' : 'التالي';
}
function endOnb() { store.set('onb', true); $('onb').classList.add('hidden'); $('auth').classList.remove('hidden'); }
$('oNext').onclick = () => { if (oi < SLIDES.length - 1) { oi++; drawOnb(); } else endOnb(); };
$('skip').onclick = endOnb;

/* ---------- الدخول ---------- */
document.querySelectorAll('.tab').forEach(t => t.onclick = () => {
  document.querySelectorAll('.tab').forEach(x => x.classList.toggle('active', x === t));
  $('loginForm').classList.toggle('hidden', t.dataset.f !== 'login');
  $('registerForm').classList.toggle('hidden', t.dataset.f !== 'register');
});
async function submitAuth(e, path, payload, errEl) {
  e.preventDefault(); errEl.textContent = '';
  const btn = e.target.querySelector('button[type=submit]'); btn.disabled = true;
  try {
    const { token, user } = await api(path, 'POST', payload);
    store.set('token', token); store.set('user', user); await startApp();
  } catch (err) { errEl.textContent = err.message; }
  btn.disabled = false;
}
$('loginForm').onsubmit = e => submitAuth(e, '/auth/login', { email: $('lEmail').value.trim(), password: $('lPass').value }, $('lErr'));
$('registerForm').onsubmit = e => submitAuth(e, '/auth/register', { name: $('rName').value.trim(), email: $('rEmail').value.trim(), password: $('rPass').value }, $('rErr'));

function logout() {
  clearInterval(pollTimer); store.del('token'); store.del('user');
  last = { level: null, pump: null, ts: 0 }; Object.assign(mem, { zone: null, pump: null });
  closeSheet(); document.querySelector('.tab[data-f=login]').click(); $('app').classList.add('hidden'); $('auth').classList.remove('hidden'); location.hash = '';
}

/* ---------- التنقل ---------- */
const PAGES = ['home', 'stats', 'alerts', 'me'];
function route() {
  const p = PAGES.includes(location.hash.slice(1)) ? location.hash.slice(1) : 'home';
  PAGES.forEach(x => $('v-' + x).classList.toggle('active', x === p));
  document.querySelectorAll('#nav a').forEach(a => a.classList.toggle('active', a.dataset.p === p));
  if (p === 'alerts') { unread = 0; renderBadge(); }
  if (p === 'stats') drawStats();
}
window.addEventListener('hashchange', route);

/* ---------- تشغيل التطبيق ---------- */
async function startApp() {
  $('auth').classList.add('hidden'); $('onb').classList.add('hidden'); $('app').classList.remove('hidden');
  const u = store.get('user') || {};
  $('hello').textContent = 'أهلاً ' + (u.name || '');
  try { settings = { ...DEFAULTS, ...(await api('/settings')) }; } catch (e) { toast(e.message, 'warn'); }
  try { alerts = await api('/alerts'); } catch { alerts = []; }
  renderAll(); route(); refreshAna();
  clearInterval(pollTimer); poll(); pollTimer = setInterval(poll, CONFIG.POLL_MS);
}

/* ---------- قراءة الحساس ---------- */
function toPercent(r) {
  if (typeof r.level === 'number') return clamp(Math.round(r.level), 0, 100);
  if (typeof r.distance_cm === 'number') {
    const span = settings.tankHeight - settings.deadZone;
    return span > 0 ? clamp(Math.round((settings.tankHeight - r.distance_cm) / span * 100), 0, 100) : null;
  }
  return null;
}
async function poll() {
  try {
    const r = await api('/tank/latest');
    const level = toPercent(r); if (level === null) throw new Error('no data');
    const fresh = Date.now() - r.ts < 120000;
    setConn(fresh);
    if (fresh) evaluate(level, !!r.pump);
    last = { level, pump: !!r.pump, ts: r.ts };
    renderHome(); renderMe();
    if (++ticks % 20 === 0) refreshAna();
  } catch (e) {
    setConn(false);
    if (last.level === null) { $('status').textContent = 'بانتظار الحساس'; $('hint').textContent = e.message === 'no data' ? '' : e.message; }
  }
}
function setConn(ok) { const c = $('conn'); c.textContent = ok ? 'متصل بالحساس' : 'غير متصل'; c.classList.toggle('on', ok); }
const zoneOf = l => l <= settings.crit ? 'crit' : l <= settings.low ? 'low' : 'ok';

/* ---------- التنبيهات ---------- */
function evaluate(level, pump) {
  const now = Date.now(), zone = zoneOf(level), gap = settings.repeatMin * 60000;
  if (last.level !== null && level - last.level >= 15) raise('good', `تمت تعبئة الخزان: صار ${level}%.`);
  if (zone !== mem.zone) {
    if (zone === 'low' && mem.zone === 'ok') raise('warn', `مستوى المياه منخفض: باقي ${level}%. جهّز طلب الصهريج.`);
    if (zone === 'crit') { mem.critAt = now; raise('crit', `مستوى المياه حرج: باقي ${level}% فقط. اطلب الصهريج الآن!`); }
    mem.zone = zone;
  } else if (zone === 'crit' && now - mem.critAt >= gap) {
    mem.critAt = now; raise('crit', `تذكير: المياه ما زالت حرجة (${level}%). اطلب الصهريج.`);
  }
  if (mem.pump !== null && mem.pump !== pump) raise('pump', pump ? 'الدينمو اشتغل الآن.' : 'الدينمو توقف.');
  mem.pump = pump;
  if (pump && level <= 5 && now - mem.protectAt >= gap) { mem.protectAt = now; raise('danger', 'خطر: الدينمو شغّال والخزان شبه فارغ. أطفئه فوراً!'); }
}
function raise(type, msg) {
  const a = { ts: Date.now(), type, msg };
  alerts.unshift(a); alerts = alerts.slice(0, 100);
  api('/alerts', 'POST', a).catch(() => {});
  if (location.hash !== '#alerts') { unread++; renderBadge(); }
  renderAlerts();
  toast(msg, type === 'pump' ? '' : type);
  if ('Notification' in window && Notification.permission === 'granted') new Notification('تانك TANK', { body: msg });
  if (settings.vibrate && navigator.vibrate && (type === 'crit' || type === 'danger')) navigator.vibrate([200, 100, 200]);
}
function renderBadge() { $('badge').textContent = unread; $('badge').classList.toggle('hidden', !unread); }

const ICONS = { crit: '🚨', warn: '⚠️', danger: '🛑', pump: '⚙️', good: '✅' };
function renderAlerts() {
  const grp = a => (a.type === 'pump' || a.type === 'danger') ? 'pump' : 'water';
  const list = alerts.filter(a => filter === 'all' || grp(a) === filter);
  $('alertList').replaceChildren(...list.map(a => h('li', { class: a.type }, h('i', {}, ICONS[a.type] || '💧'),
    h('div', {}, h('span', {}, a.msg), h('time', {}, ago(a.ts))))));
  $('alertEmpty').classList.toggle('hidden', list.length > 0);
}
$('filterChips').onclick = e => {
  const b = e.target.closest('.chip'); if (!b) return;
  filter = b.dataset.k; document.querySelectorAll('#filterChips .chip').forEach(c => c.classList.toggle('active', c === b)); renderAlerts();
};
$('clearAlerts').onclick = async () => {
  try { await api('/alerts', 'DELETE'); alerts = []; renderAlerts(); toast('تم مسح التنبيهات'); } catch (e) { toast(e.message, 'warn'); }
};

/* ---------- العرض ---------- */
const TIPS = ['أصلح أي تسريب في الصنابير، قطرة كل ثانية تضيّع مئات اللترات شهرياً.', 'املأ الخزان قبل الصيف ورمضان بوقت كافٍ، الطلب يزيد والمواعيد تتأخر.', 'لا تشغّل الدينمو على خزان شبه فاضي، هذا أكثر سبب لتلف المضخة.', 'نظّف الخزان مرة أو مرتين في السنة للحفاظ على جودة المياه.', 'قلّل مدة الاستحمام دقيقتين، توفّر آلاف اللترات في السنة.', 'اسقِ النباتات صباحاً أو مساءً لتقليل التبخر.'];
function renderAll() { renderHome(); renderAlerts(); renderMe(); renderBadge(); }

function renderHome() {
  $('tip').textContent = TIPS[new Date().getDate() % TIPS.length];
  const L = last.level; if (L === null) return;
  const z = zoneOf(L), cap = settings.capacity, lit = Math.round(L / 100 * cap);
  phone.style.setProperty('--state', { ok: 'var(--surf)', low: 'var(--warn)', crit: 'var(--danger)' }[z]);
  $('water').style.height = L + '%'; $('pct').textContent = L;
  $('liters').textContent = `${lit} لتر من ${cap}`; $('cLiters').textContent = lit;
  $('status').textContent = { ok: 'مستوى جيد', low: 'مستوى منخفض', crit: 'مستوى حرج' }[z];
  $('hint').textContent = { ok: 'مخزونك كافٍ حالياً.', low: 'جهّز طلب الصهريج قبل ما ينزل أكثر.', crit: 'اطلب الصهريج الآن قبل انقطاع المياه.' }[z];
  $('cPump').textContent = last.pump ? 'يعمل' : 'متوقف';
  $('pumpIcon').classList.toggle('on', last.pump);
  $('pumpState').textContent = last.pump ? 'الدينمو يعمل' : 'الدينمو متوقف';
  const runs = alerts.filter(a => a.type === 'pump' && a.msg.includes('اشتغل') && new Date(a.ts).toDateString() === new Date().toDateString()).length;
  $('pumpNote').textContent = last.pump && L <= 5 ? '⚠️ الخزان شبه فارغ، أطفئه فوراً!' : `مرات التشغيل اليوم: ${runs}`;
  if (ana.rate > 0.05) {
    const left = L / ana.rate, toLow = (L - settings.low) / ana.rate;
    $('cLeft').textContent = fmtDur(left);
    $('predText').textContent = `بمعدل استهلاك ${ana.rate.toFixed(1)}% بالساعة، يكفيك تقريباً ${fmtDur(left)}.`;
    $('orderText').textContent = toLow <= 0 ? '🚨 اطلب الصهريج الآن' : `أفضل وقت للطلب: خلال ${fmtDur(toLow)}`;
  } else {
    $('cLeft').textContent = '--';
    $('predText').textContent = 'نحتاج قراءات أكثر لحساب التوقّع.'; $('orderText').textContent = '';
  }
}
function renderMe() {
  const u = store.get('user') || {};
  $('meName').textContent = u.name || ''; $('meMail').textContent = u.email || ''; $('avatar').textContent = (u.name || 'ت')[0];
  const live = last.ts && Date.now() - last.ts < 120000;
  $('devState').textContent = settings.deviceId ? `${settings.deviceId} · ${live ? 'متصل' : 'بانتظار البيانات'}` : 'لم تربط جهازاً بعد';
  $('devDot').classList.toggle('on', !!(settings.deviceId && live));
}

/* ---------- الإحصائيات ---------- */
function analyze(pts) {
  let drop = 0, fills = 0;
  for (let i = 1; i < pts.length; i++) { const d = pts[i].level - pts[i - 1].level; if (d < 0) drop -= d; else if (d >= 15) fills++; }
  const span = pts.length > 1 ? (pts[pts.length - 1].ts - pts[0].ts) / 3600e3 : 0;
  return { drop, fills, rate: span > 0.2 ? drop / span : 0 };
}
async function refreshAna() { try { ana = analyze(await api('/tank/history?hours=24')); renderHome(); } catch {} }
$('rangeChips').onclick = e => {
  const b = e.target.closest('.chip'); if (!b) return;
  range = +b.dataset.h; document.querySelectorAll('#rangeChips .chip').forEach(c => c.classList.toggle('active', c === b)); drawStats();
};
async function drawStats() {
  try { hist = await api('/tank/history?hours=' + range); } catch (e) { return toast(e.message, 'warn'); }
  const a = analyze(hist);
  $('sUse').textContent = Math.round(a.drop / 100 * settings.capacity); $('sFill').textContent = a.fills; $('sRate').textContent = a.rate.toFixed(1);
  $('chartEmpty').classList.toggle('hidden', hist.length > 1);
  const cv = $('chart'), W = cv.clientWidth; if (!W) return;
  const dpr = window.devicePixelRatio || 1, H = 220; cv.width = W * dpr; cv.height = H * dpr;
  const g = cv.getContext('2d'); g.scale(dpr, dpr);
  const pl = 34, pr = 6, pt = 8, pb = 22, w = W - pl - pr, hh = H - pt - pb, y = v => pt + hh - v / 100 * hh;
  g.font = '11px Tajawal'; g.fillStyle = 'rgba(232,247,253,.6)'; g.strokeStyle = 'rgba(232,247,253,.12)';
  [0, 25, 50, 75, 100].forEach(v => { g.beginPath(); g.moveTo(pl, y(v)); g.lineTo(W - pr, y(v)); g.stroke(); g.fillText(v + '%', 2, y(v) + 4); });
  g.strokeStyle = '#ff5a4f'; g.setLineDash([5, 4]); g.beginPath(); g.moveTo(pl, y(settings.crit)); g.lineTo(W - pr, y(settings.crit)); g.stroke(); g.setLineDash([]);
  if (hist.length < 2) return;
  const t0 = hist[0].ts, t1 = hist[hist.length - 1].ts, x = t => pl + (t - t0) / (t1 - t0 || 1) * w;
  g.beginPath(); hist.forEach((p, i) => i ? g.lineTo(x(p.ts), y(p.level)) : g.moveTo(x(p.ts), y(p.level)));
  g.strokeStyle = '#5cc8f0'; g.lineWidth = 2.5; g.lineJoin = 'round'; g.stroke();
  g.lineTo(x(t1), y(0)); g.lineTo(x(t0), y(0)); g.closePath();
  const gr = g.createLinearGradient(0, pt, 0, pt + hh); gr.addColorStop(0, 'rgba(92,200,240,.35)'); gr.addColorStop(1, 'rgba(92,200,240,0)');
  g.fillStyle = gr; g.fill(); g.fillStyle = 'rgba(232,247,253,.6)';
  g.fillText(fmtTime(t0), pl, H - 6); const e2 = fmtTime(t1); g.fillText(e2, W - pr - g.measureText(e2).width, H - 6);
}

/* ---------- النوافذ السفلية ---------- */
function openSheet(title, node) { $('sheetTitle').textContent = title; $('sheetBody').replaceChildren(node); $('sheet').classList.add('open'); }
function closeSheet() { $('sheet').classList.remove('open'); }
$('scrim').onclick = closeSheet;
document.addEventListener('keydown', e => { if (e.key === 'Escape') closeSheet(); });

function validate(n) {
  const nums = ['tankHeight', 'deadZone', 'capacity', 'low', 'crit', 'repeatMin'];
  if (nums.some(k => !Number.isFinite(n[k]) || n[k] <= 0 && k !== 'deadZone')) return 'تأكد من تعبئة كل الأرقام بقيم صحيحة';
  if (n.crit >= n.low) return 'المستوى الحرج لازم يكون أقل من المنخفض';
  if (n.low > 90) return 'المستوى المنخفض لازم يكون 90% أو أقل';
  if (n.deadZone >= n.tankHeight) return 'المسافة الميتة لازم تكون أقل من ارتفاع الخزان';
  return '';
}
function formSheet(title, fields, before, note) {
  const f = h('form', { class: 'form' });
  if (note) f.append(h('p', { class: 'meta' }, note));
  fields.forEach(x => f.append(x.type === 'check'
    ? h('label', { class: 'chk' }, x.label, h('input', { type: 'checkbox', name: x.k, ...(settings[x.k] ? { checked: '' } : {}) }))
    : h('label', {}, x.label, h('input', { name: x.k, type: x.type || 'text', value: settings[x.k] ?? '', ...(x.type === 'number' ? { step: 'any' } : {}) }))));
  f.append(h('button', { class: 'btn', type: 'submit' }, 'حفظ'));
  f.onsubmit = async e => {
    e.preventDefault();
    const next = { ...settings };
    fields.forEach(x => { const el = f.elements[x.k]; next[x.k] = x.type === 'check' ? el.checked : x.type === 'number' ? Number(el.value) : el.value.trim(); });
    const err = validate(next); if (err) return toast(err, 'warn');
    try {
      if (before) await before(next);
      settings = { ...DEFAULTS, ...(await api('/settings', 'PUT', next)) };
      toast('تم الحفظ', 'good'); closeSheet(); renderAll(); poll();
    } catch (x) { toast(x.message, 'warn'); }
  };
  openSheet(title, f);
}
function suppliersSheet() {
  const box = h('div');
  const save = async list => {
    try { settings = { ...DEFAULTS, ...(await api('/settings', 'PUT', { ...settings, suppliers: list })) }; draw(); }
    catch (e) { toast(e.message, 'warn'); }
  };
  const draw = () => {
    const list = settings.suppliers || [];
    box.replaceChildren(h('p', { class: 'meta' }, `المتبقي في الخزان: ${last.level ?? '--'}%. اتصل بمورّدك أو راسله واتساب.`));
    if (!list.length) box.append(h('p', { class: 'empty' }, 'ما أضفت مورّد صهريج بعد.'));
    list.forEach((s, i) => box.append(h('div', { class: 'sup' }, h('div', {}, h('b', {}, s.name), h('small', {}, s.phone)),
      h('a', { class: 'sq', href: 'tel:' + s.phone, 'aria-label': 'اتصال' }, '📞'),
      h('a', { class: 'sq', target: '_blank', rel: 'noopener', 'aria-label': 'واتساب', href: 'https://wa.me/' + waNum(s.phone) + '?text=' + encodeURIComponent('السلام عليكم، أبغى صهريج مياه لو سمحت.') }, '💬'),
      h('button', { class: 'sq', type: 'button', 'aria-label': 'حذف', onclick: () => save(list.filter((_, j) => j !== i)) }, '🗑'))));
    const f = h('form', { class: 'form add' }, h('label', {}, 'اسم المورّد', h('input', { name: 'n', required: '' })),
      h('label', {}, 'رقم الجوال', h('input', { name: 'p', type: 'tel', required: '' })), h('button', { class: 'btn ghost', type: 'submit' }, 'إضافة مورّد'));
    f.onsubmit = e => { e.preventDefault(); save([...list, { name: f.elements.n.value.trim(), phone: f.elements.p.value.trim() }]); };
    box.append(f);
  };
  draw(); openSheet('اطلب صهريج', box);
}
$('fab').onclick = $('orderBtn').onclick = suppliersSheet;

const ACTIONS = {
  device: () => formSheet('جهاز الحساس', [{ k: 'deviceId', label: 'رقم الجهاز (Device ID)' }], n => api('/device/link', 'POST', { deviceId: n.deviceId }), 'اكتب رقم الجهاز المكتوب في إعداد الحساس. اتركه فاضياً لفك الربط.'),
  tank: () => formSheet('إعدادات الخزان', [{ k: 'tankHeight', label: 'المسافة من الحساس إلى قاع الخزان (سم)', type: 'number' }, { k: 'deadZone', label: 'المسافة الميتة للحساس (سم)', type: 'number' }, { k: 'capacity', label: 'سعة الخزان (لتر)', type: 'number' }]),
  alerts: () => formSheet('حدود التنبيه', [{ k: 'low', label: 'منخفض عند (%)', type: 'number' }, { k: 'crit', label: 'حرج عند (%)', type: 'number' }, { k: 'repeatMin', label: 'تكرار التنبيه الحرج (دقائق)', type: 'number' }, { k: 'vibrate', label: 'اهتزاز عند التنبيه الحرج', type: 'check' }]),
  suppliers: suppliersSheet,
  notif: async () => {
    if (!('Notification' in window)) return toast('المتصفح لا يدعم الإشعارات', 'warn');
    const p = await Notification.requestPermission(); toast(p === 'granted' ? 'تم تفعيل الإشعارات' : 'الإشعارات مرفوضة من المتصفح', p === 'granted' ? 'good' : 'warn');
  },
  logout
};
document.querySelectorAll('[data-act]').forEach(b => b.onclick = () => ACTIONS[b.dataset.act]());

/* ---------- الانطلاق ---------- */
drawOnb();
setTimeout(() => {
  $('splash').classList.add('gone');
  if (store.get('token')) startApp();
  else if (store.get('onb')) $('auth').classList.remove('hidden');
  else $('onb').classList.remove('hidden');
}, 1400);
