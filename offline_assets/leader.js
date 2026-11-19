import {openDatabase, addStudent, addLecture, snapshot, lectureAttendance, recordAttendance} from './db.js';

const byId = id => document.getElementById(id);
const buttons = [...document.querySelectorAll('[data-panel]')];
const scanLecture = byId('scan-lecture');
const reportLecture = byId('report-lecture');
const video = byId('camera');
const canvas = document.createElement('canvas');
const context = canvas.getContext('2d', {willReadFrequently: true});
const numbers = new Intl.NumberFormat('ar', {numberingSystem: 'arab'});
const timeFormat = new Intl.DateTimeFormat('ar', {dateStyle: 'short', timeStyle: 'short'});
let db;
let data = {students: [], lectures: [], count: 0};
let activePanel = 'students';
let report = [];
let reportRequest = 0;
let cameraStream;
let cameraRun = 0;
let scanTimer;
let busy = false;
let shownPayload;
let payloadSeenAt = 0;

function status(id, text, kind = '') {
  const el = byId(id);
  el.textContent = text;
  el.dataset.kind = kind;
  el.hidden = !text;
}

function prepareOffline() {
  if (!window.isSecureContext || !('serviceWorker' in navigator)) {
    status('offline-status', 'استخدم HTTPS أو localhost لتفعيل الكاميرا والعمل بلا اتصال', 'error');
    return;
  }
  const worker = navigator.serviceWorker;
  let ready = false;
  const timer = setTimeout(() => {
    if (!ready) status('offline-status', 'لم يكتمل تجهيز التطبيق بلا اتصال', 'error');
  }, 12000);
  function update() {
    if (worker.controller) {
      ready = true;
      clearTimeout(timer);
      status('offline-status', 'جاهز للعمل بلا إنترنت', 'success');
    }
  }
  worker.addEventListener('controllerchange', update);
  update();
  worker.register('/sw.js').then(update).catch(() => {
    if (!ready) {
      clearTimeout(timer);
      status('offline-status', 'تعذّر تجهيز التطبيق بلا اتصال', 'error');
    }
  });
}

function listItem(title, metadata, action, handle) {
  const li = document.createElement('li');
  const block = document.createElement('div');
  const name = document.createElement('strong');
  const sub = document.createElement('small');
  name.textContent = title;
  sub.textContent = metadata;
  block.append(name, sub);
  li.append(block);
  if (action) {
    const button = document.createElement('button');
    button.type = 'button';
    button.textContent = action;
    button.addEventListener('click', handle);
    li.append(button);
  }
  return li;
}

function fillLectures(select) {
  const choice = select.value;
  const options = data.lectures.map(item => new Option(`${item.name} · ${item.date} ${item.time}`, item.id));
  select.replaceChildren(new Option('اختر محاضرة', ''), ...options);
  select.value = data.lectures.some(item => String(item.id) === choice) ? choice : '';
  if (!select.value && data.lectures.length === 1) select.value = String(data.lectures[0].id);
}

async function refresh() {
  data = await snapshot(db);
  data.lectures.sort((a, b) => `${b.date} ${b.time}`.localeCompare(`${a.date} ${a.time}`) || b.id - a.id);
  byId('student-count').textContent = numbers.format(data.students.length);
  byId('lecture-count').textContent = numbers.format(data.lectures.length);
  byId('attendance-count').textContent = numbers.format(data.count);
  byId('students-empty').hidden = data.students.length > 0;
  byId('lectures-empty').hidden = data.lectures.length > 0;
  byId('student-list').replaceChildren(...data.students.map(student => listItem(
    student.name, [student.number, student.group].filter(Boolean).join(' · '), 'كود الطالب', () => showCode(student),
  )));
  byId('lecture-list').replaceChildren(...data.lectures.map(lecture => listItem(
    lecture.name, `${lecture.date} · ${lecture.time}`, 'تسجيل الحضور', () => {
      scanLecture.value = String(lecture.id);
      setPanel('scan');
    },
  )));
  fillLectures(scanLecture);
  fillLectures(reportLecture);
}

function showCode(student) {
  byId('invite-student').textContent = student.name;
  byId('invite-code').value = AttendanceCode.format(student.code);
  status('invite-message', '');
  byId('invite-dialog').showModal();
}

byId('share-code').hidden = !navigator.share;
byId('share-code').addEventListener('click', async () => {
  try {
    await navigator.share({text: byId('invite-code').value});
  } catch (error) {
    if (error.name !== 'AbortError') status('invite-message', 'تعذّرت المشاركة. انسخ الكود يدوياً.');
  }
});
byId('copy-code').addEventListener('click', async () => {
  const input = byId('invite-code');
  try {
    await navigator.clipboard.writeText(input.value);
    status('invite-message', 'تم نسخ الكود.', 'success');
  } catch {
    input.focus();
    input.select();
    status('invite-message', 'حدّدنا لك الكود. انسخه باستخدام قائمة الجهاز.');
  }
});

function saveForm(id, commit) {
  byId(id).addEventListener('submit', async event => {
    event.preventDefault();
    const form = event.currentTarget;
    const values = Object.fromEntries([...new FormData(form)].map(([k, v]) => [k, v.trim()]));
    const button = form.querySelector('button[type=submit]');
    if (button.disabled) return;
    button.disabled = true;
    try {
      await commit(values);
      form.reset();
      await refresh();
    } catch (error) {
      const duplicate = id === 'student-form' && error.name === 'ConstraintError';
      status('global-message', duplicate ? 'هذا الرقم الجامعي مسجل بالفعل.' : (error.userMessage || 'تعذّر حفظ البيانات في هذا المتصفح.'), 'error');
    } finally {
      button.disabled = false;
    }
  });
}
function invalid(userMessage) { return Object.assign(new Error(userMessage), {userMessage}); }
saveForm('student-form', async values => {
  if (!values.name || !values.number) throw invalid('أدخل اسم الطالب ورقمه الجامعي.');
  await addStudent(db, {...values, code: AttendanceCode.create()});
  status('global-message', 'تمت إضافة الطالب. اضغط «كود الطالب» لإرساله له.', 'success');
  navigator.storage?.persist?.().catch(() => {});
});
saveForm('lecture-form', async values => {
  if (!values.name || !values.date || !values.time) throw invalid('أدخل اسم المحاضرة والتاريخ والوقت.');
  await addLecture(db, values);
  status('global-message', 'تمت إضافة المحاضرة.', 'success');
});

function setPanel(panel) {
  if (activePanel !== panel) status('global-message', '');
  if (panel !== 'scan') stopCamera();
  activePanel = panel;
  for (const button of buttons) {
    const selected = button.dataset.panel === panel;
    if (selected) button.setAttribute('aria-current', 'true');
    else button.removeAttribute('aria-current');
    byId(button.getAttribute('aria-controls')).hidden = !selected;
  }
  if (panel === 'reports') updateReport();
  if (panel === 'scan') describeScan();
}
for (const button of buttons) button.addEventListener('click', () => setPanel(button.dataset.panel));

function describeScan() {
  const chosen = !!scanLecture.value;
  byId('start-camera').disabled = !chosen;
  byId('pick-qr').disabled = !chosen;
  if (!chosen) status('scan-message', 'اختر المحاضرة لتبدأ المسح.');
  else status('scan-message', cameraStream ? 'وجّه الكاميرا إلى رمز الطالب.' : 'شغّل الكاميرا أو اختر صورة للرمز.');
}
scanLecture.addEventListener('change', () => {
  stopCamera();
  describeScan();
});

async function registerPayload(payload) {
  const code = AttendanceCode.decode(payload);
  const lectureId = Number(scanLecture.value);
  if (!lectureId) return;
  if (!code) return status('scan-message', 'هذا ليس رمز حضور من قسم الطالب.', 'error');
  if (busy) return;
  busy = true;
  const notify = (text, kind) => {
    if (Number(scanLecture.value) === lectureId) status('scan-message', text, kind);
  };
  try {
    const result = await recordAttendance(db, lectureId, code);
    if (result.kind === 'saved') {
      notify(`تم تسجيل حضور ${result.student.name}.`, 'success');
      await refresh();
    } else if (result.kind === 'duplicate') {
      notify(`${result.student.name} مسجّل بالفعل في هذه المحاضرة.`);
    } else if (result.kind === 'unknown-student') {
      notify('هذا الكود لا يطابق أي طالب على هذا الهاتف.', 'error');
    } else {
      notify('المحاضرة غير موجودة على هذا الهاتف.', 'error');
    }
  } catch {
    notify('تعذّر تسجيل الحضور في قاعدة البيانات المحلية.', 'error');
  } finally {
    busy = false;
  }
}

function decodeImage(image, width, height, maxSide) {
  if (!width || !height) return null;
  const scale = Math.min(1, maxSide / Math.max(width, height));
  canvas.width = Math.max(1, Math.round(width * scale));
  canvas.height = Math.max(1, Math.round(height * scale));
  context.fillStyle = '#ffffff';
  context.fillRect(0, 0, canvas.width, canvas.height);
  context.drawImage(image, 0, 0, canvas.width, canvas.height);
  const pixels = context.getImageData(0, 0, canvas.width, canvas.height);
  return jsQR(pixels.data, pixels.width, pixels.height, {inversionAttempts: 'dontInvert'});
}

function stopCamera() {
  cameraRun++;
  clearTimeout(scanTimer);
  cameraStream?.getTracks().forEach(track => track.stop());
  cameraStream = undefined;
  video.srcObject = null;
  shownPayload = undefined;
  byId('scanner-view').hidden = true;
  byId('stop-camera').hidden = true;
  byId('start-camera').hidden = false;
}

function cameraLoop(run) {
  if (run !== cameraRun) return;
  if (!busy && video.readyState >= 2) {
    try {
      const result = decodeImage(video, video.videoWidth, video.videoHeight, 640);
      const now = performance.now();
      if (result) {
        payloadSeenAt = now;
        if (shownPayload !== result.data) {
          shownPayload = result.data;
          registerPayload(result.data);
        }
      } else if (now - payloadSeenAt > 650) {
        shownPayload = undefined;
      }
    } catch {
      stopCamera();
      status('scan-message', 'تعذّرت قراءة الكاميرا. جرّب قراءة صورة للرمز.', 'error');
      return;
    }
  }
  scanTimer = setTimeout(() => cameraLoop(run), 140);
}

byId('start-camera').addEventListener('click', async () => {
  if (!scanLecture.value) return;
  if (!navigator.mediaDevices?.getUserMedia) {
    status('scan-message', 'فتح الكاميرا يتطلب HTTPS أو localhost. يمكنك قراءة صورة للرمز بدلاً من ذلك.', 'error');
    return;
  }
  const run = ++cameraRun;
  byId('start-camera').hidden = true;
  byId('stop-camera').hidden = false;
  status('scan-message', 'جارٍ طلب إذن استخدام الكاميرا…');
  try {
    const stream = await navigator.mediaDevices.getUserMedia({audio: false, video: {facingMode: {ideal: 'environment'}}});
    if (run !== cameraRun) {
      stream.getTracks().forEach(track => track.stop());
      return;
    }
    cameraStream = stream;
    stream.getVideoTracks().forEach(track => track.addEventListener('ended', () => {
      if (cameraRun === run) {
        stopCamera();
        status('scan-message', 'توقفت الكاميرا. يمكنك تشغيلها من جديد.');
      }
    }));
    video.srcObject = stream;
    byId('scanner-view').hidden = false;
    await video.play();
    if (run !== cameraRun) return;
    describeScan();
    cameraLoop(run);
  } catch {
    if (run === cameraRun) {
      stopCamera();
      status('scan-message', 'تعذّر فتح الكاميرا. تحقق من الإذن أو جرّب قراءة صورة للرمز.', 'error');
    }
  }
});
byId('stop-camera').addEventListener('click', () => { stopCamera(); describeScan(); });
window.addEventListener('pagehide', stopCamera);
document.addEventListener('visibilitychange', () => {
  if (document.hidden) stopCamera();
  else if (activePanel === 'scan') describeScan();
});

byId('pick-qr').addEventListener('click', () => { stopCamera(); byId('qr-image').click(); });
byId('qr-image').addEventListener('change', async event => {
  const input = event.currentTarget;
  const file = input.files[0];
  input.value = '';
  if (!file) return;
  if (file.size > 20 * 1024 * 1024) return status('scan-message', 'اختر صورة بحجم أقل من ٢٠ ميغابايت.', 'error');
  const lectureId = scanLecture.value;
  const url = URL.createObjectURL(file);
  try {
    const image = new Image();
    image.src = url;
    await image.decode();
    if (activePanel !== 'scan' || scanLecture.value !== lectureId) return;
    const result = decodeImage(image, image.naturalWidth, image.naturalHeight, 1350);
    if (!result) return status('scan-message', 'لم نجد رمز QR واضحاً في الصورة.', 'error');
    await registerPayload(result.data);
  } catch {
    status('scan-message', 'تعذّرت قراءة هذا الملف كصورة.', 'error');
  } finally {
    URL.revokeObjectURL(url);
  }
});

async function updateReport() {
  const request = ++reportRequest;
  const id = Number(reportLecture.value);
  report = [];
  byId('report-list').replaceChildren();
  byId('export-report').disabled = true;
  byId('reports-empty').hidden = false;
  byId('reports-empty').textContent = id ? 'جارٍ قراءة التقرير…' : 'اختر محاضرة لعرض الحضور.';
  if (!id) return;
  try {
    const rows = await lectureAttendance(db, id);
    if (reportRequest !== request) return;
    const times = new Map(rows.map(row => [row.studentId, row.checkedAt]));
    report = data.students.map(student => ({student, checkedAt: times.get(student.id)}));
    byId('reports-empty').textContent = `${numbers.format(rows.length)} حاضر · ${numbers.format(report.length - rows.length)} غائب`;
    byId('report-list').replaceChildren(...report.map(({student, checkedAt}) => listItem(student.name,
      [student.number, checkedAt ? `حاضر · ${timeFormat.format(new Date(checkedAt))}` : 'غائب'].join(' · '),
    )));
    byId('export-report').disabled = !report.length;
  } catch {
    if (reportRequest === request) byId('reports-empty').textContent = 'تعذّرت قراءة التقرير المحلي.';
  }
}
reportLecture.addEventListener('change', updateReport);
function csvCell(value) {
  const raw = String(value);
  const safe = /^[\s]*[=+\-@]|^[\t\r\n]/.test(raw) ? "'" + raw : raw;
  return '"' + safe.replace(/"/g, '""') + '"';
}
byId('export-report').addEventListener('click', () => {
  const rows = [['الرقم الجامعي', 'الاسم', 'المجموعة', 'الحالة', 'وقت التسجيل (UTC)'],
    ...report.map(({student, checkedAt}) => [student.number, student.name, student.group, checkedAt ? 'حاضر' : 'غائب', checkedAt || ''])];
  const csv = '\ufeff' + rows.map(row => row.map(csvCell).join(',')).join('\r\n');
  const url = URL.createObjectURL(new Blob([csv], {type: 'text/csv;charset=utf-8'}));
  const link = document.createElement('a');
  link.href = url;
  link.download = `attendance-${reportLecture.value}.csv`;
  link.click();
  setTimeout(() => URL.revokeObjectURL(url), 1500);
});

prepareOffline();
try {
  db = await openDatabase();
  await refresh();
  byId('app-controls').disabled = false;
  describeScan();
} catch {
  status('global-message', 'تعذّر فتح قاعدة البيانات المحلية. استخدم متصفحاً يدعم IndexedDB ولا تستخدم التصفح الخاص.', 'error');
}
