# iOS-remote

Control and mirror your iPhone screen from Linux — no jailbreak, no Xcode, no macOS required.

Uses pymobiledevice3's native iOS 17+ CoreDevice services over USB. Works entirely through the browser.

## Requirements

- Linux (tested on Linux 7.x)
- Python 3.10+
- iPhone with **Developer Mode** enabled (Settings → Privacy & Security → Developer Mode)
- USB connection
- `ffmpeg` (optional, for screen recording)

## Quick Start

```bash
# Terminal 1: start the USB tunnel (needs sudo)
sudo pymobiledevice3 tunneld start

# Terminal 2: run the app
./start.sh
```

Open `http://localhost:5000` in your browser.

## Features

- **Live screen mirroring** — HEVC stream via pymobiledevice3's ScreenStreamServer, rendered in browser with WebCodecs
- **Touch input** — tap, drag
- **Hardware buttons** — Home, Lock, Volume Up/Down, Mute, Siri
- **Screenshots** — save PNG captures
- **Text input** — type text and send to device
- **Rotation** — switch device orientation
- **Screen recording** — record to MP4 via ffmpeg

## Manual Setup

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
python3 app.py
```

## Architecture

- **Flask** (port 5000) — web UI and control endpoints
- **ScreenStreamServer** (port 8080) — pymobiledevice3's built-in HEVC stream server, embedded in the same process
- **IndigoHIDService** — hardware button presses (home, lock, volume, mute, siri)
- **UniversalHIDServiceService** — touch and keyboard input via `touch_session()`
- **ScreenCaptureService** — single-frame PNG screenshots
- **OrientationService** — device rotation

## License

BSD-3-Clause
