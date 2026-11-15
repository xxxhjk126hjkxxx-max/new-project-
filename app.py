from __future__ import annotations

import io
import os
import sqlite3
from functools import wraps
from pathlib import Path

import qrcode
from flask import Flask, flash, jsonify, redirect, render_template, request, send_file, session, url_for
from openpyxl import Workbook
from werkzeug.security import check_password_hash, generate_password_hash

app = Flask(__name__)
app.config.update(
    SECRET_KEY=os.getenv("SECRET_KEY", "dev-only-change-this-secret"),
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    SESSION_COOKIE_SECURE=os.getenv("COOKIE_SECURE", "false").lower() == "true",
)

BASE_DIR = Path(__file__).resolve().parent
DB_PATH = Path(os.getenv("DATABASE_PATH", str(BASE_DIR / "attendance.db")))
QR_DIR = BASE_DIR / "static" / "qr"
QR_DIR.mkdir(parents=True, exist_ok=True)
DB_PATH.parent.mkdir(parents=True, exist_ok=True)
ADMIN_USERNAME = os.getenv("ADMIN_USERNAME", "admin")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "admin123")


def get_db():
    conn = sqlite3.connect(DB_PATH, timeout=15)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db():
    with get_db() as conn:
        conn.executescript("""
        CREATE TABLE IF NOT EXISTS users (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          username TEXT UNIQUE NOT NULL,
          password_hash TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS students (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          student_number TEXT UNIQUE NOT NULL,
          name TEXT NOT NULL,
          grade_group TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS lectures (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          name TEXT NOT NULL,
          lecture_date TEXT NOT NULL,
          lecture_time TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS attendance (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          lecture_id INTEGER NOT NULL REFERENCES lectures(id) ON DELETE CASCADE,
          student_id INTEGER NOT NULL REFERENCES students(id) ON DELETE CASCADE,
          checked_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
          UNIQUE(lecture_id, student_id)
        );
        """)
        user = conn.execute("SELECT id FROM users WHERE username=?", (ADMIN_USERNAME,)).fetchone()
        if user is None:
            conn.execute("INSERT INTO users(username,password_hash) VALUES(?,?)",
                         (ADMIN_USERNAME, generate_password_hash(ADMIN_PASSWORD)))


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if "user_id" not in session:
            return redirect(url_for("login"))
        return view(*args, **kwargs)
    return wrapped


def student_qr_path(student_id: int) -> Path:
    return QR_DIR / f"{student_id}.png"


def generate_student_qr(student_id: int, student_number: str) -> str:
    path = student_qr_path(student_id)
    if not path.exists():
        qr = qrcode.QRCode(box_size=10, border=4)
        qr.add_data(f"student_id:{student_number}")
        qr.make(fit=True)
        qr.make_image(fill_color="#103b70", back_color="white").save(path)
    return url_for("static", filename=f"qr/{student_id}.png")


def student_number_from_qr(payload: str) -> str | None:
    value = (payload or "").strip()
    if value.lower().startswith("student_id:"):
        value = value.split(":", 1)[1].strip()
    return value or None


@app.before_request
def bootstrap():
    init_db()


@app.route("/")
def index():
    return redirect(url_for("dashboard" if session.get("user_id") else "login"))


@app.route("/login", methods=["GET", "POST"])
def login():
    if session.get("user_id"):
        return redirect(url_for("dashboard"))
    if request.method == "POST":
        username = (request.form.get("username") or "").strip()
        password = request.form.get("password") or ""
        with get_db() as conn:
            user = conn.execute("SELECT * FROM users WHERE username=?", (username,)).fetchone()
        if user and check_password_hash(user["password_hash"], password):
            session.clear()
            session["user_id"] = user["id"]
            session["username"] = user["username"]
            return redirect(url_for("dashboard"))
        flash("اسم المستخدم أو كلمة المرور غير صحيحة", "error")
    return render_template("login.html")


@app.route("/logout", methods=["POST"])
def logout():
    session.clear()
    return redirect(url_for("login"))


@app.route("/dashboard")
@login_required
def dashboard():
    with get_db() as conn:
        stats = {
            "total_students": conn.execute("SELECT COUNT(*) FROM students").fetchone()[0],
            "total_lectures": conn.execute("SELECT COUNT(*) FROM lectures").fetchone()[0],
            "total_attendance": conn.execute("SELECT COUNT(*) FROM attendance").fetchone()[0],
        }
        lectures = conn.execute("SELECT * FROM lectures ORDER BY lecture_date DESC, lecture_time DESC LIMIT 8").fetchall()
    return render_template("dashboard.html", stats=stats, lectures=lectures)


@app.route("/students", methods=["GET", "POST"])
@login_required
def students():
    if request.method == "POST":
        action = request.form.get("action")
        sid = request.form.get("student_id", type=int)
        if action in ("create", "update"):
            name = (request.form.get("name") or "").strip()
            number = (request.form.get("student_number") or "").strip()
            group = (request.form.get("grade_group") or "").strip()
            if not all((name, number, group)):
                flash("يرجى تعبئة جميع الحقول", "error")
            else:
                try:
                    with get_db() as conn:
                        if action == "create":
                            conn.execute("INSERT INTO students(student_number,name,grade_group) VALUES(?,?,?)", (number,name,group))
                            flash("تمت إضافة الطالب", "success")
                        elif sid:
                            conn.execute("UPDATE students SET student_number=?,name=?,grade_group=? WHERE id=?", (number,name,group,sid))
                            old_qr = student_qr_path(sid)
                            if old_qr.exists():
                                old_qr.unlink()
                            flash("تم تحديث بيانات الطالب", "success")
                except sqlite3.IntegrityError:
                    flash("رقم الطالب مستخدم بالفعل", "error")
        elif action == "delete" and sid:
            with get_db() as conn:
                conn.execute("DELETE FROM students WHERE id=?", (sid,))
            student_qr_path(sid).unlink(missing_ok=True)
            flash("تم حذف الطالب", "success")
        return redirect(url_for("students"))
    with get_db() as conn:
        rows = conn.execute("SELECT * FROM students ORDER BY name").fetchall()
    return render_template("students.html", students=rows)


@app.route("/students/<int:student_id>/qr")
@login_required
def student_qr(student_id):
    with get_db() as conn:
        student = conn.execute("SELECT * FROM students WHERE id=?", (student_id,)).fetchone()
    if not student:
        flash("الطالب غير موجود", "error")
        return redirect(url_for("students"))
    return render_template("student_qr.html", student=student, qr_url=generate_student_qr(student_id, student["student_number"]))


@app.route("/students/<int:student_id>/download_qr")
@login_required
def download_qr(student_id):
    with get_db() as conn:
        student = conn.execute("SELECT * FROM students WHERE id=?", (student_id,)).fetchone()
    if not student:
        flash("الطالب غير موجود", "error")
        return redirect(url_for("students"))
    generate_student_qr(student_id, student["student_number"])
    return send_file(student_qr_path(student_id), as_attachment=True, download_name=f"qr_{student['student_number']}.png", mimetype="image/png")


@app.route("/lectures", methods=["GET", "POST"])
@login_required
def lectures():
    if request.method == "POST":
        values = [(request.form.get(k) or "").strip() for k in ("name", "lecture_date", "lecture_time")]
        if not all(values):
            flash("يرجى تعبئة اسم المحاضرة والتاريخ والوقت", "error")
        else:
            with get_db() as conn:
                conn.execute("INSERT INTO lectures(name,lecture_date,lecture_time) VALUES(?,?,?)", values)
            flash("تم إنشاء المحاضرة", "success")
        return redirect(url_for("lectures"))
    with get_db() as conn:
        rows = conn.execute("SELECT * FROM lectures ORDER BY lecture_date DESC,lecture_time DESC").fetchall()
    return render_template("lectures.html", lectures=rows)


@app.route("/attendance/<int:lecture_id>")
@login_required
def attendance_page(lecture_id):
    with get_db() as conn:
        lecture = conn.execute("SELECT * FROM lectures WHERE id=?", (lecture_id,)).fetchone()
    if not lecture:
        flash("المحاضرة غير موجودة", "error")
        return redirect(url_for("lectures"))
    return render_template("attendance.html", lecture=lecture)


@app.route("/api/scan", methods=["POST"])
@login_required
def api_scan():
    data = request.get_json(silent=True) or {}
    lecture_id = data.get("lecture_id")
    student_number = student_number_from_qr(str(data.get("qr_data") or ""))
    if not isinstance(lecture_id, int) or not student_number:
        return jsonify(success=False, message="رمز QR أو بيانات المحاضرة غير صالحة"), 400
    with get_db() as conn:
        if not conn.execute("SELECT 1 FROM lectures WHERE id=?", (lecture_id,)).fetchone():
            return jsonify(success=False, message="المحاضرة غير موجودة"), 404
        student = conn.execute("SELECT * FROM students WHERE student_number=?", (student_number,)).fetchone()
        if not student:
            return jsonify(success=False, message="الطالب غير موجود"), 404
        try:
            conn.execute("INSERT INTO attendance(lecture_id,student_id) VALUES(?,?)", (lecture_id, student["id"]))
        except sqlite3.IntegrityError:
            return jsonify(success=False, message=f"{student['name']} مسجل مسبقاً في هذه المحاضرة"), 409
    return jsonify(success=True, message=f"تم تسجيل حضور {student['name']} بنجاح")


@app.route("/reports")
@login_required
def reports():
    lecture_id = request.args.get("lecture_id", type=int)
    with get_db() as conn:
        lectures = conn.execute("SELECT * FROM lectures ORDER BY lecture_date DESC,lecture_time DESC").fetchall()
        selected = conn.execute("SELECT * FROM lectures WHERE id=?", (lecture_id,)).fetchone() if lecture_id else None
        present = conn.execute("SELECT s.*,a.checked_at FROM attendance a JOIN students s ON s.id=a.student_id WHERE a.lecture_id=? ORDER BY s.name", (lecture_id,)).fetchall() if selected else []
        all_students = conn.execute("SELECT * FROM students ORDER BY name").fetchall() if selected else []
        counts = conn.execute("SELECT s.id,COUNT(a.id) AS attendance_count FROM students s LEFT JOIN attendance a ON a.student_id=s.id GROUP BY s.id").fetchall()
    present_ids = {row["id"] for row in present}
    absent = [row for row in all_students if row["id"] not in present_ids]
    return render_template("reports.html", lectures=lectures, selected=selected, present=present, absent=absent, counts={row["id"]: row["attendance_count"] for row in counts})


@app.route("/reports/export/<int:lecture_id>")
@login_required
def export_excel(lecture_id):
    with get_db() as conn:
        lecture = conn.execute("SELECT * FROM lectures WHERE id=?", (lecture_id,)).fetchone()
        if not lecture:
            flash("المحاضرة غير موجودة", "error")
            return redirect(url_for("reports"))
        students = conn.execute("SELECT s.student_number,s.name,s.grade_group,a.checked_at FROM students s LEFT JOIN attendance a ON a.student_id=s.id AND a.lecture_id=? ORDER BY s.name", (lecture_id,)).fetchall()
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "تقرير الحضور"
    sheet.append(["اسم المحاضرة", lecture["name"]])
    sheet.append(["التاريخ", lecture["lecture_date"], "الوقت", lecture["lecture_time"]])
    sheet.append([])
    sheet.append(["رقم الطالب", "الاسم", "الصف / المجموعة", "الحالة", "وقت التسجيل"])
    for student in students:
        sheet.append([student["student_number"], student["name"], student["grade_group"], "حاضر" if student["checked_at"] else "غائب", student["checked_at"] or "-"])
    for column, width in {"A": 20, "B": 28, "C": 24, "D": 14, "E": 24}.items():
        sheet.column_dimensions[column].width = width
    output = io.BytesIO()
    workbook.save(output)
    output.seek(0)
    return send_file(output, as_attachment=True, download_name=f"attendance_{lecture_id}.xlsx", mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", "5000")), debug=os.getenv("FLASK_DEBUG") == "1")
