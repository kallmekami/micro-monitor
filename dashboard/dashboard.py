"""
dashboard.py

Terminal dashboard, no browser involved. Subscribes to both "metrics"
and "alerts" and draws a live view using rich. Two background threads
handle the redis subscriptions so the screen can keep redrawing on its
own timer instead of being blocked waiting on messages.

Quick note to self: rich.Live + screen=True basically takes over the
whole terminal like htop does, ctrl+c to get out of it.
"""

import json
import os
import threading
import time
from collections import deque

import redis
from rich.console import Console
from rich.live import Live
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

REDIS_HOST = os.getenv("REDIS_HOST", "redis")
REDIS_PORT = int(os.getenv("REDIS_PORT", 6379))

METRICS_CHANNEL = "metrics"
ALERTS_CHANNEL = "alerts"

MAX_ALERTS = 8

state = {"cpu": 0.0, "ram": 0.0, "timestamp": "-", "connected": False}
alerts = deque(maxlen=MAX_ALERTS)

console = Console()


def bar(value, width=30):
    filled = int((value / 100) * width)
    filled = max(0, min(width, filled))

    # red/yellow/green just based on how bad it is, nothing scientific
    if value > 85:
        color = "red"
    elif value > 60:
        color = "yellow"
    else:
        color = "green"

    t = Text()
    t.append("#" * filled, style=color)
    t.append("-" * (width - filled), style="grey30")
    t.append(f"  {value:5.1f}%", style="bold white")
    return t


def render():
    body = Table.grid(padding=(0, 1))
    body.add_column()
    body.add_column()
    body.add_row("CPU", bar(state["cpu"]))
    body.add_row("RAM", bar(state["ram"]))

    status = "[green]connected[/]" if state["connected"] else "[red]waiting for data...[/]"
    header = Text.from_markup(
        f"[bold cyan]micro-monitor[/]   {status}\n"
        f"[dim]last update: {state['timestamp']}[/]"
    )

    alert_box = Table.grid(padding=(0, 1))
    alert_box.add_column()
    if alerts:
        for a in alerts:
            alert_box.add_row(f"[red]!! {a['timestamp']}  {a['message']}[/]")
    else:
        alert_box.add_row("[dim]nothing yet[/]")

    layout = Table.grid(expand=True)
    layout.add_row(header)
    layout.add_row("")
    layout.add_row(body)
    layout.add_row("")
    layout.add_row(Text("ALERTS", style="bold red"))
    layout.add_row(alert_box)

    return Panel(layout, title="micro monitor", border_style="cyan", expand=False)


def listen_metrics(r):
    pubsub = r.pubsub()
    pubsub.subscribe(METRICS_CHANNEL)
    for msg in pubsub.listen():
        if msg["type"] != "message":
            continue
        try:
            data = json.loads(msg["data"])
        except (json.JSONDecodeError, TypeError):
            continue
        state["cpu"] = data.get("cpu", state["cpu"])
        state["ram"] = data.get("ram", state["ram"])
        state["timestamp"] = data.get("timestamp", state["timestamp"])
        state["connected"] = True


def listen_alerts(r):
    pubsub = r.pubsub()
    pubsub.subscribe(ALERTS_CHANNEL)
    for msg in pubsub.listen():
        if msg["type"] != "message":
            continue
        try:
            data = json.loads(msg["data"])
        except (json.JSONDecodeError, TypeError):
            continue
        alerts.appendleft(data)


def wait_for_redis(r):
    while True:
        try:
            r.ping()
            return
        except redis.exceptions.ConnectionError:
            time.sleep(1)


def main():
    console.print(f"[dim]connecting to {REDIS_HOST}:{REDIS_PORT}...[/]")
    r = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, decode_responses=True)
    wait_for_redis(r)

    threading.Thread(target=listen_metrics, args=(r,), daemon=True).start()
    threading.Thread(target=listen_alerts, args=(r,), daemon=True).start()

    with Live(render(), console=console, refresh_per_second=4, screen=True) as live:
        while True:
            live.update(render())
            time.sleep(0.25)


if __name__ == "__main__":
    main()
