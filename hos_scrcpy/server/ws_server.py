"""WebSocket server for remote device screen mirroring and touch control.

Usage:
    python -m hos_scrcpy.server.ws_server --port 8765
    # Then open http://localhost:8765 in a browser

Or programmatically:
    from hos_scrcpy.server.ws_server import ScreenServer
    server = ScreenServer(port=8765)
    server.attach_device("SN123456")
    server.start()
"""

import asyncio
import hashlib
import base64
import json
import struct
import threading
from hos_scrcpy.utils.logger import logger

TAG = "WSServer"

_HTML_PAGE = """<!DOCTYPE html>
<html lang="zh">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>HOScrcpy Web</title>
<style>
*{margin:0;padding:0;box-sizing:border-box}
body{background:#1a1a1a;display:flex;flex-direction:column;align-items:center;height:100vh;overflow:hidden;font-family:monospace}
#toolbar{display:flex;gap:8px;padding:8px;background:#2a2a2a;width:100%;flex-wrap:wrap}
#toolbar button,#toolbar input{padding:6px 12px;border:none;border-radius:4px;cursor:pointer;font-family:monospace}
#toolbar button{background:#007AFF;color:#fff}
#toolbar button:active{opacity:.8}
#toolbar input{background:#333;color:#fff;border:1px solid #555;width:180px}
#canvas{flex:1;object-fit:contain;max-width:100vw;max-height:calc(100vh - 56px);touch-action:none;cursor:crosshair}
#status{color:#888;font-size:11px;padding:2px 8px;width:100%;text-align:center}
</style>
</head>
<body>
<div id="toolbar">
  <input id="device" placeholder="Device SN (auto-detect)" />
  <button onclick="doConnect()">Connect</button>
  <button onclick="sendKey('power')">Power</button>
  <button onclick="sendKey('home')">Home</button>
  <button onclick="sendKey('back')">Back</button>
</div>
<canvas id="canvas"></canvas>
<div id="status">Disconnected - Click Connect</div>
<script>
var ws, canvas = document.getElementById('canvas'), ctx = canvas.getContext('2d'), img = new Image();

function doConnect() {
  if (ws) { ws.close(); }
  var sn = document.getElementById('device').value || '';
  ws = new WebSocket((location.protocol==='https:'?'wss:':'ws:')+'//'+location.host+'/ws?sn='+encodeURIComponent(sn));
  ws.binaryType = 'arraybuffer';
  ws.onopen = function() { document.getElementById('status').textContent = 'Connected - streaming...'; };
  ws.onmessage = function(e) {
    if (typeof e.data === 'string') {
      try { var m = JSON.parse(e.data); if (m.type==='status') document.getElementById('status').textContent=m.text; } catch(_){}
      return;
    }
    var buf = new Uint8Array(e.data);
    var len = (buf[0]<<24)|(buf[1]<<16)|(buf[2]<<8)|buf[3];
    if (len<=0||len>10000000) return;
    var blob = new Blob([buf.slice(4,4+len)],{type:'image/jpeg'});
    var url = URL.createObjectURL(blob);
    img.onload = function() {
      canvas.width = img.width; canvas.height = img.height;
      ctx.drawImage(img,0,0); URL.revokeObjectURL(url);
    };
    img.src = url;
  };
  ws.onclose = function() { document.getElementById('status').textContent = 'Disconnected'; };
  ws.onerror = function() { document.getElementById('status').textContent = 'Connection error'; };
}

function sendKey(k) { if (ws) ws.send(JSON.stringify({type:'key',key:k})); }

function getDeviceXY(e) {
  var r = canvas.getBoundingClientRect();
  return {x: Math.round((e.clientX-r.left)*(canvas.width/r.width)), y: Math.round((e.clientY-r.top)*(canvas.height/r.height))};
}
canvas.addEventListener('pointerdown', function(e) {
  e.preventDefault(); if (!ws) return;
  var p = getDeviceXY(e);
  ws.send(JSON.stringify({type:'touch',event:'down',x:p.x,y:p.y}));
  canvas.setPointerCapture(e.pointerId);
});
canvas.addEventListener('pointermove', function(e) {
  e.preventDefault(); if (!ws||!canvas.hasPointerCapture(e.pointerId)) return;
  var p = getDeviceXY(e);
  ws.send(JSON.stringify({type:'touch',event:'move',x:p.x,y:p.y}));
});
canvas.addEventListener('pointerup', function(e) {
  e.preventDefault(); if (!ws) return;
  var p = getDeviceXY(e);
  ws.send(JSON.stringify({type:'touch',event:'up',x:p.x,y:p.y}));
});
canvas.addEventListener('wheel', function(e) {
  e.preventDefault(); if (!ws) return;
  var p = getDeviceXY(e);
  ws.send(JSON.stringify({type:'wheel',delta:e.deltaY>0?-200:200,x:p.x,y:p.y}));
});
</script>
</body>
</html>"""

WS_GUID = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"


class ScreenServer:
    """WebSocket server that streams device screen and relays touch events."""

    def __init__(self, port: int = 8765, host: str = "0.0.0.0"):
        self._port = port
        self._host = host
        self._clients: set = set()
        self._device = None
        self._capture = None
        self._touch = None
        self._keyboard = None
        self._running = False
        self._latest_frame: bytes | None = None
        self._loop = None

    def attach_device(self, sn: str, ip: str = "127.0.0.1", port: str = "8710"):
        """Attach a device and start streaming."""
        from hos_scrcpy.core.device import Device
        from hos_scrcpy.input.keyboard import KeyboardController
        from hos_scrcpy.screen.capture import ScreenCapture

        self._device = Device(sn=sn, ip=ip, port=port)
        if not self._device.is_online():
            raise ConnectionError(f"Device {sn} is offline")

        self._keyboard = KeyboardController(self._device)
        self._capture = ScreenCapture(self._device)
        self._touch = self._capture.start_java_stream(self._on_frame)
        if self._touch is None:
            self._capture.start_screenshot_stream(self._on_frame, interval=0.5)
            logger.info(f"{TAG}: screenshot mode (Java unavailable)")
        logger.info(f"{TAG}: device {sn} attached")

    def _on_frame(self, jpeg: bytes):
        """Called from capture thread — push frame to asyncio queue."""
        if jpeg and len(jpeg) > 1000:
            self._latest_frame = jpeg
            # Wake up the asyncio broadcast task
            if self._loop and self._loop.is_running():
                self._loop.call_soon_threadsafe(self._frame_event.set)

    def start(self, blocking: bool = True):
        """Start the WebSocket server."""
        self._running = True
        self._frame_event = asyncio.Event()
        if blocking:
            asyncio.run(self._serve())
        else:
            threading.Thread(target=lambda: asyncio.run(self._serve()), daemon=True).start()

    async def _broadcast_task(self):
        """Asyncio task: broadcast frames to all clients when signaled."""
        last_sent = None
        tick = 0
        while self._running:
            try:
                # Wait for new frame or 50ms timeout (keep-alive)
                await asyncio.wait_for(self._frame_event.wait(), timeout=0.05)
                self._frame_event.clear()
            except asyncio.TimeoutError:
                pass

            frame = self._latest_frame
            if frame is None or frame is last_sent:
                continue

            # Send to all clients concurrently
            data = self._build_ws_frame(frame)
            dead = set()
            tasks = []
            for writer in list(self._clients):
                tasks.append(self._safe_send(writer, data, dead))
            if tasks:
                await asyncio.gather(*tasks)
            self._clients -= dead
            last_sent = frame

    async def _safe_send(self, writer, data: bytes, dead: set):
        """Send frame data to one client, track failures."""
        try:
            writer.write(data)
            await writer.drain()
        except Exception:
            dead.add(writer)

    @staticmethod
    def _build_ws_frame(jpeg: bytes) -> bytes:
        """Build a binary WebSocket frame from JPEG bytes."""
        data = struct.pack(">I", len(jpeg)) + jpeg
        frame = bytearray()
        frame.append(0x82)  # FIN + binary
        length = len(data)
        if length < 126:
            frame.append(length)
        elif length < 65536:
            frame.append(126)
            frame.extend(struct.pack(">H", length))
        else:
            frame.append(127)
            frame.extend(struct.pack(">Q", length))
        frame.extend(data)
        return bytes(frame)

    async def _serve(self):
        """Main async server loop."""
        self._loop = asyncio.get_running_loop()
        self._server = await asyncio.start_server(
            self._handle_connection, self._host, self._port
        )
        # Start the event-driven broadcast task
        broadcast = asyncio.create_task(self._broadcast_task())
        logger.info(f"{TAG}: server listening on http://{self._host}:{self._port}")
        logger.info(f"{TAG}: open browser → http://localhost:{self._port}")
        async with self._server:
            await self._server.serve_forever()
        broadcast.cancel()

    async def _handle_connection(self, reader, writer):
        """Route HTTP vs WebSocket."""
        try:
            request = await asyncio.wait_for(reader.readuntil(b"\r\n\r\n"), timeout=10)
        except Exception:
            writer.close()
            return

        request_text = request.decode("utf-8", errors="replace")
        if "Upgrade: websocket" not in request_text:
            await self._http_handler(writer, request_text)
        else:
            await self._ws_handler(reader, writer, request_text)

    async def _http_handler(self, writer, request_text):
        """Serve the HTML page."""
        body = _HTML_PAGE.encode()
        cl = f"Content-Length: {len(body)}\r\n".encode()
        writer.write(
            b"HTTP/1.1 200 OK\r\n"
            b"Content-Type: text/html; charset=utf-8\r\n"
            + cl +
            b"Connection: close\r\n\r\n"
            + body
        )
        await writer.drain()
        writer.close()

    async def _ws_handler(self, reader, writer, request_text):
        """Handle WebSocket upgrade and messaging."""
        # Extract key for handshake
        key = ""
        for line in request_text.split("\r\n"):
            if line.lower().startswith("sec-websocket-key:"):
                key = line.split(":", 1)[1].strip()
                break

        accept = base64.b64encode(
            hashlib.sha1((key + WS_GUID).encode()).digest()
        ).decode()

        writer.write(
            f"HTTP/1.1 101 Switching Protocols\r\n"
            f"Upgrade: websocket\r\n"
            f"Connection: Upgrade\r\n"
            f"Sec-WebSocket-Accept: {accept}\r\n"
            f"\r\n"
            .encode()
        )
        await writer.drain()

        self._clients.add(writer)
        logger.info(f"{TAG}: client connected ({len(self._clients)} total)")

        # Send initial frame
        if self._latest_frame:
            try:
                writer.write(self._build_ws_frame(self._latest_frame))
                await writer.drain()
            except Exception:
                pass

        try:
            while self._running:
                msg = await self._read_ws_msg(reader)
                if msg is None:
                    break
                self._handle_msg(msg)
        except Exception:
            pass
        finally:
            self._clients.discard(writer)
            try:
                writer.close()
            except Exception:
                pass
            logger.info(f"{TAG}: client disconnected ({len(self._clients)} remaining)")

    async def _read_ws_msg(self, reader) -> dict | None:
        """Read a WebSocket frame and parse JSON text message."""
        try:
            b0 = await asyncio.wait_for(reader.readexactly(1), timeout=120)
            opcode = b0[0] & 0x0F
            if opcode == 0x8:
                return None  # close
            if opcode == 0x9:
                self._skip_ws_payload(reader)
                return {}
            if opcode == 0xA:
                return {}

            b1 = await asyncio.wait_for(reader.readexactly(1), timeout=10)
            mask = (b1[0] & 0x80) != 0
            length = b1[0] & 0x7F
            if length == 126:
                length = struct.unpack(">H", await asyncio.wait_for(reader.readexactly(2), timeout=10))[0]
            elif length == 127:
                length = struct.unpack(">Q", await asyncio.wait_for(reader.readexactly(8), timeout=10))[0]

            mask_key = await asyncio.wait_for(reader.readexactly(4), timeout=10) if mask else b""
            payload = await asyncio.wait_for(reader.readexactly(length), timeout=10)
            if mask:
                payload = bytes(b ^ mask_key[i % 4] for i, b in enumerate(payload))

            return json.loads(payload.decode("utf-8")) if opcode == 0x1 else {}
        except Exception:
            return None

    async def _skip_ws_payload(self, reader):
        """Skip WebSocket payload bytes (used for ping frames we don't need to read)."""
        try:
            b1 = await asyncio.wait_for(reader.readexactly(1), timeout=5)
            length = b1[0] & 0x7F
            mask = (b1[0] & 0x80) != 0
            if length == 126:
                length = struct.unpack(">H", await asyncio.wait_for(reader.readexactly(2), timeout=5))[0]
            elif length == 127:
                length = struct.unpack(">Q", await asyncio.wait_for(reader.readexactly(8), timeout=5))[0]
            if mask:
                await asyncio.wait_for(reader.readexactly(4), timeout=5)
            await asyncio.wait_for(reader.readexactly(length), timeout=5)
        except Exception:
            pass

    def _handle_msg(self, msg: dict):
        """Handle a JSON message from a web client."""
        msg_type = msg.get("type", "")
        if msg_type == "touch":
            event = msg.get("event", "")
            x, y = int(msg.get("x", 0)), int(msg.get("y", 0))
            if self._touch:
                if event == "down":
                    self._touch.down(x, y)
                elif event == "move":
                    self._touch.move(x, y)
                elif event == "up":
                    self._touch.up(x, y)
        elif msg_type == "key":
            key = msg.get("key", "")
            if self._keyboard:
                if key == "power":
                    self._keyboard.power()
                elif key == "home":
                    self._keyboard.home()
                elif key == "back":
                    self._keyboard.back()

    def stop(self):
        self._running = False
        if self._capture:
            self._capture.stop()
        if self._server:
            self._server.close()


def start_server(port: int = 8765, device_sn: str = None):
    """Convenience: start a server with optional device auto-attach."""
    server = ScreenServer(port=port)
    if device_sn:
        server.attach_device(device_sn)
    else:
        from hos_scrcpy.core.device import Device
        devices = Device.list_all()
        if devices:
            d = devices[0]
            server.attach_device(d.sn, d.ip, d.port)
            logger.info(f"{TAG}: auto-attached {d}")
        else:
            logger.warning(f"{TAG}: no devices found, server empty")
    server.start()


if __name__ == "__main__":
    import argparse
    from hos_scrcpy.utils.logger import setup_logging
    setup_logging()

    p = argparse.ArgumentParser(description="HOScrcpy WebSocket Server")
    p.add_argument("--port", type=int, default=8765)
    p.add_argument("--sn", type=str, default="")
    p.add_argument("--ip", type=str, default="127.0.0.1")
    p.add_argument("--hdc-port", type=str, default="8710")
    args = p.parse_args()

    server = ScreenServer(port=args.port)
    if args.sn:
        server.attach_device(args.sn, args.ip, args.hdc_port)
    else:
        from hos_scrcpy.core.device import Device
        devices = Device.list_all()
        if devices:
            d = devices[0]
            server.attach_device(d.sn, d.ip, d.port)
            logger.info(f"Auto-attached: {d}")
        else:
            logger.warning("No devices found. Start server empty.")
    server.start()
