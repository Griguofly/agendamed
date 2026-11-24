"""Configuración de AgendaMed.

Todo lo sensible (clave secreta, base de datos, credenciales del admin) se lee de
variables de entorno. En desarrollo se cargan desde el archivo .env (que NO se
sube al repositorio: ver .gitignore). En Render se definen en el panel del servicio.
"""
import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")


def _normalizar_url(url):
    """Fuerza el driver psycopg2 en las URLs de PostgreSQL.

    Render entrega "postgres://...", y SQLAlchemy 2.1 elige por defecto otro driver (psycopg 3)
    cuando la URL dice solo "postgresql://". Con "postgresql+psycopg2://" siempre se usa el
    driver psycopg2-binary que figura en requirements.txt.
    """
    for prefijo in ("postgres://", "postgresql://"):
        if url.startswith(prefijo):
            return "postgresql+psycopg2://" + url[len(prefijo):]
    return url


def _url_base_de_datos():
    """SQLite si no hay DATABASE_URL (desarrollo); PostgreSQL en producción."""
    url = os.environ.get("DATABASE_URL", "").strip()
    if not url:
        return "sqlite:///agendamed.db"
    return _normalizar_url(url)


class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY")
    SQLALCHEMY_DATABASE_URI = _url_base_de_datos()
    # pool_pre_ping evita errores cuando la base cierra conexiones inactivas.
    SQLALCHEMY_ENGINE_OPTIONS = {"pool_pre_ping": True}
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # Cookies de sesión: en Render (HTTPS) definir COOKIE_SECURE=1.
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    SESSION_COOKIE_SECURE = os.environ.get("COOKIE_SECURE", "0") == "1"

    # Modelo de IA (entrenado previamente con ml/entrenar_modelo.py).
    MODELO_PATH = BASE_DIR / "ml" / "modelo_ausentismo.joblib"
    METRICAS_PATH = BASE_DIR / "ml" / "metricas.json"

    # Datos iniciales (especialidades, médicos y usuario administrativo).
    AUTO_SEED = os.environ.get("AUTO_SEED", "1") == "1"
    ADMIN_EMAIL = os.environ.get("ADMIN_EMAIL", "").strip().lower()
    ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "")


class TestConfig(Config):
    TESTING = True
    SECRET_KEY = "clave-solo-para-tests"
    # Por defecto SQLite en memoria; con TEST_DATABASE_URL se prueba contra PostgreSQL.
    SQLALCHEMY_DATABASE_URI = _normalizar_url(os.environ.get("TEST_DATABASE_URL", "sqlite:///:memory:"))
    WTF_CSRF_ENABLED = False
    BCRYPT_LOG_ROUNDS = 4
    AUTO_SEED = False
    ADMIN_EMAIL = ""
    ADMIN_PASSWORD = ""