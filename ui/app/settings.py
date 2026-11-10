"""Django settings for the local Price Tracker application."""

import os
import sys
from pathlib import Path

from app import household

BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = os.environ.get(
    "DJANGO_SECRET_KEY",
    "local-development-key-change-before-any-public-deployment",
)
DEBUG = os.environ.get("DJANGO_DEBUG", "1") == "1"
ALLOWED_HOSTS = [
    host.strip()
    for host in os.environ.get("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1").split(",")
    if host.strip()
]

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "tracker.apps.TrackerConfig",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

# Household mode (milestone 9): turned on only by scripts/serve.py, which runs the app with
# Waitress for the family's phones. Development (runserver) and the tests are unaffected.
HOUSEHOLD_MODE = os.environ.get("PRICE_TRACKER_HOUSEHOLD") == "1"
if HOUSEHOLD_MODE:
    _household = household.ensure_env(household.ENV_FILE)
    SECRET_KEY = _household["DJANGO_SECRET_KEY"]  # random, kept in the git-ignored household.env
    DEBUG = False  # visitors on the Wi-Fi only ever see plain error pages
    ALLOWED_HOSTS = household.local_hosts()
    # WhiteNoise serves styles and scripts, with version-stamped names so browsers
    # always fetch the new files after an update (no Ctrl+F5 needed).
    MIDDLEWARE.insert(1, "whitenoise.middleware.WhiteNoiseMiddleware")
    STORAGES = {
        "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
        "staticfiles": {"BACKEND": "app.storage.HouseholdStaticStorage"},  # WhiteNoise, see app/storage.py
    }

# Daily database backups go here (set BACKUP_DIR in household.env). Never during the
# tests: they would copy the test database into your real backup folder.
RUNNING_TESTS = len(sys.argv) > 1 and sys.argv[1] == "test"
BACKUP_DIR = "" if RUNNING_TESTS else household.read_env(household.ENV_FILE).get("BACKUP_DIR", "")
BACKUP_KEEP = 14

ROOT_URLCONF = "app.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "tracker.context_processors.currency",
            ],
        },
    },
]

WSGI_APPLICATION = "app.wsgi.application"
ASGI_APPLICATION = "app.asgi.application"

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": BASE_DIR / "db.sqlite3",
    }
}

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "en-us"
TIME_ZONE = "Europe/Bucharest"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
LOGIN_URL = "login"
LOGIN_REDIRECT_URL = "dashboard"
LOGOUT_REDIRECT_URL = "login"
