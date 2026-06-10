# settings.py — Django + Render (prod) / Local (dev)
import os
from pathlib import Path

# === Entorno y rutas ===
AMBIENTE = os.getenv("AMBIENTE", "local").lower()  # "local" o "produccion"
BASE_DIR = Path(__file__).resolve().parent.parent

# === Clave secreta y debug ===
SECRET_KEY = os.getenv("SECRET_KEY", "dev-secret-change-me")
DEBUG = AMBIENTE != "produccion"

# === Hosts y CSRF ===
ALLOWED_HOSTS = ["127.0.0.1", "localhost"] if DEBUG else ["*"]
_external = os.getenv("RENDER_EXTERNAL_HOSTNAME")
if _external:
    ALLOWED_HOSTS.append(_external)
    # Render sirve tu app en https://<host>
    CSRF_TRUSTED_ORIGINS = [f"https://{_external}"]

# === Apps ===
INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",

    "app_instalaciones",
    "widget_tweaks",
]

# === Middleware ===
MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    # WhiteNoise se inserta en prod justo después de SecurityMiddleware
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]
if AMBIENTE == "produccion":
    MIDDLEWARE.insert(1, "whitenoise.middleware.WhiteNoiseMiddleware")
    # Render termina en proxy HTTPS:
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
    CSRF_COOKIE_SECURE = True
    SESSION_COOKIE_SECURE = True
    # (Opcional endurecer aún más)
    # SECURE_HSTS_SECONDS = 3600
    # SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    # SECURE_HSTS_PRELOAD = True

# === URLs y WSGI ===
ROOT_URLCONF = "instalaciones.urls"
WSGI_APPLICATION = "instalaciones.wsgi.application"

# === Templates ===
TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        # si usas carpeta templates/ a nivel de proyecto
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "app_instalaciones.context_processors.permisos_usuario",
            ],
        },
    },
]

# === Base de datos ===
# Por defecto: SQLite (ideal para desarrollo)
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": BASE_DIR / "db.sqlite3",
    }
}
# En producción: usar Postgres si hay DATABASE_URL
try:
    import dj_database_url  # type: ignore
except ModuleNotFoundError:
    dj_database_url = None

if AMBIENTE == "produccion" and dj_database_url and os.getenv("DATABASE_URL"):
    DATABASES["default"] = dj_database_url.config(
        conn_max_age=600, ssl_require=True
    )

# === Validadores de contraseña ===
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

# === i18n ===
LANGUAGE_CODE = "es-co"
TIME_ZONE = "America/Bogota"
USE_I18N = True
USE_TZ = True

# === Archivos estáticos y media ===
STATIC_URL = "/static/"
MEDIA_URL = "/media/"

if AMBIENTE == "produccion":
    STATIC_ROOT = BASE_DIR / "staticfiles"  # donde collectstatic deja los archivos
    STATICFILES_STORAGE = "whitenoise.storage.CompressedManifestStaticFilesStorage"
else:
    # si tienes carpeta static/ en desarrollo
    STATICFILES_DIRS = [BASE_DIR / "static"]
    MEDIA_ROOT = BASE_DIR / "media"

# === Login y sesiones ===
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
LOGIN_URL = "/login/"
LOGIN_REDIRECT_URL = "home"

EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"

SESSION_COOKIE_AGE = 3600
SESSION_EXPIRE_AT_BROWSER_CLOSE = True
SESSION_ENGINE = "django.contrib.sessions.backends.db"
