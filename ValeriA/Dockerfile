FROM python:3.11-slim

WORKDIR /app

COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY backend/ /app/backend/
COPY frontend/ /app/frontend/

ENV DB_PATH=/data/app.db
ENV PORT=8090

WORKDIR /app/backend

EXPOSE 8090

CMD ["sh", "-c", "uvicorn main:app --host 0.0.0.0 --port ${PORT}"]
