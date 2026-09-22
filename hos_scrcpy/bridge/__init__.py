"""Bridge layer — pure-Python streaming (no Java/JAR).

Video: gRPC client to the device-side scrcpy extension (H.264).
Touch: uitest daemon JSON socket (Gestures events).
"""
from hos_scrcpy.bridge.native_stream import (
    start_native_bridge,
    read_frames,
    HosStreamBridge,
    HosVideoStream,
    HosTouchChannel,
)
