"""
collector.py

Job of this service is simple: every couple of seconds read CPU and RAM
usage from the machine, package it as JSON and publish it to redis.

Nobody downstream (dashboard, alert) is hardcoded here. We don't know
who's listening and we don't care - that's kind of the whole point of
using pub/sub instead of just calling each other directly.
"""

import json
import os
import time
from datetime import datetime

import psutil
import redis

# all of these can be overridden from docker-compose.yml so we don't
# have to rebuild the image every time we want to change something
REDIS_HOST = os.getenv("REDIS_HOST", "redis")
REDIS_PORT = int(os.getenv("REDIS_PORT", 6379))
INTERVAL = float(os.getenv("COLLECT_INTERVAL", 2))

CHANNEL = "metrics"


def get_metrics():
    cpu = psutil.cpu_percent(interval=None)
    ram = psutil.virtual_memory().percent
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    return {"cpu": cpu, "ram": ram, "timestamp": now}


def wait_for_redis(r):
    # redis container might not be ready when this one starts,
    # so just keep retrying instead of crashing
    while True:
        try:
            r.ping()
            return
        except redis.exceptions.ConnectionError:
            print("[collector] redis not ready yet, retrying...")
            time.sleep(1)


def main():
    print(f"[collector] starting up, connecting to {REDIS_HOST}:{REDIS_PORT}")
    r = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, decode_responses=True)
    wait_for_redis(r)
    print(f"[collector] connected. publishing on '{CHANNEL}' every {INTERVAL}s")

    # first call to cpu_percent always returns 0.0 because it needs a
    # baseline to compare against - warming it up here so the first
    # real reading isn't garbage
    psutil.cpu_percent(interval=None)
    time.sleep(1)

    while True:
        data = get_metrics()
        r.publish(CHANNEL, json.dumps(data))
        print(f"[collector] {data}")
        time.sleep(INTERVAL)


if __name__ == "__main__":
    main()
