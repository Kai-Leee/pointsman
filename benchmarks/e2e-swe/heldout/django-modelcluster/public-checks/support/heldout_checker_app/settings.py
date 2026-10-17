"""Checker-owned Django settings: in-memory SQLite, USE_TZ with a non-UTC zone, per-process MEDIA_ROOT.

HELDOUT_CHECKER_APPS selects the optional checker apps a case needs (core is always loaded), so a
candidate defect in one subsystem's model declarations cannot break unrelated cases.
"""
import os
import tempfile

_optional = {
    "tags": "heldout_checker_tags",
    "probe": "heldout_checker_probe",
    "default": "heldout_checker_default",
}
_selected = [name for name in os.environ.get("HELDOUT_CHECKER_APPS", "").split(",") if name]

SECRET_KEY = "heldout-public-checks"
DEBUG = False
USE_TZ = True
TIME_ZONE = "Asia/Seoul"
DATABASES = {"default": {"ENGINE": "django.db.backends.sqlite3", "NAME": ":memory:"}}
INSTALLED_APPS = [
    "django.contrib.contenttypes",
    "django.contrib.auth",
    "taggit",
    "heldout_checker_app",
] + [_optional[name] for name in _selected if name in _optional]
DEFAULT_AUTO_FIELD = "django.db.models.AutoField"
MEDIA_ROOT = tempfile.mkdtemp(prefix="heldout-media-")
SILENCED_SYSTEM_CHECKS = []
