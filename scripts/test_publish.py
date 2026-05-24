# scripts/test_publish.py
# Publishes a single test telemetry message to EMQX.
# Run from the project root: python scripts/test_publish.py
#
# Override connection settings via environment variables:
#   EMQX_HOST  (default: localhost)
#   EMQX_PORT  (default: 1883)
#   EMQX_USERNAME / EMQX_PASSWORD  (optional, for authenticated brokers)

import json, time, os
import paho.mqtt.client as mqtt
from dotenv import load_dotenv

load_dotenv()

MQTT_HOST = os.environ.get("EMQX_HOST", "localhost")
MQTT_PORT = int(os.environ.get("EMQX_PORT", 1883))  # compose exposes 1883
MQTT_USERNAME = os.environ.get("EMQX_USERNAME", "")
MQTT_PASSWORD = os.environ.get("EMQX_PASSWORD", "")

PAYLOAD = {
    "schema_version": "1.0",
    "org_id":    "org-sunrise",
    "farm_id":   "farm-01",
    "device_id": "gw-lora-001",
    "sent_ts":   int(time.time() * 1000),
    "seq":       1,
    "is_buffered": False,
    "readings": {
        "temperature": 24.7,
        "humidity":    63.2,
        "lux":         320.0,
        "nh3":         12.5
    }
}

client = mqtt.Client(
    client_id="test-publisher",
    protocol=mqtt.MQTTv5,
    callback_api_version=mqtt.CallbackAPIVersion.VERSION2,
)

if MQTT_USERNAME:
    client.username_pw_set(MQTT_USERNAME, MQTT_PASSWORD)

print(f"Connecting to EMQX at {MQTT_HOST}:{MQTT_PORT}...")
client.connect(MQTT_HOST, MQTT_PORT)
client.publish(
    topic="org-sunrise/farms/farm-01/gateways/gw-lora-001/telemetry",
    payload=json.dumps(PAYLOAD),
    qos=1,
)
client.disconnect()
print("[OK] Published test message to EMQX")
