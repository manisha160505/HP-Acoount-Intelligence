FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
EXPOSE 8000
# Shell form so ${PORT} expands. Hosts that assign a port (Render, Cloud Run,
# Heroku) set PORT; locally and under docker-compose it falls back to 8000.
CMD uvicorn app.main:app --app-dir src --host 0.0.0.0 --port ${PORT:-8000}
