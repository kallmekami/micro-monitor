FROM python:3.11-slim

WORKDIR /app

RUN pip install --no-cache-dir redis

COPY alert.py .

CMD ["python", "-u", "alert.py"]
