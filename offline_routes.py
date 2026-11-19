"""Serve the two standalone single-file apps built by build_single_files.py."""
from pathlib import Path

from flask import Blueprint, send_from_directory

BASE = Path(__file__).resolve().parent
offline = Blueprint("offline", __name__)


@offline.get("/")
def leader():
    return send_from_directory(BASE, "leader.html")


@offline.get("/student")
def student():
    return send_from_directory(BASE, "student.html")


@offline.get("/student-offline.html")
def standalone_student():
    return send_from_directory(BASE, "student.html")
