FROM python:3.11-slim

WORKDIR /app

RUN pip install --no-cache-dir redis rich

COPY dashboard.py .

CMD ["python", "-u", "dashboard.py"]
