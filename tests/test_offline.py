import re
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

import app


class OfflineShellTest(unittest.TestCase):
    def setUp(self):
        folder = TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.database = Path(folder.name) / "legacy.db"
        database_patch = patch.object(app, "DB_PATH", self.database)
        database_patch.start()
        self.addCleanup(database_patch.stop)
        self.client = app.app.test_client()

    def test_offline_shell_and_assets_do_not_open_legacy_database(self):
        paths = (
            "/", "/student", "/student-offline.html", "/sw.js",
            *(f"/offline-assets/{asset}" for asset in (
                "app.css", "leader.js", "student.js", "db.js", "qr-code.js",
                "manifest.webmanifest", "student.webmanifest", "icon.svg",
                "icon-192.png", "icon-512.png", "vendor/jsqr.js", "vendor/qrcode.js",
            )),
        )
        for path in paths:
            with self.subTest(path=path), self.client.get(path) as response:
                self.assertEqual(response.status_code, 200)
        self.assertFalse(self.database.exists())

    def test_standalone_page_inlines_every_dependency(self):
        response = self.client.get("/student-offline.html")
        html = response.get_data(as_text=True)
        self.assertIn('id="student-token"', html)
        self.assertIn("const AttendanceCode", html)
        self.assertIn("var qrcode", html)
        self.assertFalse(re.search(r'<(?:link|script|img)\b[^>]*\b(?:src|href)\s*=', html, re.IGNORECASE))
        self.assertNotIn('/offline-assets/', html)

    def test_legacy_login_still_uses_legacy_database(self):
        self.assertEqual(self.client.get("/login").status_code, 200)
        self.assertTrue(self.database.exists())


if __name__ == "__main__":
    unittest.main()
