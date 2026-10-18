"""Local development settings."""
from .base import *  # noqa: F403

DEBUG = True

# Keep the .env list (base.py) and add local conveniences plus any public
# tunnel host (ngrok/cloudflared) so ONLYOFFICE can reach this dev server.
_tunnel_hosts = env.list("EXTRA_ALLOWED_HOSTS", default=[])
ALLOWED_HOSTS = [
    *env.list("ALLOWED_HOSTS", default=["localhost", "127.0.0.1"]),
    "localhost",
    "127.0.0.1",
    ".localhost",
    *_tunnel_hosts,
]

# CSRF origins need a full "https://host" URL, unlike ALLOWED_HOSTS.
CSRF_TRUSTED_ORIGINS = [
    *env.list("CSRF_TRUSTED_ORIGINS", default=[]),
    *(f"https://{host}" for host in _tunnel_hosts),
]

# EMAIL_* come from .env / base.py (Brevo SMTP). Do not force console here.

# Avoid login lockouts during local development.
AXES_ENABLED = False

try:
    import debug_toolbar  # noqa: F401

    INSTALLED_APPS += ["debug_toolbar"]  # noqa: F405
    MIDDLEWARE.insert(0, "debug_toolbar.middleware.DebugToolbarMiddleware")  # noqa: F405
    INTERNAL_IPS = ["127.0.0.1"]
except ImportError:
    pass
