FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY requirements.txt ./
RUN python -m pip install --no-cache-dir -r requirements.txt

RUN groupadd --gid 10001 taskhub \
    && useradd --uid 10001 --gid taskhub --no-create-home taskhub \
    && install -d -m 0700 -o taskhub -g taskhub /app/.keys \
    && touch /app/.keys/.keep

COPY app/ ./app/
COPY alembic/ ./alembic/
COPY alembic.ini ./
COPY scripts/generate_auth_keys.py ./scripts/

USER taskhub
EXPOSE 8000

CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
