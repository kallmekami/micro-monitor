"""
alert.py

Listens to the "metrics" channel that collector.py publishes to, and
if CPU or RAM goes above a threshold, fires an alert on its own
channel called "alerts". Dashboard (or anything else really) can pick
that up.

This service has no idea collector or dashboard even exist as files -
it just reacts to whatever shows up on the metrics channel.
"""

import json
import os
import time
from datetime import datetime

import redis

REDIS_HOST = os.getenv("REDIS_HOST", "redis")
REDIS_PORT = int(os.getenv("REDIS_PORT", 6379))

METRICS_CHANNEL = "metrics"
ALERTS_CHANNEL = "alerts"

CPU_THRESHOLD = float(os.getenv("CPU_THRESHOLD", 80))
RAM_THRESHOLD = float(os.getenv("RAM_THRESHOLD", 85))

# don't want to spam an alert on literally every single reading while
# usage stays high, so just cool down for a bit after firing one
COOLDOWN = 10
last_fired = {"cpu": 0, "ram": 0}


def maybe_fire(r, kind, value, threshold):
    now = time.time()
    if value <= threshold:
        return
    if now - last_fired[kind] < COOLDOWN:
        return

    payload = {
        "type": kind,
        "value": value,
        "threshold": threshold,
        "message": f"{kind.upper()} usage high: {value}% (threshold {threshold}%)",
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }
    r.publish(ALERTS_CHANNEL, json.dumps(payload))
    print(f"[alert] fired -> {payload}")
    last_fired[kind] = now


def wait_for_redis(r):
    while True:
        try:
            r.ping()
            return
        except redis.exceptions.ConnectionError:
            print("[alert] redis not ready yet, retrying...")
            time.sleep(1)


def main():
    r = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, decode_responses=True)
    wait_for_redis(r)

    pubsub = r.pubsub()
    pubsub.subscribe(METRICS_CHANNEL)
    print(f"[alert] watching '{METRICS_CHANNEL}' "
          f"(cpu > {CPU_THRESHOLD}%, ram > {RAM_THRESHOLD}%)")

    for msg in pubsub.listen():
        if msg["type"] != "message":
            # first message after subscribe is a "subscribe" confirmation,
            # not actual data - skip it
            continue

        try:
            data = json.loads(msg["data"])
        except (json.JSONDecodeError, TypeError):
            continue

        maybe_fire(r, "cpu", data.get("cpu", 0), CPU_THRESHOLD)
        maybe_fire(r, "ram", data.get("ram", 0), RAM_THRESHOLD)


if __name__ == "__main__":
    main()
