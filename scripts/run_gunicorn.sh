#!/usr/bin/env sh
exec gunicorn wireloft_web.app:app -k uvicorn.workers.UvicornWorker --bind 0.0.0.0:8000
