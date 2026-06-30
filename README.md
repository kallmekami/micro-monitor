# Micro Monitor

A small distributed system project that monitors CPU and RAM usage of a
machine in real time, built using a microservice architecture with
Docker and Redis as the communication layer between services.

This project was built as a practical exercise in microservice design,
specifically to explore how independent services can communicate
without being directly coupled to one another, using the
publish/subscribe pattern instead of direct service-to-service calls.

---

## 1. Motivation

Most introductory examples of microservices use HTTP requests between
services (Service A calls Service B's REST endpoint directly). This
works, but it creates tight coupling: Service A needs to know Service
B's address, has to handle retries if B is down, and the two are
essentially glued together.

The goal of this project was to instead use an **event-driven**
approach. Services don't call each other - they publish events to a
message broker (Redis, in this case) and other services subscribe to
the events they care about. None of the services know about each
other's existence, only about Redis.

---

## 2. System Overview

The system is made up of four containers:

```
                    +--------------+
                    |    Redis     |
                    |  (pub/sub)   |
                    +------+-------+
            publish        |        subscribe
        +-------------------+-------------------+
        |                   |                   |
+---------------+   +---------------+   +---------------+
|  collector    |   | alert         |   |  dashboard    |
|  reads CPU/   |   | checks        |   |  CLI display  |
|  RAM usage    |   | thresholds    |   |  (rich/TUI)   |
+---------------+   +-------+-------+   +-------^-------+
                            |  publish           |
                            +-- channel "alerts"-+
```

| Service    | Role                                              |
|------------|---------------------------------------------------|
| collector  | reads system CPU/RAM stats, publishes them        |
| alert      | listens for metrics, fires alerts past a threshold|
| dashboard  | terminal UI showing live metrics and alerts       |
| redis      | message broker, not a custom service - off the shelf|

Two Redis channels are used:

| Channel   | Published by | Subscribed by      | Payload                                  |
|-----------|--------------|---------------------|-------------------------------------------|
| `metrics` | collector    | dashboard, alert     | `{cpu, ram, timestamp}`                   |
| `alerts`  | alert        | dashboard            | `{type, value, threshold, message, timestamp}` |

---

## 3. Why Redis Pub/Sub Instead of HTTP

This was the main design decision in the project, so it's worth
explaining in more detail.

With a typical REST-based approach, if `collector` wanted to notify
`dashboard` and `alert` of a new reading, it would need to make two
separate HTTP requests, know both addresses, and handle the case
where either one is unreachable. Adding a third consumer later would
mean modifying `collector`'s code directly.

With pub/sub, `collector` just publishes one message to a channel and
does not need to know who - or how many services - are listening.
Adding a new consumer later (say, a logging service that writes
metrics to a file) requires zero changes to `collector`. It just
subscribes to the same channel.

The tradeoff is that pub/sub in Redis is **fire-and-forget**: if a
subscriber isn't connected at the moment a message is published, it
simply misses it. There is no message queue or persistence involved
(this is different from something like RabbitMQ or Kafka). For a
monitoring use case where a new reading comes in every 2 seconds, this
tradeoff is acceptable, since missing one reading isn't critical.

---

## 4. Service Details

### 4.1 collector

Reads CPU and memory usage using the `psutil` Python library and
publishes a JSON payload to the `metrics` channel on a fixed interval
(default every 2 seconds, configurable).

The first call to `psutil.cpu_percent()` always returns `0.0` because
it needs a previous sample to compare against - the code accounts for
this by discarding the first reading.

### 4.2 alert

Subscribes to `metrics`. On every incoming reading, it compares the
CPU and RAM values against configurable thresholds (default 80% CPU,
85% RAM). If a threshold is exceeded, it publishes a message to the
`alerts` channel.

A 10-second cooldown is implemented per metric type so that if CPU
stays above the threshold for an extended period, the system doesn't
fire a new alert every single reading - only once, then again after
the cooldown expires if it's still high.

### 4.3 dashboard

Subscribes to both `metrics` and `alerts` channels in two separate
background threads, and renders a live-updating terminal interface
using the `rich` library. This is a pure command-line interface; there
is no web server or browser component involved anywhere in the
project.

The dashboard shows:
- a progress-bar style display for current CPU and RAM usage,
  colour-coded (green / yellow / red depending on severity)
- a scrolling list of the most recent alerts received

---

## 5. Running the Project

### Requirements
- Docker
- Docker Compose (v2, the `docker compose` command, not the old
  standalone `docker-compose`)

### Steps

Clone or unzip the project, then from the root directory:

```bash
docker compose up --build
```

This starts four containers: `mm-redis`, `mm-collector`, `mm-alert`,
and `mm-dashboard`.

The dashboard runs as an interactive terminal application, so it's
best viewed by attaching to it directly:

```bash
docker attach mm-dashboard
```

To detach without stopping the container, use `Ctrl+P` followed by
`Ctrl+Q`.

To view the collector or alert service logs instead:

```bash
docker compose logs -f collector
docker compose logs -f alert
```

To stop everything:

```bash
docker compose down
```

### Verifying Redis Manually

It is possible to manually inspect the pub/sub channels using
`redis-cli`, which is useful for debugging or for demonstrating that
the messages are in fact flowing through Redis and not some other
mechanism:

```bash
docker exec -it mm-redis redis-cli
> SUBSCRIBE metrics
```

---

## 6. Configuration

All configuration is done through environment variables defined in
`docker-compose.yml`, no rebuilding of images is required to change
them.

| Variable           | Used by    | Default | Description                       |
|---------------------|------------|---------|------------------------------------|
| `REDIS_HOST`         | all        | `redis` | hostname of the Redis container    |
| `REDIS_PORT`         | all        | `6379`  | Redis port                          |
| `COLLECT_INTERVAL`   | collector  | `2`     | seconds between each reading        |
| `CPU_THRESHOLD`      | alert      | `80`    | CPU % that triggers an alert        |
| `RAM_THRESHOLD`      | alert      | `85`    | RAM % that triggers an alert        |

---

## 7. A Note on `pid: host`

In `docker-compose.yml`, the `collector` service is configured with
`pid: host`. This makes the container share the process namespace of
the host machine, which allows `psutil` to report statistics for the
actual host rather than just the resources visible inside the
container (which, by default, would be limited and not very
representative of real system load).

If host-level visibility isn't desired (e.g. for a sandboxed test
environment), this line can simply be removed and the collector will
fall back to reporting the container's own resource usage.

---

## 8. Project Structure

```
micro-monitor/
├── docker-compose.yml
├── README.md
├── collector/
│   ├── Dockerfile
│   └── collector.py
├── alert/
│   ├── Dockerfile
│   └── alert.py
└── dashboard/
    ├── Dockerfile
    └── dashboard.py
```

---

## 9. Limitations and Possible Improvements

This is a learning-focused project, so a number of things were kept
intentionally simple:

- **No persistence**: metrics are not stored anywhere, only displayed
  live. A real monitoring system would write to a time-series
  database (e.g. InfluxDB, Prometheus, or even just appending to a
  log file) so historical data could be queried later.
- **No authentication on Redis**: in a production environment Redis
  would need a password and possibly TLS, since right now anyone on
  the same network could connect and read the channels.
- **Single machine only**: the project currently monitors the host it
  runs on. Extending it to monitor multiple machines would mean
  running multiple collector instances, each tagging its messages
  with a hostname so the dashboard can distinguish between them.
- **No notification integration**: the alert service only publishes
  to Redis; it does not yet send emails, Slack messages, or Telegram
  notifications, which would be a natural next step.

---

## 10. Summary

This project demonstrates a basic but functional microservice system
using an event-driven communication pattern. Three independent
services (collector, alert, dashboard) are fully decoupled from one
another and only interact through Redis pub/sub channels, which
satisfies the core principle of microservice architecture: services
should be independently deployable and should not require knowledge
of each other's internal implementation or location.
<img width="952" height="455" alt="image" src="https://github.com/user-attachments/assets/38dd68b2-264b-4288-8779-af27b0bbac7b" />
