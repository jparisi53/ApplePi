# WiFiApple

A Flask web server that uses the MLB Stats API to detect home runs and wins for the team you choose to monitor, and triggers a linear actuator upon detection.

> **Forked from [jbooba/WiFiApple](https://github.com/jbooba/WiFiApple)**

## Platform Support

This project now supports both **Arduino** and **Raspberry Pi** platforms:

- **Arduino Version** (Original): Uses Arduino Nano ESP32 with separate server
- **Raspberry Pi Version** (New): All-in-one Python script running directly on Pi

## Disclaimer

This was 99% "vibe coded" by chatGPT. A ton of research, time and tweaking went into it, but I'd be lying if I said I "coded this myself." I did not. As such, it's probably a pretty awful implementation, but hey, it works!

## Description

This monitors the team you set (defaults to the Mets) and triggers a linear actuator when it detects a home run or Win. Originally designed to raise and lower a Home Run Apple on a desk.

- It notes the start time of the server so as to not accidentally trigger for any hits that may have occurred prior to the start of monitoring.

- Determines home and away teams via teamID and HalfInning so as to only detect hits from the team you are monitoring.

- Has checks for doubleheaders, postponed games, delayed games, etc. It should reliably (and almost immediately) find the correct gameID for the current or upcoming game.

- When the game status changes from "In-Progress" to "Game Over," the script will find the final score and determine if the monitored team won. If it did, a trigger will be sent.

- A dedicated trigger queue and background thread handle actuator activation, so MLB polling is never blocked by the actuator cycle.

_________________________________________________________________________________________

## Quick Start

### For Raspberry Pi (Recommended)

1. **Install [uv](https://docs.astral.sh/uv/)** (if you haven't already):
   ```bash
   curl -LsSf https://astral.sh/uv/install.sh | sh
   ```

2. **Install dependencies:**
   ```bash
   uv add flask pymlb-statsapi rpi-gpio
   ```

3. **Wire your linear actuator** following `RASPBERRY_PI_WIRING.md`
   - IN1 → GPIO 17 (Physical pin 11)
   - IN2 → GPIO 27 (Physical pin 13)

4. **Run the script:**
   ```bash
   sudo uv run RaspberryPiApple.py
   ```
   > `sudo` is required for GPIO access.

5. **Access web interface:** `http://[your-pi-ip]:5000`

See `RASPBERRY_PI_SETUP.md` for detailed instructions including auto-start on boot.

### For Arduino (Original)

1. **Install [uv](https://docs.astral.sh/uv/)** (if you haven't already):
   ```bash
   curl -LsSf https://astral.sh/uv/install.sh | sh
   ```

2. **Install dependencies:**
   ```bash
   uv add flask pymlb-statsapi
   ```

3. **Run the server:**
   ```bash
   uv run AppleServer.py
   ```

4. **Upload Arduino sketch:**
   - Open `AppleSketch.ino` in Arduino IDE
   - Configure WiFi credentials and server IP
   - Upload to Arduino Nano ESP32

5. **Access web interface:** `http://localhost:5000`

## Files

- `RaspberryPiApple.py` - All-in-one script for Raspberry Pi
- `AppleServer.py` - Flask server for Arduino version
- `AppleSketch.ino` - Arduino sketch for ESP32
- `RASPBERRY_PI_SETUP.md` - Detailed Raspberry Pi setup guide
- `RASPBERRY_PI_WIRING.md` - Hardware wiring instructions

## Configuration

Use the web interface to select your team, or edit the default team ID in the script:

```python
monitored_team_id = 121  # New York Mets
```

The web interface also exposes:
- A **manual trigger** button to test the actuator
- A `/status` JSON endpoint for monitoring state (current game, pending triggers, last activation time, GPIO pins)

You can monitor the script's activity via the command line or web interface.