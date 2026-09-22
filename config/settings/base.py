"""Base settings shared across all environments."""
from pathlib import Path
import os
import environ

BASE_DIR = Path(__file__).resolve().parent.parent.parent

env = environ.Env(
    DEBUG=(bool, False),
    ALLOWED_HOSTS=(list, []),
)
environ.Env.read_env(BASE_DIR / ".env")

SECRET_KEY = env("SECRET_KEY")
DEBUG = env.bool("DEBUG", default=False)
ALLOWED_HOSTS = env.list("ALLOWED_HOSTS", default=[])

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.humanize",
    "django.contrib.staticfiles",
    "django.contrib.sites",
    # Third-party
    "allauth",
    "allauth.account",
    "axes",
    "crispy_forms",
    "crispy_tailwind",
    "model_utils",
    # Local apps
    "apps.core",
    "apps.users",
    "apps.questions",
    "apps.reviews",
    "apps.analytics",
    "apps.ai",
    "apps.research",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "allauth.account.middleware.AccountMiddleware",
    "axes.middleware.AxesMiddleware",
]

ROOT_URLCONF = "config.urls"

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
                "apps.core.context_processors.navigation_context",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"

DATABASES = {
    # "default": {
    #     "ENGINE": "django.db.backends.sqlite3",
    #     "NAME": BASE_DIR / "db.sqlite3",
    # },
    # Railway / PostgreSQL (commented out for local SQLite development):
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": "railway",
        "USER": "postgres",
        "PASSWORD": "eFpJQNkaXixKdZKyTIcjvRbBRFPXLFIy",
        "HOST": "tokaido.proxy.rlwy.net",
        "PORT": "11132",
    },
}

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

STATIC_URL = "/static/"
STATICFILES_DIRS = [BASE_DIR / "static"]
STATIC_ROOT = BASE_DIR / "staticfiles"

MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

AUTH_USER_MODEL = "users.User"

SITE_ID = 1

AUTHENTICATION_BACKENDS = [
    "axes.backends.AxesStandaloneBackend",
    "django.contrib.auth.backends.ModelBackend",
    "allauth.account.auth_backends.AuthenticationBackend",
]

LOGIN_URL = "account_login"
LOGIN_REDIRECT_URL = "core:home"
LOGOUT_REDIRECT_URL = "account_login"

ACCOUNT_LOGOUT_ON_GET = True
ACCOUNT_LOGIN_METHODS = {"email"}
ACCOUNT_SIGNUP_FIELDS = ["email*", "password1*", "password2*"]
ACCOUNT_EMAIL_VERIFICATION = "optional"
ACCOUNT_CHANGE_EMAIL = True
ACCOUNT_USER_MODEL_USERNAME_FIELD = None
ACCOUNT_ADAPTER = "apps.users.adapters.ExamiQAccountAdapter"
ACCOUNT_FORMS = {
    "login": "apps.users.forms.ExamiQLoginForm",
    "signup": "apps.users.forms.ExamiQSignupForm",
    "change_password": "apps.users.forms.ExamiQChangePasswordForm",
}

CRISPY_ALLOWED_TEMPLATE_PACKS = "tailwind"
CRISPY_TEMPLATE_PACK = "tailwind"

AXES_ENABLED = env.bool("AXES_ENABLED", default=True)
AXES_FAILURE_LIMIT = env.int("AXES_FAILURE_LIMIT", default=5)
AXES_COOLOFF_TIME = env.float("AXES_COOLOFF_TIME", default=1)
# Lock by email (username) so one bad actor on a shared IP does not block everyone.
AXES_LOCKOUT_PARAMETERS = ["username"]

SESSION_COOKIE_AGE = 86400

DEFAULT_SECONDS_PER_QUESTION = 30

SITE_URL = env("SITE_URL", default="http://127.0.0.1:8000")
DEFAULT_FROM_EMAIL = env("DEFAULT_FROM_EMAIL", default="noreply@examiq.local")

AI_ENABLED = env.bool("AI_ENABLED", default=False)
LLM_PROVIDER = env("LLM_PROVIDER", default="openai")
OPENAI_API_KEY = env("OPENAI_API_KEY", default="")
OPENAI_MODEL = env("OPENAI_MODEL", default="gpt-4o-mini")
GEMINI_API_KEY = env("GEMINI_API_KEY", default="")
GEMINI_MODEL = env("GEMINI_MODEL", default="gemini-2.0-flash")
GEMINI_FALLBACK_MODELS = env.list(
    "GEMINI_FALLBACK_MODELS",
    default=[
        "gemini-2.0-flash",
        "gemini-2.5-flash",
        "gemini-2.5-flash-lite",
        "gemini-2.0-flash-lite",
    ],
)
GEMINI_QUESTION_MAX_OUTPUT_TOKENS = env.int("GEMINI_QUESTION_MAX_OUTPUT_TOKENS", default=2048)
AI_GENERATION_BATCH_SIZE = env.int("AI_GENERATION_BATCH_SIZE", default=5)
AI_GENERATION_MAX_ATTEMPTS = env.int("AI_GENERATION_MAX_ATTEMPTS", default=3)
# Legacy env keys retained so existing .env files keep loading; no longer enforced.
AI_GENERATION_MAX_COUNT = env.int("AI_GENERATION_MAX_COUNT", default=50)
MAX_QUESTIONS_PER_SUBJECT = env.int("MAX_QUESTIONS_PER_SUBJECT", default=0)
VALIDATION_SESSION_DEFAULT_SIZE = env.int("VALIDATION_SESSION_DEFAULT_SIZE", default=15)
VALIDATION_SESSION_MIN_SIZE = env.int("VALIDATION_SESSION_MIN_SIZE", default=10)
VALIDATION_SESSION_MAX_SIZE = env.int("VALIDATION_SESSION_MAX_SIZE", default=20)
RETAKE_ACTION_PLAN_THRESHOLD = env.int("RETAKE_ACTION_PLAN_THRESHOLD", default=3)
QUESTION_MISTAKE_STUDENT_THRESHOLD = env.int(
    "QUESTION_MISTAKE_STUDENT_THRESHOLD", default=15
)
OLLAMA_API_KEY = env("OLLAMA_API_KEY", default="")
OLLAMA_BASE_URL = env("OLLAMA_BASE_URL", default="https://ollama.com")
OLLAMA_MODEL = env("OLLAMA_MODEL", default="gpt-oss:120b")
OLLAMA_FALLBACK_MODELS = env.list(
    "OLLAMA_FALLBACK_MODELS",
    default=["gpt-oss:20b", "gpt-oss:120b"],
)
