#!/usr/bin/env python3
"""
Raspberry Pi Home Run Apple Controller
Monitors MLB games and triggers linear actuator for home runs and wins
"""

from flask import Flask, request, render_template_string, redirect
import threading
import time
import re
from zoneinfo import ZoneInfo
from datetime import datetime, timedelta, timezone
from collections import deque
from pymlb_statsapi import api
import RPi.GPIO as GPIO

app = Flask(__name__)

# =====================
# ---- GPIO Setup ----
# =====================
# Using GPIO pins 17 and 27 (physical pins 11 and 13)
# Avoiding pins 1 (3.3V) and 6 (GND) as requested
IN1_PIN = 17  # GPIO 17 (Physical pin 11) - L298N IN1
IN2_PIN = 27  # GPIO 27 (Physical pin 13) - L298N IN2

GPIO.setmode(GPIO.BCM)  # Use BCM GPIO numbering
GPIO.setwarnings(False)
GPIO.setup(IN1_PIN, GPIO.OUT)
GPIO.setup(IN2_PIN, GPIO.OUT)

# Initialize pins to LOW (motor stopped)
GPIO.output(IN1_PIN, GPIO.LOW)
GPIO.output(IN2_PIN, GPIO.LOW)

print(f"[GPIO] Initialized - IN1: GPIO{IN1_PIN}, IN2: GPIO{IN2_PIN}")

# =====================
# ---- Server State ----
# =====================
monitored_team_id = 121  # Default team (New York Mets)
current_game_id = None
seen_plays = set()
last_seen_status = ""
server_start_time = datetime.now(timezone.utc)
triggered_wins = set()

# Trigger queue + stats
_trigger_q = deque()                 # FIFO of pending triggers
_state_lock = threading.Lock()       # Guards queue + simple state
last_enqueued_at = None              # When we last queued a trigger
last_triggered_at = None             # When actuator was last activated

# =====================
# ---- MLB Teams UI ----
# =====================
MLB_TEAMS = {
    "Arizona Diamondbacks": 109,
    "Atlanta Braves": 144,
    "Baltimore Orioles": 110,
    "Boston Red Sox": 111,
    "Chicago Cubs": 112,
    "Chicago White Sox": 145,
    "Cincinnati Reds": 113,
    "Cleveland Guardians": 114,
    "Colorado Rockies": 115,
    "Detroit Tigers": 116,
    "Houston Astros": 117,
    "Kansas City Royals": 118,
    "Los Angeles Angels": 108,
    "Los Angeles Dodgers": 119,
    "Miami Marlins": 146,
    "Milwaukee Brewers": 158,
    "Minnesota Twins": 142,
    "New York Mets": 121,
    "New York Yankees": 147,
    "Oakland Athletics": 133,
    "Philadelphia Phillies": 143,
    "Pittsburgh Pirates": 134,
    "San Diego Padres": 135,
    "San Francisco Giants": 137,
    "Seattle Mariners": 136,
    "St. Louis Cardinals": 138,
    "Tampa Bay Rays": 139,
    "Texas Rangers": 140,
    "Toronto Blue Jays": 141,
    "Washington Nationals": 120
}

# =====================
# ---- Actuator Control ----
# =====================

def activate_actuator(duration_seconds=10):
    """
    Activate the linear actuator:
    1. Extend for duration_seconds
    2. Retract for duration_seconds
    3. Stop
    """
    global last_triggered_at
    
    try:
        print(f"[ACTUATOR] 🎯 Raising actuator for {duration_seconds} seconds...")
        
        # Extend
        GPIO.output(IN1_PIN, GPIO.HIGH)
        GPIO.output(IN2_PIN, GPIO.LOW)
        time.sleep(duration_seconds)
        
        # Retract
        print(f"[ACTUATOR] 🔽 Retracting actuator for {duration_seconds} seconds...")
        GPIO.output(IN1_PIN, GPIO.LOW)
        GPIO.output(IN2_PIN, GPIO.HIGH)
        time.sleep(duration_seconds)
        
        # Stop
        GPIO.output(IN1_PIN, GPIO.LOW)
        GPIO.output(IN2_PIN, GPIO.LOW)
        
        last_triggered_at = datetime.utcnow()
        print("[ACTUATOR] ✅ Actuator cycle complete")
        
    except Exception as e:
        print(f"[ERROR] Actuator control failed: {e}")
        # Ensure motor is stopped on error
        GPIO.output(IN1_PIN, GPIO.LOW)
        GPIO.output(IN2_PIN, GPIO.LOW)


# =====================
# ---- Helpers ----
# =====================

def get_latest_game_id(team_id):
    today = datetime.now(ZoneInfo("America/New_York")).strftime("%Y-%m-%d")
    yesterday = (datetime.now(ZoneInfo("America/New_York")) - timedelta(days=1)).strftime("%Y-%m-%d")
    schedule = api.schedule(start_date=yesterday, end_date=today, team=team_id)

    in_progress_game = None
    doubleheader_game2 = None
    game_over_game = None
    postponed_game = None
    final_game = None

    for game in schedule:
        game_id = game.get("game_id")
        status = game.get("status")
        try:
            game_data = api.get("game", {"gamePk": game_id})
            doubleheader = game_data['gameData']['game'].get('doubleHeader', 'N')
            gid = game_data['gameData']['game'].get('id', '')
        except Exception as e:
            print(f"[WARN] Could not retrieve game details: {e}")
            continue

        print(f"[DEBUG] Found game ID {game_id} with status '{status}' (DoubleHeader: {doubleheader})")

        if status == "In Progress" or status.startswith("Manager challenge") or status.startswith("Umpire review"):
            in_progress_game = (game_id, status)
        elif doubleheader == 'S' and gid.endswith('-2'):
            print("[INFO] Found doubleheader Game 2")
            doubleheader_game2 = (game_id, status)
        elif status == "Game Over":
            game_over_game = (game_id, status)
        elif status == "Postponed":
            postponed_game = (game_id, status)
        elif status == "Final":
            final_game = (game_id, status)

    return (
        in_progress_game or
        doubleheader_game2 or
        game_over_game or
        postponed_game or
        final_game or
        (None, None)
    )


def fetch_play_data(game_id):
    return api.get("game_playByPlay", {"gamePk": game_id})


def get_team_info(game_id):
    data = api.get("game", {"gamePk": game_id})
    home_id = data['gameData']['teams']['home']['id']
    away_id = data['gameData']['teams']['away']['id']
    return home_id, away_id


def should_skip_event(play):
    """Return True if play is a non-at-bat filler event that should not be marked as seen."""
    event = play.get("result", {}).get("event", "").lower()
    filler_events = {
        "batter timeout", "mound visit", "injury delay", "manager visit",
        "challenge", "review", "umpire review", "pitching substitution",
        "warmup", "defensive switch", "offensive substitution", "throwing error",
        "passed ball", "wild pitch", "steals"
    }
    return event in filler_events


def queue_trigger(reason: str):
    global last_enqueued_at
    with _state_lock:
        _trigger_q.append({
            "reason": reason,
            "enqueued_at": datetime.utcnow().isoformat()
        })
        last_enqueued_at = datetime.utcnow()
        print(f"[QUEUE] Trigger queued ({reason}). Pending count = {len(_trigger_q)}")


# =====================
# ---- Background Loops ----
# =====================

def actuator_trigger_loop():
    """
    Separate thread that processes the trigger queue and activates the actuator.
    This ensures actuator activation doesn't block the MLB monitoring loop.
    """
    while True:
        with _state_lock:
            if _trigger_q:
                trigger = _trigger_q.popleft()
                reason = trigger.get("reason", "UNKNOWN")
                print(f"[TRIGGER] Processing trigger: {reason}")
        
        if trigger:
            activate_actuator(duration_seconds=10)
            trigger = None  # Reset for next iteration
        
        time.sleep(1)  # Check queue every second


def background_loop():
    global current_game_id, seen_plays, last_seen_status, triggered_wins

    while True:
        game_id, status = get_latest_game_id(monitored_team_id)

        if not game_id:
            print("[INFO] No active or final games found.")
            time.sleep(15)
            continue

        if current_game_id != game_id:
            print(f"[INFO] Switched to new game ID: {game_id}")
            current_game_id = game_id
            seen_plays.clear()

        if status != last_seen_status:
            print(f"[DEBUG] Game status changed: {status}")
            last_seen_status = status

        # Victory trigger once per game
        if status in ["Final", "Game Over"] and game_id not in triggered_wins:
            try:
                data = api.get("game", {"gamePk": game_id})
                home_team_id = data['gameData']['teams']['home']['id']
                away_team_id = data['gameData']['teams']['away']['id']
                linescore = data.get("liveData", {}).get("linescore", {})
                home_score = linescore.get("teams", {}).get("home", {}).get("runs", 0)
                away_score = linescore.get("teams", {}).get("away", {}).get("runs", 0)

                print(f"[FINAL] Final score — Home: {home_score}, Away: {away_score}")

                if ((home_team_id == monitored_team_id and home_score > away_score) or
                    (away_team_id == monitored_team_id and away_score > home_score)):
                    print("[VICTORY] Monitored team won — queueing win trigger")
                    queue_trigger("TEAM_WIN")
                    triggered_wins.add(game_id)
            except Exception as e:
                print(f"[ERROR] Failed to check final score: {e}")

        try:
            data = fetch_play_data(game_id)
            all_plays = data.get("allPlays", [])
            print(f"[DEBUG] Retrieved {len(all_plays)} plays.")

            # Look at the last couple of fully-formed plays for freshness
            for play in all_plays[-3:]:
                idx = play["about"]["atBatIndex"]
                desc = play.get("result", {}).get("description", "")
                events = play.get("playEvents", [])
                start_str = events[0].get("startTime") if events else None

                print(f"[PLAY {idx}] ===============================")
                print(f"Description: {desc}")
                print(f"Start Time (raw): {start_str}")

                if not desc or not start_str:
                    print("[WAIT] Description not yet available, will check again later.")
                    continue  # Don't mark as seen

                start_dt = datetime.fromisoformat(start_str.replace("Z", "+00:00"))
                if start_dt < server_start_time - timedelta(minutes=1):
                    print(f"[SKIP] Play happened before server started at {server_start_time}")
                    continue

                if idx in seen_plays:
                    print(f"[SKIP] Already processed play {idx}.")
                    continue

                half_inning = play["about"].get("halfInning")
                is_home_batting = (half_inning == "bottom")
                home_id, away_id = get_team_info(game_id)
                batting_team_id = home_id if is_home_batting else away_id

                desc_lower = desc.lower()
                is_dinger = False

                if "double play" in desc_lower or "triple play" in desc_lower:
                    print("[SKIP] Double/triple play — not a hit.")

                if "steals" in desc_lower:
                    print("[SKIP] Stolen base. At-Bat is ongoing")
                elif re.search(r'\b(homers?)\b', desc_lower) or re.search(r'\b(grand slam?)\b', desc_lower):
                    is_dinger = True

                if batting_team_id == monitored_team_id and is_dinger:
                    print("[HIT] Dinger detected — queueing trigger")
                    queue_trigger("DINGER")
                else:
                    print("[SKIP] Not a monitored-team dinger.")

                if not should_skip_event(play):
                    seen_plays.add(idx)
                else:
                    print("[SKIP] Filler event — not marking as seen.")

        except Exception as e:
            print(f"[ERROR] Fetching or processing play data failed: {e}")

        time.sleep(15)


# =====================
# ---- HTTP Routes ----
# =====================

@app.route("/")
def index():
    team_options = "".join(
        f'<option value="{id}" {"selected" if id == monitored_team_id else ""}>{name}</option>'
        for name, id in MLB_TEAMS.items()
    )
    pending = len(_trigger_q)
    html = f"""
    <html><body>
    <h1>🍎 Raspberry Pi Apple Server</h1>
    <form method="POST" action="/set_team">
        <label>Select Team:</label>
        <select name="team_id">{team_options}</select>
        <button type="submit">Set Team</button>
    </form>
    <hr/>
    <p><b>Pending triggers:</b> {pending}</p>
    <p><b>Last enqueued:</b> {last_enqueued_at}</p>
    <p><b>Last actuator activation:</b> {last_triggered_at}</p>
    <p><b>GPIO Pins:</b> IN1=GPIO{IN1_PIN}, IN2=GPIO{IN2_PIN}</p>

    <form method="POST" action="/manual_trigger" style="margin-top:10px;">
        <button type="submit">Trigger Apple Now 🍎</button>
    </form>
    </body></html>
    """
    return render_template_string(html)


@app.route("/set_team", methods=["POST"])
def set_team():
    global monitored_team_id
    try:
        monitored_team_id = int(request.form["team_id"])
        print(f"[INFO] Updated monitored team to: {monitored_team_id}")
    except Exception:
        return "Invalid team ID", 400
    return redirect("/", code=303)


@app.route("/manual_trigger", methods=["POST"])
def manual_trigger():
    queue_trigger("MANUAL_BUTTON")
    return redirect("/", code=303)


@app.route("/status")
def status():
    with _state_lock:
        return {
            "monitored_team_id": monitored_team_id,
            "current_game_id": current_game_id,
            "pending_triggers": len(_trigger_q),
            "last_enqueued_at": last_enqueued_at.isoformat() if last_enqueued_at else None,
            "last_triggered_at": last_triggered_at.isoformat() if last_triggered_at else None,
            "gpio_pins": {"IN1": IN1_PIN, "IN2": IN2_PIN}
        }, 200


def cleanup():
    """Cleanup GPIO on exit"""
    print("[GPIO] Cleaning up...")
    GPIO.output(IN1_PIN, GPIO.LOW)
    GPIO.output(IN2_PIN, GPIO.LOW)
    GPIO.cleanup()


if __name__ == "__main__":
    try:
        # Start background threads
        threading.Thread(target=background_loop, daemon=True).start()
        threading.Thread(target=actuator_trigger_loop, daemon=True).start()
        
        print("[INFO] Starting Flask server on http://0.0.0.0:5000")
        print(f"[INFO] Monitoring team ID: {monitored_team_id}")
        
        app.run(host="0.0.0.0", port=5000)
    except KeyboardInterrupt:
        print("\n[INFO] Shutting down...")
    finally:
        cleanup()