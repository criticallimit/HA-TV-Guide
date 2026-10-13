"""Constants for the TV Guide migration bridge."""
DOMAIN = "tv_guide"
SOURCE = "criticallimit/TV-Guide"
SENSORS = {
    "next_reminder": ("sensor.tv_guide_next_reminder", "Next reminder", "mdi:alarm", True),
    "bookmark_count": ("sensor.tv_guide_bookmark_count", "Bookmark count", "mdi:bookmark", False),
    "reminder_count": ("sensor.tv_guide_reminder_count", "Reminder count", "mdi:alarm-check", False),
    "last_update": ("sensor.tv_guide_last_update", "Last EPG update", "mdi:update", True),
}
REFRESH_SOURCE = "binary_sensor.tv_guide_refresh_running"
