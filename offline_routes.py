from pathlib import Path

from flask import Blueprint, render_template, send_from_directory

ASSETS = Path(__file__).resolve().parent / "offline_assets"
offline = Blueprint("offline", __name__, static_folder=str(ASSETS), static_url_path="/offline-assets")


@offline.get("/")
def leader():
    return send_from_directory(ASSETS, "leader.html")


@offline.get("/student")
def student():
    return render_template("offline_student.html", standalone=False)


@offline.get("/sw.js")
def service_worker():
    return send_from_directory(ASSETS, "sw.js", max_age=0)


@offline.get("/student-offline.html")
def standalone_student():
    """Build the generic student page using only bundled sources, not student data."""
    css = (ASSETS / "app.css").read_text(encoding="utf-8")
    license_text = (ASSETS / "vendor/qrcode.LICENSE.txt").read_text(encoding="utf-8")
    scripts = [(ASSETS / name).read_text(encoding="utf-8")
               for name in ("vendor/qrcode.js", "qr-code.js", "student.js")]
    scripts[0] = f"/*\n{license_text}\n*/\n" + scripts[0]
    if "</style" in css.lower() or any("</script" in script.lower() for script in scripts):
        raise ValueError("An offline asset contains an inline HTML closing tag")
    return render_template("offline_student.html", standalone=True, css=css, scripts=scripts)
