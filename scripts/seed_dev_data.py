import os, sys, django

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
# Respect an already-set DJANGO_SETTINGS_MODULE; fall back to production (not local)
os.environ["DJANGO_SETTINGS_MODULE"] = os.environ.get(
    "DJANGO_SETTINGS_MODULE", "config.settings.production"
)
django.setup()

from apps.devices.models import Organization, Farm, Device

# ─── Data Definition ──────────────────────────────────────────────────────────────────

SEED_DATA = [
    {
        "org": {"slug": "org-sunrise", "name": "Sunrise Poultry Co."},
        "farms": [
            {
                "slug": "farm-01",
                "name": "Farm Alpha",
                "devices": [
                    {"slug": "gw-lora-001", "name": "LoRa Gateway 001", "status": "active",
                     "sensor_capabilities": ["temperature", "humidity"], "firmware_version": "1.0.0"},
                    {"slug": "gw-lora-002", "name": "LoRa Gateway 002", "status": "active",
                     "sensor_capabilities": ["temperature", "humidity", "lux"], "firmware_version": "1.0.1"},
                ],
            },
            {
                "slug": "farm-02",
                "name": "Farm Beta",
                "devices": [
                    {"slug": "gw-lora-003", "name": "LoRa Gateway 003", "status": "active",
                     "sensor_capabilities": ["temperature", "humidity", "nh3"], "firmware_version": "1.0.1"},
                    {"slug": "gw-lora-004", "name": "LoRa Gateway 004", "status": "inactive",
                     "sensor_capabilities": ["temperature", "humidity"], "firmware_version": "1.0.0"},
                ],
            },
        ],
    },
    {
        "org": {"slug": "org-greenvalley", "name": "Green Valley Farms Ltd."},
        "farms": [
            {
                "slug": "farm-gv-01",
                "name": "North Greenhouse",
                "devices": [
                    {"slug": "gw-gv-001", "name": "GV North Gateway 001", "status": "active",
                     "sensor_capabilities": ["temperature", "humidity", "lux"], "firmware_version": "1.1.0"},
                    {"slug": "gw-gv-002", "name": "GV North Gateway 002", "status": "active",
                     "sensor_capabilities": ["temperature", "humidity", "lux", "nh3"], "firmware_version": "1.1.0"},
                ],
            },
            {
                "slug": "farm-gv-02",
                "name": "South Greenhouse",
                "devices": [
                    {"slug": "gw-gv-003", "name": "GV South Gateway 001", "status": "active",
                     "sensor_capabilities": ["temperature", "humidity"], "firmware_version": "1.0.2"},
                ],
            },
            {
                "slug": "farm-gv-03",
                "name": "Open Field A",
                "devices": [
                    {"slug": "gw-gv-004", "name": "GV Field Gateway 001", "status": "active",
                     "sensor_capabilities": ["temperature", "humidity", "lux"], "firmware_version": "1.1.0"},
                    {"slug": "gw-gv-005", "name": "GV Field Gateway 002", "status": "stolen",  # Phase 9
                     "sensor_capabilities": ["temperature", "humidity"], "firmware_version": "1.0.0"},
                ],
            },
        ],
    },
    {
        "org": {"slug": "org-tehranagri", "name": "Tehran Agri Systems"},
        "farms": [
            {
                "slug": "farm-ta-01",
                "name": "Pilot Farm East",
                "devices": [
                    {"slug": "gw-ta-001", "name": "TA East Gateway 001", "status": "active",
                     "sensor_capabilities": ["temperature", "humidity", "nh3"], "firmware_version": "1.0.3"},
                    {"slug": "gw-ta-002", "name": "TA East Gateway 002", "status": "active",
                     "sensor_capabilities": ["temperature", "humidity"], "firmware_version": "1.0.3"},
                ],
            },
            {
                "slug": "farm-ta-02",
                "name": "Pilot Farm West",
                "devices": [
                    {"slug": "gw-ta-003", "name": "TA West Gateway 001", "status": "inactive",
                     "sensor_capabilities": ["temperature", "humidity", "lux"], "firmware_version": "0.9.5"},
                ],
            },
        ],
    },
]

# ─── Seeding Logic ──────────────────────────────────────────────────────────────────

total_orgs = total_farms = total_devices = 0

for entry in SEED_DATA:
    org, created = Organization.objects.get_or_create(
        slug=entry["org"]["slug"],
        defaults={"name": entry["org"]["name"]},
    )
    print(f"{'[CREATED]' if created else '[EXISTS] '} Organization: {org.slug}")
    if created:
        total_orgs += 1

    for farm_data in entry["farms"]:
        devices = farm_data.pop("devices")
        farm, created = Farm.objects.get_or_create(
            slug=farm_data["slug"],
            organization=org,
            defaults={"name": farm_data["name"]},
        )
        print(f"  {'[CREATED]' if created else '[EXISTS] '} Farm: {farm.slug}")
        if created:
            total_farms += 1

        for dev_data in devices:
            device, created = Device.objects.get_or_create(
                slug=dev_data["slug"],
                defaults={
                    "farm": farm,
                    "name": dev_data["name"],
                    "status": dev_data["status"],
                    "sensor_capabilities": dev_data["sensor_capabilities"],
                    "firmware_version": dev_data["firmware_version"],
                },
            )
            print(f"    {'[CREATED]' if created else '[EXISTS] '} Device: {device.slug} ({dev_data['status']})")
            if created:
                total_devices += 1

print(f"\n[OK] Seed complete — {total_orgs} orgs, {total_farms} farms, {total_devices} devices added.")

# ─── Reset Redis consumer group so the PEL never gets stuck ───────────────────
# On first run: creates the group starting from position 0 (reprocess all messages).
# On subsequent runs: group already exists, the except block is silently skipped.

import redis as redis_lib
from django.conf import settings

redis_url = getattr(settings, "REDIS_URL", os.environ.get("REDIS_URL", "redis://redis:6379/0"))
r = redis_lib.from_url(redis_url)

try:
    r.xgroup_destroy("telemetry:stream", "pipeline-workers")
except Exception:
    pass

try:
    r.xgroup_create("telemetry:stream", "pipeline-workers", id="0", mkstream=True)
    print("[OK] Redis consumer group reset to position 0")
except Exception as e:
    print(f"[WARN] Could not reset consumer group: {e}")
