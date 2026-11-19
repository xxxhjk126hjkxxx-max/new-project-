import re
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

import app


def external_refs(html: str) -> list[str]:
    refs = re.findall(r'<(?:link|script|img)\b[^>]*\b(?:src|href)\s*=\s*["\']([^"\']+)', html, re.IGNORECASE)
    return [ref for ref in refs if not ref.startswith("data:")]


class OfflineShellTest(unittest.TestCase):
    def setUp(self):
        folder = TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.database = Path(folder.name) / "legacy.db"
        database_patch = patch.object(app, "DB_PATH", self.database)
        database_patch.start()
        self.addCleanup(database_patch.stop)
        self.client = app.app.test_client()

    def test_single_file_apps_are_served_without_legacy_database(self):
        for path in ("/", "/student", "/student-offline.html"):
            with self.subTest(path=path), self.client.get(path) as response:
                self.assertEqual(response.status_code, 200)
        self.assertFalse(self.database.exists())

    def test_leader_file_is_self_contained(self):
        html = self.client.get("/").get_data(as_text=True)
        self.assertIn('id="student-form"', html)
        self.assertIn("const AttendanceCode", html)
        self.assertIn("function openDatabase", html)
        self.assertEqual(external_refs(html), [])
        self.assertNotIn("/offline-assets/", html)

    def test_student_file_is_self_contained(self):
        with self.client.get("/student") as response:
            html = response.get_data(as_text=True)
        self.assertIn('id="student-token"', html)
        self.assertIn("const AttendanceCode", html)
        self.assertIn("var qrcode", html)
        self.assertEqual(external_refs(html), [])
        self.assertNotIn("/offline-assets/", html)

    def test_legacy_login_still_uses_legacy_database(self):
        self.assertEqual(self.client.get("/login").status_code, 200)
        self.assertTrue(self.database.exists())


if __name__ == "__main__":
    unittest.main()
