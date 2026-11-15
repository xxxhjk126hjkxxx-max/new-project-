from __future__ import annotations

import io
import os
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any

import qrcode
from flask import (
    Flask,
    flash,
    jsonify,
    redirect,
    render_template,
    request,
    send_file,
    session,
    url_for,
)
from openpyxl import Workbook
from werkzeug.security import check_password_hash, generate_password_hash

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "change-this-secret-key")

BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "attendance.db"
QR_DIR = BASE_DIR / "static" / "qr"
QR_DIR.mkdir(exist_ok=True, parents=True)

ADMIN_USERNAME = os.getenv("ADMIN_USERNAME", "admin")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "admin123")


def get_db() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db() -> None:
    conn = get_db()
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS students (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            student_number TEXT UNIQUE NOT NULL,
            name TEXT NOT NULL,
            grade_group TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS lectures (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            lecture_date TEXT NOT NULL,
            lecture_time TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS attendance (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            lecture_id INTEGER NOT NULL,
            student_id INTEGER NOT NULL,
            checked_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(lecture_id, student_id),
            FOREIGN KEY (lecture_id) REFERENCES lectures(id) ON DELETE CASCADE,
            FOREIGN KEY (student_id) REFERENCES students(id) ON DELETE CASCADE
        )
        """
    )
    conn.commit()
    conn.close()


def ensure_admin_user() -> None:
    conn = get_db()
    user = conn.execute("SELECT * FROM users WHERE username = ?", (ADMIN_USERNAME,)).fetchone()
    if user is None:
        conn.execute(
            "INSERT INTO users (username, password_hash) VALUES (?, ?)",
            (ADMIN_USERNAME, generate_password_hash(ADMIN_PASSWORD)),
        )
        conn.commit()
    conn.close()


def login_required(view):
    def wrapped(*args, **kwargs):
        if "user_id" not in session:
            return redirect(url_for("login"))
        return view(*args, **kwargs)

    wrapped.__name__ = view.__name__
    return wrapped


def generate_student_qr(student_id: int, student_number: str) -> str:
    qr_path = QR_DIR / f"{student_id}.png"
    if not qr_path.exists():
        payload = f"student_id:{student_number}"
        qr = qrcode.QRCode(version=1, box_size=10, border=4)
        qr.add_data(payload)
        qr.make(fit=True)
        image = qr.make_image(fill_color="#0d3b66", back_color="white")
        image.save(qr_path)
    return f"/static/qr/{student_id}.png"


def parse_qr_payload(payload: str) -> str | None:
    value = (payload or "").strip()
    if not value:
        return None
    if value.lower().startswith("student_id:"):
        return value.split(":", 1)[1].strip()
    if value.isdigit():
        return value
    return None


def fetch_student_by_number(student_number: str):
    conn = get_db()
    student = conn.execute(
        "SELECT * FROM students WHERE student_number = ?",
        (student_number,),
    ).fetchone()
    conn.close()
    return student


def fetch_dashboard_stats():
    conn = get_db()
    total_students = conn.execute("SELECT COUNT(*) FROM students").fetchone()[0]
    total_lectures = conn.execute("SELECT COUNT(*) FROM lectures").fetchone()[0]
    total_attendance = conn.execute("SELECT COUNT(*) FROM attendance").fetchone()[0]
    latest = conn.execute(
        "SELECT COUNT(*) FROM students s LEFT JOIN attendance a ON a.student_id = s.id WHERE a.id IS NOT NULL"
    ).fetchone()[0]
    conn.close()
    return {
        "total_students": total_students,
        "total_lectures": total_lectures,
        "total_attendance": total_attendance,
        "attendance_rows": latest,
    }


def get_lecture_summary(lecture_id: int):
    conn = get_db()
    lecture = conn.execute("SELECT * FROM lectures WHERE id = ?", (lecture_id,)).fetchone()
    present = conn.execute(
        """
        SELECT s.*
        FROM attendance a
        JOIN students s ON s.id = a.student_id
        WHERE a.lecture_id = ?
        ORDER BY s.name ASC
        """,
        (lecture_id,),
    ).fetchall()
    all_students = conn.execute("SELECT * FROM students ORDER BY name ASC").fetchall()
    conn.close()
    present_ids = {row["id"] for row in present}
    absent = [s for s in all_students if s["id"] not in present_ids]
    return lecture, present, absent


@app.before_request
def bootstrap():
    init_db()
    ensure_admin_user()


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = (request.form.get("username") or "").strip()
        password = request.form.get("password") or ""
        conn = get_db()
        user = conn.execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()
        conn.close()

        if user and check_password_hash(user["password_hash"], password):
            session["user_id"] = user["id"]
            session["username"] = user["username"]
            flash("تم تسجيل الدخول بنجاح", "success")
            return redirect(url_for("dashboard"))

        flash("اسم المستخدم أو كلمة المرور غير صحيحة", "error")

    return render_template("login.html")


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


@app.route("/")
@login_required
def dashboard():
    lectures = []
    conn = get_db()
    lectures = conn.execute(
        "SELECT * FROM lectures ORDER BY lecture_date DESC, lecture_time DESC LIMIT 10"
    ).fetchall()
    conn.close()
    stats = fetch_dashboard_stats()
    return render_template("dashboard.html", lectures=lectures, stats=stats)


@app.route("/students", methods=["GET", "POST"])
@login_required
def students():
    if request.method == "POST":
        action = request.form.get("action")
        if action == "create":
            name = (request.form.get("name") or "").strip()
            student_number = (request.form.get("student_number") or "").strip()
            grade_group = (request.form.get("grade_group") or "").strip()

            if not all([name, student_number, grade_group]):
                flash("يرجى تعبئة جميع الحقول", "error")
                return redirect(url_for("students"))

            conn = get_db()
            try:
                conn.execute(
                    "INSERT INTO students (student_number, name, grade_group) VALUES (?, ?, ?)",
                    (student_number, name, grade_group),
                )
                conn.commit()
                flash("تمت إضافة الطالب بنجاح", "success")
            except sqlite3.IntegrityError:
                flash("رقم الطالب موجود بالفعل", "error")
            finally:
                conn.close()
            return redirect(url_for("students"))

        if action == "update":
            student_id = request.form.get("student_id")
            name = (request.form.get("name") or "").strip()
            student_number = (request.form.get("student_number") or "").strip()
            grade_group = (request.form.get("grade_group") or "").strip()
            if student_id and all([name, student_number, grade_group]):
                conn = get_db()
                conn.execute(
                    "UPDATE students SET name = ?, student_number = ?, grade_group = ? WHERE id = ?",
                    (name, student_number, grade_group, student_id),
                )
                conn.commit()
                conn.close()
                flash("تم تحديث بيانات الطالب", "success")
            else:
                flash("بيانات غير مكتملة", "error")
            return redirect(url_for("students"))

        if action == "delete":
            student_id = request.form.get("student_id")
            if student_id:
                conn = get_db()
                conn.execute("DELETE FROM students WHERE id = ?", (student_id,))
                conn.commit()
                conn.close()
                flash("تم حذف الطالب", "success")
            return redirect(url_for("students"))

    conn = get_db()
    students_list = conn.execute(
        "SELECT * FROM students ORDER BY name ASC"
    ).fetchall()
    conn.close()
    return render_template("students.html", students=students_list)


@app.route("/students/<int:student_id>/qr")
@login_required
def student_qr(student_id: int):
    conn = get_db()
    student = conn.execute("SELECT * FROM students WHERE id = ?", (student_id,)).fetchone()
    conn.close()
    if not student:
        flash("لم يتم العثور على الطالب", "error")
        return redirect(url_for("students"))
    qr_url = generate_student_qr(student["id"], student["student_number"])
    return render_template("student_qr.html", student=student, qr_url=qr_url)


@app.route("/students/<int:student_id>/download_qr")
@login_required
def download_qr(student_id: int):
    conn = get_db()
    student = conn.execute("SELECT * FROM students WHERE id = ?", (student_id,)).fetchone()
    conn.close()
    if not student:
        flash("لم يتم العثور على الطالب", "error")
        return redirect(url_for("students"))
    qr_path = QR_DIR / f"{student_id}.png"
    if not qr_path.exists():
        generate_student_qr(student_id, student["student_number"])
    return send_file(qr_path, mimetype="image/png", as_attachment=True, download_name=f"qr_{student['student_number']}.png")


@app.route("/lectures", methods=["GET", "POST"])
@login_required
def lectures():
    if request.method == "POST":
        name = (request.form.get("name") or "").strip()
        lecture_date = (request.form.get("lecture_date") or "").strip()
        lecture_time = (request.form.get("lecture_time") or "").strip()
        if not all([name, lecture_date, lecture_time]):
            flash("يرجى إدخال اسم المحاضرة والتاريخ والوقت", "error")
            return redirect(url_for("lectures"))

        conn = get_db()
        conn.execute(
            "INSERT INTO lectures (name, lecture_date, lecture_time) VALUES (?, ?, ?)",
            (name, lecture_date, lecture_time),
        )
        conn.commit()
        conn.close()
        flash("تم إنشاء المحاضرة بنجاح", "success")
        return redirect(url_for("lectures"))

    conn = get_db()
    lecture_list = conn.execute(
        "SELECT * FROM lectures ORDER BY lecture_date DESC, lecture_time DESC"
    ).fetchall()
    conn.close()
    return render_template("lectures.html", lectures=lecture_list)


@app.route("/attendance/<int:lecture_id>")
@login_required
def attendance_page(lecture_id: int):
    conn = get_db()
    lecture = conn.execute("SELECT * FROM lectures WHERE id = ?", (lecture_id,)).fetchone()
    conn.close()
    if not lecture:
        flash("لم يتم العثور على المحاضرة", "error")
        return redirect(url_for("lectures"))
    return render_template("attendance.html", lecture=lecture)


@app.route("/api/scan", methods=["POST"])
@login_required
def api_scan():
    payload = request.get_json(silent=True) or {}
    lecture_id = payload.get("lecture_id")
    qr_data = payload.get("qr_data")

    if not lecture_id or not qr_data:
        return jsonify({"success": False, "message": "بيانات المسح غير مكتملة"}), 400

    student_number = parse_qr_payload(str(qr_data))
    if not student_number:
        return jsonify({"success": False, "message": "رمز QR غير صالح"}), 400

    student = fetch_student_by_number(student_number)
    if not student:
        return jsonify({"success": False, "message": "الطالب غير موجود"}), 404

    conn = get_db()
    existing = conn.execute(
        "SELECT * FROM attendance WHERE lecture_id = ? AND student_id = ?",
        (lecture_id, student["id"]),
    ).fetchone()
    if existing:
        conn.close()
        return jsonify({"success": False, "message": f"{student['name']} تم تسجيله مسبقاً في هذه المحاضرة"}), 409

    conn.execute(
        "INSERT INTO attendance (lecture_id, student_id) VALUES (?, ?)",
        (lecture_id, student["id"]),
    )
    conn.commit()
    conn.close()
    return jsonify({"success": True, "message": f"تم تسجيل {student['name']} حضوراً"})


@app.route("/reports")
@login_required
def reports():
    lecture_id = request.args.get("lecture_id", type=int)
    conn = get_db()
    lectures = conn.execute("SELECT * FROM lectures ORDER BY lecture_date DESC, lecture_time DESC").fetchall()
    selected = None
    present = []
    absent = []
    if lecture_id:
        selected = conn.execute("SELECT * FROM lectures WHERE id = ?", (lecture_id,)).fetchone()
        if selected:
            present = conn.execute(
                """
                SELECT s.*, a.checked_at
                FROM attendance a
                JOIN students s ON s.id = a.student_id
                WHERE a.lecture_id = ?
                ORDER BY s.name ASC
                """,
                (lecture_id,),
            ).fetchall()
            all_students = conn.execute("SELECT * FROM students ORDER BY name ASC").fetchall()
            present_ids = {row["id"] for row in present}
            absent = [s for s in all_students if s["id"] not in present_ids]
    conn.close()
    return render_template("reports.html", lectures=lectures, selected=selected, present=present, absent=absent)


@app.route("/reports/export/<int:lecture_id>")
@login_required
def export_excel(lecture_id: int):
    conn = get_db()
    lecture = conn.execute("SELECT * FROM lectures WHERE id = ?", (lecture_id,)).fetchone()
    if not lecture:
        conn.close()
        flash("لم يتم العثور على المحاضرة", "error")
        return redirect(url_for("reports"))

    present = conn.execute(
        """
        SELECT s.student_number, s.name, s.grade_group, a.checked_at
        FROM attendance a
        JOIN students s ON s.id = a.student_id
        WHERE a.lecture_id = ?
        ORDER BY s.name ASC
        """,
        (lecture_id,),
    ).fetchall()
    all_students = conn.execute("SELECT * FROM students ORDER BY name ASC").fetchall()
    present_ids = {row["id"] for row in present}
    absent = [s for s in all_students if s["id"] not in present_ids]
    conn.close()

    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "تقرير الحضور"
    sheet["A1"] = "اسم المحاضرة"
    sheet["B1"] = lecture["name"]
    sheet["A2"] = "التاريخ"
    sheet["B2"] = lecture["lecture_date"]
    sheet["A3"] = "الوقت"
    sheet["B3"] = lecture["lecture_time"]

    sheet["A5"] = "رقم الطالب"
    sheet["B5"] = "الاسم"
    sheet["C5"] = "الصف / المجموعة"
    sheet["D5"] = "الحالة"
    sheet["E5"] = "تاريخ الحضور"

    row_num = 6
    for student in present:
        sheet[f"A{row_num}"] = student["student_number"]
        sheet[f"B{row_num}"] = student["name"]
        sheet[f"C{row_num}"] = student["grade_group"]
        sheet[f"D{row_num}"] = "حاضر"
        sheet[f"E{row_num}"] = student["checked_at"]
        row_num += 1

    for student in absent:
        sheet[f"A{row_num}"] = student["student_number"]
        sheet[f"B{row_num}"] = student["name"]
        sheet[f"C{row_num}"] = student["grade_group"]
        sheet[f"D{row_num}"] = "غائب"
        sheet[f"E{row_num}"] = "-"
        row_num += 1

    for column in ["A", "B", "C", "D", "E"]:
        sheet.column_dimensions[column].width = 20

    output = io.BytesIO()
    workbook.save(output)
    output.seek(0)
    return send_file(output, as_attachment=True, download_name=f"report_{lecture_id}.xlsx", mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
