(() => {
  const form = document.getElementById('student-code-form');
  const input = document.getElementById('student-token');
  const output = document.getElementById('student-code');
  const message = document.getElementById('student-status');
  const forget = document.getElementById('forget-code');
  const key = 'iua.student.code.v1';

  function status(text, kind) {
    message.textContent = text;
    message.dataset.kind = kind;
    message.hidden = !text;
  }

  function render(code) {
    output.replaceChildren();
    output.hidden = true;
    if (!code) {
      status('الكود غير صالح. أدخل الكود المكوّن من ١٦ حرفاً ورقماً كما أعطاك إياه الليدر.', 'error');
      return;
    }
    const qr = qrcode(0, 'M');
    qr.addData(AttendanceCode.encode(code));
    qr.make();
    // Only the fixed-format token is handed to the locally bundled QR encoder.
    output.innerHTML = qr.createSvgTag({cellSize: 8, margin: 32, scalable: true});
    output.hidden = false;
    forget.hidden = false;
    input.value = AttendanceCode.format(code);
    status('الرمز جاهز. اعرضه على هاتف الليدر.', 'success');
    try { localStorage.setItem(key, code); } catch { /* May be disabled for local files. */ }
  }

  form.addEventListener('submit', event => {
    event.preventDefault();
    render(AttendanceCode.normalize(input.value));
  });
  input.addEventListener('input', () => {
    output.hidden = true;
    output.replaceChildren();
    status('', '');
  });
  forget.addEventListener('click', () => {
    try { localStorage.removeItem(key); } catch { /* Storage is optional. */ }
    input.value = '';
    output.hidden = true;
    output.replaceChildren();
    forget.hidden = true;
    status('', '');
    input.focus();
  });
  let stored;
  try { stored = localStorage.getItem(key); } catch { /* Storage is optional. */ }
  if (stored) render(AttendanceCode.normalize(stored));

  const ready = document.getElementById('student-ready');
  if (!ready) return; // The standalone file is already offline-capable.
  const worker = navigator.serviceWorker;
  function showAvailability(available) {
    ready.textContent = available ? 'جاهز للعمل بلا إنترنت' : 'لتعمل بلا اتصال، احفظ ملف قسم الطالب أدناه';
    ready.dataset.kind = available ? 'success' : '';
  }
  if (!worker) {
    showAvailability(false);
    return;
  }
  const timer = setTimeout(() => showAvailability(!!worker.controller), 12000);
  function checkAvailability() {
    if (!worker.controller) return;
    clearTimeout(timer);
    showAvailability(true);
  }
  worker.addEventListener('controllerchange', checkAvailability);
  checkAvailability();
  worker.register('/sw.js').then(checkAvailability).catch(() => {
    clearTimeout(timer);
    showAvailability(!!worker.controller);
  });
})();
