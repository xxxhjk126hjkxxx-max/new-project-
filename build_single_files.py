"""Build the two standalone single-file apps from the offline_assets sources.

Outputs (repository root):
  leader.html   - leader app: students, lectures, QR scanning, reports
  student.html  - student app: enter the code, generate a QR code

Both files are fully self-contained (CSS, QR libraries and app logic are
inlined) and work without any network or server. Run after editing the
sources in offline_assets/ or templates/offline_student.html:

    python build_single_files.py
"""
from __future__ import annotations

import base64
import re
from pathlib import Path

from jinja2 import Environment, FileSystemLoader

BASE = Path(__file__).resolve().parent
ASSETS = BASE / "offline_assets"


def read(name: str) -> str:
    return (ASSETS / name).read_text(encoding="utf-8")


def check_inline_safe(name: str, content: str) -> None:
    lowered = content.lower()
    if "</script" in lowered or "</style" in lowered:
        raise ValueError(f"{name} contains a closing tag that cannot be inlined safely")


def build_leader() -> str:
    html = read("leader.html")
    css = read("app.css")
    jsqr = read("vendor/jsqr.js")
    qr_code = read("qr-code.js")
    db_js = read("db.js")
    leader_js = read("leader.js")

    for name, content in (
        ("app.css", css),
        ("vendor/jsqr.js", jsqr),
        ("qr-code.js", qr_code),
        ("db.js", db_js),
        ("leader.js", leader_js),
    ):
        check_inline_safe(name, content)

    # Inline the favicon and the header logo as data URIs (the SVG is tiny).
    icon_b64 = base64.b64encode((ASSETS / "icon.svg").read_bytes()).decode("ascii")
    icon_uri = f"data:image/svg+xml;base64,{icon_b64}"
    html = html.replace(
        '<link rel="icon" href="/offline-assets/icon.svg" type="image/svg+xml">',
        f'<link rel="icon" href="{icon_uri}" type="image/svg+xml">',
    )
    html = html.replace(
        '<img src="/offline-assets/icon.svg"',
        f'<img src="{icon_uri}"',
    )
    # Inline the stylesheet.
    html = html.replace(
        '<link rel="stylesheet" href="/offline-assets/app.css">',
        "<style>\n" + css + "\n</style>",
    )
    # Merge db.js and leader.js into one inline module: strip the import /
    # export syntax because everything now lives in the same module scope.
    db_js = re.sub(r"^export\s+", "", db_js, flags=re.MULTILINE)
    leader_js = re.sub(r"^import\s+.*from\s+'\./db\.js';\s*$", "", leader_js, flags=re.MULTILINE)
    scripts = (
        "<script>\n"
        "/* jsQR (Apache License 2.0) — full license: offline_assets/vendor/jsqr.LICENSE.txt */\n"
        + jsqr
        + "\n</script>\n<script>\n"
        + qr_code
        + "\n</script>\n"
        + '<script type="module">\n'
        + db_js
        + "\n"
        + leader_js
        + "\n</script>"
    )
    html = re.sub(
        r'<script defer src="/offline-assets/vendor/jsqr\.js"></script>\s*'
        r'<script defer src="/offline-assets/qr-code\.js"></script>\s*'
        r'<script type="module" src="/offline-assets/leader\.js"></script>',
        lambda _match: scripts,
        html,
    )
    return html


def build_student() -> str:
    env = Environment(loader=FileSystemLoader(str(BASE / "templates")))
    template = env.get_template("offline_student.html")
    css = read("app.css")
    license_text = read("vendor/qrcode.LICENSE.txt")
    scripts = [read("vendor/qrcode.js"), read("qr-code.js"), read("student.js")]
    scripts[0] = f"/*\n{license_text}\n*/\n" + scripts[0]
    for name, content in (
        ("app.css", css),
        ("vendor/qrcode.js", scripts[0]),
        ("qr-code.js", scripts[1]),
        ("student.js", scripts[2]),
    ):
        check_inline_safe(name, content)
    return template.render(standalone=True, css=css, scripts=scripts)


def main() -> None:
    outputs = {"leader.html": build_leader(), "student.html": build_student()}
    for name, html in outputs.items():
        path = BASE / name
        path.write_text(html, encoding="utf-8")
        print(f"{name}: {path.stat().st_size:,} bytes")


if __name__ == "__main__":
    main()
