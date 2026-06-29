"""WebSocket remote-control server for HOScrcpy.

Usage:
    python -m hos_scrcpy.server.ws_server --sn DEVICE_SN --port 8765
"""
# Lazy import to avoid circular import with -m
def start_server(*args, **kwargs):
    from hos_scrcpy.server.ws_server import start_server as _start
    return _start(*args, **kwargs)

