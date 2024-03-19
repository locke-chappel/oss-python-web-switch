import framebuf
import micropython

DEBUG = const(False)

WIFI_SSID = const("")
WIFI_PASS = const("")
WIFI_RECONNECT_INTERVAL = const(5 * 60)

SHARED_SECRETS = micropython.const([micropython.const("")])

MAX_TTL = const(5)

RESTORE_ON_BOOT = const(True)
