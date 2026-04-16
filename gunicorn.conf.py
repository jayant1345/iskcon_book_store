"""Gunicorn production configuration."""
import os

bind        = f"0.0.0.0:{os.environ.get('PORT', '5000')}"
workers     = int(os.environ.get("GUNICORN_WORKERS", "2"))
threads     = int(os.environ.get("GUNICORN_THREADS", "4"))
timeout     = 120
keepalive   = 5
loglevel    = os.environ.get("LOG_LEVEL", "info")
accesslog   = "-"   # stdout
errorlog    = "-"   # stderr
preload_app = True

def on_starting(server):
    """Initialize DB before workers fork."""
    try:
        from app import init_db
        init_db()
    except Exception as e:
        print(f"[WARNING] DB init on_starting failed: {e}")
