const DB_NAME = 'iua-leader-attendance';

export function openDatabase() {
  return new Promise((resolve, reject) => {
    const request = indexedDB.open(DB_NAME, 1);
    request.onupgradeneeded = () => {
      const db = request.result;
      const students = db.createObjectStore('students', {keyPath: 'id', autoIncrement: true});
      students.createIndex('number', 'number', {unique: true});
      students.createIndex('code', 'code', {unique: true});
      db.createObjectStore('lectures', {keyPath: 'id', autoIncrement: true});
      const attendance = db.createObjectStore('attendance', {keyPath: ['lectureId', 'studentId']});
      attendance.createIndex('lecture', 'lectureId');
    };
    request.onsuccess = () => {
      request.result.onversionchange = () => request.result.close();
      resolve(request.result);
    };
    request.onerror = () => reject(request.error);
    request.onblocked = () => reject(new Error('Database upgrade blocked by another tab'));
  });
}

function transact(db, stores, mode, run) {
  return new Promise((resolve, reject) => {
    const tx = db.transaction(stores, mode);
    let result;
    tx.oncomplete = () => resolve(result);
    tx.onabort = () => reject(tx.error || new Error('IndexedDB transaction aborted'));
    run(tx, value => { result = value; });
  });
}

function add(db, store, value) {
  return transact(db, [store], 'readwrite', (tx, done) => {
    const request = tx.objectStore(store).add(value);
    request.onsuccess = () => done(request.result);
  });
}

export const addStudent = (db, value) => add(db, 'students', value);
export const addLecture = (db, value) => add(db, 'lectures', value);

export function snapshot(db) {
  return transact(db, ['students', 'lectures', 'attendance'], 'readonly', (tx, done) => {
    const result = {};
    for (const store of ['students', 'lectures']) {
      const request = tx.objectStore(store).getAll();
      request.onsuccess = () => { result[store] = request.result; };
    }
    const count = tx.objectStore('attendance').count();
    count.onsuccess = () => { result.count = count.result; };
    done(result);
  });
}

export function lectureAttendance(db, lectureId) {
  return transact(db, ['attendance'], 'readonly', (tx, done) => {
    const request = tx.objectStore('attendance').index('lecture').getAll(lectureId);
    request.onsuccess = () => done(request.result);
  });
}

export function recordAttendance(db, lectureId, code) {
  // The lookup, duplicate check and insert share one transaction; concurrent tabs
  // cannot record the same student twice in the same lecture.
  return transact(db, ['students', 'lectures', 'attendance'], 'readwrite', (tx, done) => {
    const lectures = tx.objectStore('lectures');
    const students = tx.objectStore('students');
    const attendance = tx.objectStore('attendance');
    const lecture = lectures.get(lectureId);
    lecture.onsuccess = () => {
      if (!lecture.result) return done({kind: 'unknown-lecture'});
      const lookup = students.index('code').get(code);
      lookup.onsuccess = () => {
        const student = lookup.result;
        if (!student) return done({kind: 'unknown-student'});
        const previous = attendance.get([lectureId, student.id]);
        previous.onsuccess = () => {
          if (previous.result) return done({kind: 'duplicate', student});
          const insert = attendance.add({lectureId, studentId: student.id, checkedAt: new Date().toISOString()});
          insert.onsuccess = () => done({kind: 'saved', student});
        };
      };
    };
  });
}
