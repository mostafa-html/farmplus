# FarmPlus (FarmPulse)

Real-time IoT monitoring backend for poultry and agricultural facilities.  
Collects telemetry (temperature, humidity, lux, NH3) from LoRa gateways via MQTT,
persists it to TimescaleDB, and streams it live over WebSockets.

## Architecture

```
Device/Gateway
      │  MQTT (port 1883)
      ▼
  EMQX Broker
      │  subscriber service
      ▼
  Redis Stream  ──►  Celery Worker  ──►  TimescaleDB
  (telemetry:stream)  (pipeline)          (readings)
      │
      ▼
  Redis Pub/Sub  ──►  pubsub_relay  ──►  Django Channels  ──►  WebSocket clients
```

**Services:** Django (Daphne/ASGI) · Celery · Celery Beat · MQTT Subscriber · Pub/Sub Relay  
**Infrastructure:** EMQX 5.8 · Redis 7.2 · TimescaleDB (PostgreSQL 16)

---

## Quickstart (Windows / Mac / Linux)

### Prerequisites

- [Docker Desktop](https://www.docker.com/products/docker-desktop/) with WSL2 backend (Windows)
- Git
- Python 3.12+ (only needed to run `scripts/test_publish.py` locally)

### 1 — Clone & configure

```bash
git clone https://github.com/mostafa-html/farmplus.git
cd farmplus
cp .env.example .env
```

Open `.env` and set at minimum:
- `DJANGO_SECRET_KEY` — generate with `python -c "import secrets; print(secrets.token_urlsafe(64))"`
- `POSTGRES_PASSWORD` — any strong password
- `EMQX_NODE_COOKIE` — any random string
- `EMQX_DASHBOARD_PASSWORD` — any password

### 2 — Build the image

```bash
docker build -t farmpulse-app:latest .
```

> **Iran / restricted networks:** Use local mirrors to speed up the build:
> ```bash
> docker build \
>   --build-arg APT_MIRROR=https://repo.abrha.net/debian \
>   --build-arg PIP_MIRROR=https://package-mirror.liara.ir/repository/pypi/simple \
>   -t farmpulse-app:latest .
> ```

### 3 — Start the stack

```bash
docker compose -f docker-compose.prod.yml up -d
```

The `init` service runs automatically on first start:
- Applies all database migrations
- Seeds development devices (3 orgs, 7 farms, 12 devices)
- Resets the Redis consumer group to position 0

All other services wait for `init` to complete before starting.

### 4 — Verify

```bash
# All containers healthy?
docker compose -f docker-compose.prod.yml ps

# API docs
open http://localhost:8001/api/docs

# DB has data after publishing a test message (see below)
docker exec farmpulse_timescaledb psql -U farmpulse_user -d farmpulse \
  -c "SELECT d.slug, COUNT(*) FROM telemetry_telemetryreading r JOIN devices_device d ON d.id=r.device_id GROUP BY d.slug;"
```

### 5 — Publish a test message

Install `paho-mqtt` locally, then run the test publisher:

```bash
pip install paho-mqtt python-dotenv
python scripts/test_publish.py
```

Within 2–5 seconds the reading appears in TimescaleDB and the Celery logs show `[<msg-id>] OK Step 1 | schema v1.0`.

---

## Django Admin

```bash
# Create a superuser
docker exec -it farmpulse_django python manage.py createsuperuser

# Then open
open http://localhost:8001/admin/
```

---

## EMQX Dashboard

The dashboard port (18083) is not exposed in production for security reasons.

**Access via CLI:**
```bash
docker exec farmpulse_emqx emqx_ctl status
docker exec farmpulse_emqx emqx_ctl broker info
```

**Temporarily expose for local debugging** — add to the `emqx` service ports in `docker-compose.prod.yml`:
```yaml
- "18083:18083"
```
Then visit `http://localhost:18083` (login: `admin` / your `EMQX_DASHBOARD_PASSWORD`).

---

## Monitoring

```bash
# Celery live logs
docker logs -f farmpulse_celery

# Redis stream status
docker exec farmpulse_redis redis-cli XINFO GROUPS telemetry:stream

# Pending messages (should stay near 0)
docker exec farmpulse_redis redis-cli XLEN telemetry:stream
```

---

## Teardown

```bash
# Stop all containers
docker compose -f docker-compose.prod.yml down

# Full reset (removes all data volumes)
docker compose -f docker-compose.prod.yml down -v
```

---

## Project Structure

```
farmplus/
├── apps/
│   ├── devices/          # Organization, Farm, Device models
│   ├── telemetry/        # MQTT subscriber, Redis stream pipeline, Celery tasks
│   └── realtime/         # WebSocket consumers, Pub/Sub relay
├── config/
│   ├── settings/         # base.py, production.py, local.py
│   ├── asgi.py
│   └── celery.py
├── scripts/
│   ├── seed_dev_data.py  # Seeds orgs/farms/devices + resets Redis group
│   └── test_publish.py   # Sends one MQTT message to localhost:1883
├── Dockerfile
├── docker-compose.prod.yml
├── .env.example          # ← copy to .env before first run
└── requirements.txt
```
