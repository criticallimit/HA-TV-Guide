"""Reference option names; native HA entities own state publication."""
SENSOR_OPTIONS = {
    "sensor_next_reminder": ("sensor.tv_guide_next_reminder", "Nächste Erinnerung", "mdi:alarm", "timestamp"),
    "sensor_bookmark_count": ("sensor.tv_guide_bookmark_count", "Gemerkte Sendungen", "mdi:bookmark", None),
    "sensor_reminder_count": ("sensor.tv_guide_reminder_count", "Ausstehende Erinnerungen", "mdi:alarm-check", None),
    "sensor_last_update": ("sensor.tv_guide_last_update", "Letzte EPG-Aktualisierung", "mdi:update", "timestamp"),
    "sensor_refresh_running": ("binary_sensor.tv_guide_refresh_running", "EPG-Aktualisierung läuft", "mdi:sync", None),
}

class SensorPublisher:
    def __init__(self, runtime):
        self.runtime = runtime
