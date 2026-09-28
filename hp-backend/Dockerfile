FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
EXPOSE 8000
# Shell form so ${PORT} expands. Hosts that assign a port (Render, Cloud Run,
# Heroku) set PORT; locally and under docker-compose it falls back to 8000.
# `exec` so uvicorn replaces the shell as PID 1: sh does not pass SIGTERM on,
# so a deploy's stop never reached the app, Docker killed it 10 s later, and
# the regeneration job it was running was left orphaned (28 Sep).
CMD exec uvicorn app.main:app --app-dir src --host 0.0.0.0 --port ${PORT:-8000}
