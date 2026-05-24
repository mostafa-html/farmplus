# apps/telemetry/mqtt_subscriber.py
"""
MQTT Subscriber — Bridge between EMQX and Redis Stream.

Responsibility: Receive raw MQTT payloads and write them
to the Redis Stream for durable processing by Celery workers.

This process must run alongside Django. In development:
    python -m apps.telemetry.mqtt_subscriber

In production (Phase 12): runs as a separate Docker service.
"""

import os
import sys
import json
import time
import logging
import django

# --- Django setup (must happen before any app imports) ---
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
# Respect an already-set DJANGO_SETTINGS_MODULE; fall back to production (not local)
os.environ["DJANGO_SETTINGS_MODULE"] = os.environ.get(
    "DJANGO_SETTINGS_MODULE", "config.settings.production"
)
django.setup()

# --- Now safe to import Django-dependent modules ---
from django.conf import settings
import redis
import paho.mqtt.client as mqtt

logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────
# Configuration (reads from Django settings / .env)
# ──────────────────────────────────────────────
# Inside Docker the EMQX service is reachable via its compose service name "emqx".
# Outside Docker (local dev) override with: EMQX_HOST=localhost EMQX_PORT=1883
MQTT_HOST     = os.environ.get("EMQX_HOST", "emqx")
MQTT_PORT     = int(os.environ.get("EMQX_PORT", 1883))
MQTT_USERNAME = os.environ.get("EMQX_USERNAME", "")
MQTT_PASSWORD = os.environ.get("EMQX_PASSWORD", "")
import uuid
MQTT_CLIENT_ID = f"farmpulse-subscriber-{uuid.uuid4().hex[:8]}"
MQTT_TOPIC    = "+/farms/+/gateways/+/telemetry"
MQTT_QOS      = 1                                              # at-least-once delivery

REDIS_STREAM_KEY = settings.TELEMETRY_REDIS_STREAM_KEY        # "telemetry:stream"
REDIS_MAXLEN     = 10_000                                      # cap stream at 10k entries in dev


# ──────────────────────────────────────────────
# Redis connection
# ──────────────────────────────────────────────
redis_client = redis.Redis.from_url(
    settings.REDIS_URL,
    decode_responses=True,  # return strings, not bytes
)


# ──────────────────────────────────────────────
# MQTT Callbacks
# ──────────────────────────────────────────────
def on_connect(client, userdata, flags, reason_code, properties):
    if reason_code == 0:
        logger.info(f"[MQTT] Connected to EMQX at {MQTT_HOST}:{MQTT_PORT}")
        # Subscribe immediately on connect — also re-subscribes on reconnect
        client.subscribe(MQTT_TOPIC, qos=MQTT_QOS)
        logger.info(f"[MQTT] Subscribed to topic: {MQTT_TOPIC}")
    else:
        logger.error(f"[MQTT] Connection failed with reason code: {reason_code}")


def on_message(client, userdata, msg):
    """
    Called for every incoming MQTT message.
    Critical path — keep this fast. No business logic here.
    """
    try:
        payload_str = msg.payload.decode("utf-8")
        received_ts = int(time.time() * 1000)  # milliseconds

        # Write to Redis Stream
        # XADD returns the stream entry ID (e.g. "1746260400000-0")
        entry_id = redis_client.xadd(
            REDIS_STREAM_KEY,
            {
                "payload":     payload_str,
                "topic":       msg.topic,
                "received_ts": str(received_ts),
            },
            maxlen=REDIS_MAXLEN,
            approximate=True,   # ~MAXLEN — faster than exact trimming
        )
        logger.debug(f"[STREAM] Written entry {entry_id} from topic {msg.topic}")

    except Exception as e:
        # Log and continue — never crash the subscriber on a single bad message
        logger.error(f"[STREAM] Failed to write message to Redis Stream: {e}")


def on_disconnect(client, userdata, flags, reason_code, properties):
    if reason_code != 0:
        logger.warning(f"[MQTT] Unexpected disconnect (code {reason_code}). Will auto-reconnect.")


def on_subscribe(client, userdata, mid, reason_codes, properties):
    logger.info(f"[MQTT] Subscription confirmed (mid={mid})")


# ──────────────────────────────────────────────
# Main
# ──────────────────────────────────────────────
def main():
    logging.basicConfig(
        level=logging.DEBUG,
        format="%(asctime)s [%(levelname)s] %(message)s",
    )

    # Verify Redis is reachable before starting
    try:
        redis_client.ping()
        logger.info("[REDIS] Connection verified.")
    except Exception as e:
        logger.critical(f"[REDIS] Cannot connect to Redis: {e}")
        sys.exit(1)

    # Build MQTT client (paho-mqtt v2 API)
    client = mqtt.Client(
        client_id=MQTT_CLIENT_ID,
        protocol=mqtt.MQTTv5,
        callback_api_version=mqtt.CallbackAPIVersion.VERSION2,
    )

    if MQTT_USERNAME:
        client.username_pw_set(MQTT_USERNAME, MQTT_PASSWORD)

    # Wire up callbacks
    client.on_connect    = on_connect
    client.on_message    = on_message
    client.on_disconnect = on_disconnect
    client.on_subscribe  = on_subscribe

    # Auto-reconnect settings
    client.reconnect_delay_set(min_delay=1, max_delay=30)

    logger.info(f"[MQTT] Connecting to {MQTT_HOST}:{MQTT_PORT}...")
    client.connect(MQTT_HOST, MQTT_PORT, keepalive=60)

    # Blocking loop — runs forever, handles reconnects automatically
    client.loop_forever()


if __name__ == "__main__":
    main()
