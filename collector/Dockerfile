# nothing fancy, just python + the two libs we actually need
FROM python:3.11-slim

WORKDIR /app

RUN pip install --no-cache-dir psutil redis

COPY collector.py .

CMD ["python", "-u", "collector.py"]
