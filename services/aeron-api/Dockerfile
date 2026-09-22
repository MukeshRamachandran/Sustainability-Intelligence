FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

RUN addgroup --system aeron && adduser --system --ingroup aeron aeron
COPY backend ./backend
COPY database ./database
RUN chown -R aeron:aeron /app
USER aeron

EXPOSE 8001
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8001/health/live', timeout=3)"

CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8001"]
