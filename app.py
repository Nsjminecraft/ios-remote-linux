"""
iPhone Screen Mirror & Control for Linux (pymobiledevice3 native, iOS 17+).

Replaces the old tidevice + WebDriverAgent approach. Uses CoreDevice services
directly — no Xcode, no WDA signing, no jailbreak.

Usage:
    1. Ensure tunneld is running: sudo pymobiledevice3 tunneld start
    2. Connect iPhone via USB with developer mode enabled
    3. python app.py
    4. Open http://localhost:5000 in a browser
"""

import asyncio
import json
import os
import subprocess
import threading
import time
from pathlib import Path

from flask import Flask, Response, jsonify, render_template, request
from flask_cors import CORS

from pymobiledevice3.remote.core_device.hid_service import (
    ASCII_TO_HID,
    DIGITIZER_SURFACE_MAIN_TOUCHSCREEN,
    HID_BUTTON_STATE_DOWN,
    HID_BUTTON_STATE_UP,
    KEY_LEFT_SHIFT,
    TOUCHSCREEN_STATE_CONTACT,
    TOUCHSCREEN_STATE_RELEASE,
    IndigoHIDService,
    UniversalHIDServiceService,
    touch_session,
)
from pymobiledevice3.remote.core_device.orientation_service import OrientationService
from pymobiledevice3.remote.core_device.screen_capture_service import ScreenCaptureService
from pymobiledevice3.remote.core_device.screen_stream import ScreenStreamServer
from pymobiledevice3.tunneld.api import get_tunneld_devices

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
FLASK_PORT = 5000
STREAM_PORT = 8080
STREAM_BIND = "127.0.0.1"
SCREENSHOT_DIR = Path(__file__).parent / "screenshot"
SCREENSHOT_DIR.mkdir(exist_ok=True)
RECORDING_DIR = Path(__file__).parent / "recordings"
RECORDING_DIR.mkdir(exist_ok=True)

# ---------------------------------------------------------------------------
# Global state
# ---------------------------------------------------------------------------
rsd = None  # RemoteServiceDiscoveryService for the connected device
loop = None  # asyncio event loop running in a background thread
stream_server = None  # ScreenStreamServer instance
recording_process = None  # subprocess for ffmpeg recording

# Named buttons: name -> (usage_page, usage_code, hold_seconds)
_NAMED_BUTTONS = {
    "home": (0x0C, 0x40, 0.05),
    "lock": (0x0C, 0x30, 0.5),
    "volume-up": (0x0C, 0xE9, 0.05),
    "volume-down": (0x0C, 0xEA, 0.05),
    "mute": (0x0C, 0xE2, 0.05),
    "siri": (0x0C, 0xCF, 1.0),
}


def _run_async(coro):
    """Run an async coroutine on the background event loop from sync Flask code."""
    future = asyncio.run_coroutine_threadsafe(coro, loop)
    return future.result(timeout=15)


# ---------------------------------------------------------------------------
# Background asyncio thread — runs ScreenStreamServer + service connections
# ---------------------------------------------------------------------------
def _start_async_loop():
    global loop, rsd, stream_server
    loop = asyncio.new_event_loop()

    def _run():
        asyncio.set_event_loop(loop)
        loop.run_forever()

    t = threading.Thread(target=_run, daemon=True)
    t.start()

    # Discover connected devices via tunneld
    devices = _run_async(get_tunneld_devices())
    if not devices:
        raise RuntimeError(
            "No connected iPhone found. Ensure:\n"
            "  1. tunneld is running: sudo pymobiledevice3 tunneld start\n"
            "  2. iPhone is connected via USB\n"
            "  3. Developer mode is enabled on the iPhone"
        )
    rsd = devices[0]
    print(f"Connected to device: {rsd.name or 'iPhone'}")

    # Start the screen stream server (HTTP + WebCodecs viewer)
    stream_server = ScreenStreamServer(
        rsd,
        bind=STREAM_BIND,
        http_port=STREAM_PORT,
    )

    # Run serve() as a task on the background loop
    asyncio.run_coroutine_threadsafe(stream_server.serve(), loop)
    print(f"Screen stream server running at http://{STREAM_BIND}:{STREAM_PORT}/")


# ---------------------------------------------------------------------------
# Flask app
# ---------------------------------------------------------------------------
app = Flask(__name__, static_folder="static", template_folder="static")
CORS(app)


@app.route("/")
def index():
    return render_template("index.html", stream_url=f"{STREAM_BIND}:{STREAM_PORT}")


@app.route("/click", methods=["POST"])
def click():
    data = json.loads(request.form.get("data", "{}"))
    x = int(float(data.get("disX", 0)))
    y = int(float(data.get("disY", 0)))
    # Convert 0..1 floats to 0..65535 HID coordinates if needed
    if x <= 1 and y <= 1:
        x = round(x * 65535)
        y = round(y * 65535)
    else:
        x = min(65535, max(0, x))
        y = min(65535, max(0, y))

    async def _tap():
        async with touch_session(rsd) as svc:
            await svc.send_touchscreen(
                TOUCHSCREEN_STATE_CONTACT, x, y,
                service_id=DIGITIZER_SURFACE_MAIN_TOUCHSCREEN,
            )
            await asyncio.sleep(0.05)
            await svc.send_touchscreen(
                TOUCHSCREEN_STATE_RELEASE, x, y,
                service_id=DIGITIZER_SURFACE_MAIN_TOUCHSCREEN,
            )

    _run_async(_tap())
    return jsonify({"status": "ok"})


@app.route("/drag", methods=["POST"])
def drag():
    data = json.loads(request.form.get("data", "{}"))
    x1 = int(float(data.get("disX", 0)))
    y1 = int(float(data.get("disY", 0)))
    x2 = int(float(data.get("toX", 0)))
    y2 = int(float(data.get("toY", 0)))
    # Normalize to 0..65535
    for v in (x1, y1, x2, y2):
        if v <= 1:
            x1, y1, x2, y2 = [round(v * 65535) for v in (x1, y1, x2, y2)]
            break

    async def _drag():
        async with touch_session(rsd) as svc:
            await svc.send_touchscreen(
                TOUCHSCREEN_STATE_CONTACT, x1, y1,
                service_id=DIGITIZER_SURFACE_MAIN_TOUCHSCREEN,
            )
            steps = 30
            for i in range(1, steps + 1):
                ix = x1 + (x2 - x1) * i // steps
                iy = y1 + (y2 - y1) * i // steps
                await svc.send_touchscreen(
                    TOUCHSCREEN_STATE_CONTACT, ix, iy,
                    service_id=DIGITIZER_SURFACE_MAIN_TOUCHSCREEN,
                )
                await asyncio.sleep(0.02)
            await svc.send_touchscreen(
                TOUCHSCREEN_STATE_RELEASE, x2, y2,
                service_id=DIGITIZER_SURFACE_MAIN_TOUCHSCREEN,
            )

    _run_async(_drag())
    return jsonify({"status": "ok"})


@app.route("/home", methods=["POST"])
def home():
    async def _home():
        async with IndigoHIDService(rsd) as svc:
            up, uc, hold = _NAMED_BUTTONS["home"]
            await svc.send_button(up, uc, HID_BUTTON_STATE_DOWN)
            await asyncio.sleep(hold)
            await svc.send_button(up, uc, HID_BUTTON_STATE_UP)

    _run_async(_home())
    return jsonify({"status": "ok"})


@app.route("/lock", methods=["POST"])
def lock():
    async def _lock():
        async with IndigoHIDService(rsd) as svc:
            up, uc, hold = _NAMED_BUTTONS["lock"]
            await svc.send_button(up, uc, HID_BUTTON_STATE_DOWN)
            await asyncio.sleep(hold)
            await svc.send_button(up, uc, HID_BUTTON_STATE_UP)

    _run_async(_lock())
    return jsonify({"status": "ok"})


@app.route("/screenshot", methods=["POST"])
def screenshot():
    async def _screenshot():
        async with ScreenCaptureService(rsd) as svc:
            response = await svc.capture_screenshot()
            return response["image"]

    image_data = _run_async(_screenshot())
    name = time.strftime("%Y-%m-%d-%H-%M-%S", time.localtime())
    path = SCREENSHOT_DIR / f"{name}.png"
    path.write_bytes(image_data)
    return jsonify({"status": "ok", "path": str(path)})


@app.route("/rotation", methods=["POST"])
def rotation():
    async def _rotate():
        async with OrientationService(rsd) as svc:
            return await svc.rotate(direction="right")

    result = _run_async(_rotate())
    return jsonify({"status": "ok", "orientation": result})


@app.route("/send", methods=["POST"])
def send():
    data = json.loads(request.form.get("data", "{}"))
    text = data.get("text", "")
    if not text:
        return jsonify({"status": "error", "message": "empty text"}), 400

    async def _send():
        async with touch_session(rsd) as svc:
            kb_id = await svc.create_keyboard_service()
            for ch in text:
                mapping = ASCII_TO_HID.get(ch)
                if mapping is None:
                    continue
                usage, needs_shift = mapping
                usages = (KEY_LEFT_SHIFT, usage) if needs_shift else (usage,)
                await svc.send_keyboard(kb_id, usages)
                await asyncio.sleep(0.02)
                await svc.send_keyboard(kb_id, ())
                await asyncio.sleep(0.02)

    _run_async(_send())
    return jsonify({"status": "ok"})


@app.route("/button", methods=["POST"])
def button():
    data = json.loads(request.form.get("data", "{}"))
    name = data.get("button", "")
    if name not in _NAMED_BUTTONS:
        return jsonify({"status": "error", "message": f"unknown button: {name}"}), 400

    async def _button():
        async with IndigoHIDService(rsd) as svc:
            up, uc, hold = _NAMED_BUTTONS[name]
            await svc.send_button(up, uc, HID_BUTTON_STATE_DOWN)
            await asyncio.sleep(hold)
            await svc.send_button(up, uc, HID_BUTTON_STATE_UP)

    _run_async(_button())
    return jsonify({"status": "ok"})


@app.route("/status")
def status():
    return jsonify({
        "connected": rsd is not None,
        "device": rsd.name if rsd else None,
        "stream_url": f"http://{STREAM_BIND}:{STREAM_PORT}/",
        "recording": recording_process is not None and recording_process.poll() is None,
    })


@app.route("/recording/start", methods=["POST"])
def recording_start():
    global recording_process
    if recording_process is not None and recording_process.poll() is None:
        return jsonify({"status": "error", "message": "already recording"}), 400

    name = time.strftime("%Y-%m-%d-%H-%M-%S", time.localtime())
    path = RECORDING_DIR / f"{name}.mp4"
    stream_url = f"http://{STREAM_BIND}:{STREAM_PORT}/stream"

    recording_process = subprocess.Popen(
        ["ffmpeg", "-i", stream_url, "-c", "copy", "-y", str(path)],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    return jsonify({"status": "ok", "path": str(path)})


@app.route("/recording/stop", methods=["POST"])
def recording_stop():
    global recording_process
    if recording_process is None or recording_process.poll() is not None:
        return jsonify({"status": "error", "message": "not recording"}), 400

    recording_process.terminate()
    recording_process.wait(timeout=5)
    recording_process = None
    return jsonify({"status": "ok"})


if __name__ == "__main__":
    print("Starting iPhone Screen Mirror...")
    print("Make sure tunneld is running: sudo /path/to/venv/bin/pymobiledevice3 remote tunneld")
    print()
    _start_async_loop()
    print(f"Open http://localhost:{FLASK_PORT} in your browser")
    app.run(host="0.0.0.0", port=FLASK_PORT, debug=False, threaded=True)
