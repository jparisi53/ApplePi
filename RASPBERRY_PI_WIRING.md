# Raspberry Pi Wiring Guide for Linear Actuator

## Components Needed
1. Raspberry Pi (any model with GPIO pins)
2. L298N Motor Driver Module (or similar H-bridge controller)
3. Linear Actuator
4. 12V Power Supply (for actuator - check your actuator's voltage requirements)
5. Jumper wires

## Pin Connections

### Raspberry Pi GPIO to L298N Motor Driver

| Raspberry Pi | L298N Module | Description |
|--------------|--------------|-------------|
| GPIO 17 (Physical Pin 11) | IN1 | Control signal 1 |
| GPIO 27 (Physical Pin 13) | IN2 | Control signal 2 |
| GND (Physical Pin 9, 14, 20, 25, 30, 34, or 39) | GND | Common ground |

**Note:** Pins 1 (3.3V) and 6 (GND) are avoided as requested (in use for fan)

### L298N Motor Driver to Linear Actuator

| L298N Module | Linear Actuator | Description |
|--------------|-----------------|-------------|
| OUT1 | Actuator Wire 1 | Motor output 1 |
| OUT2 | Actuator Wire 2 | Motor output 2 |

### L298N Power Connections

| L298N Module | Power Source | Description |
|--------------|--------------|-------------|
| +12V | 12V Power Supply + | Positive voltage (match your actuator voltage) |
| GND | 12V Power Supply - | Ground |
| +5V | Leave disconnected | (Pi provides logic power via GPIO) |

## Wiring Diagram (Text)

```
Raspberry Pi                    L298N Motor Driver              Linear Actuator
┌─────────────┐                ┌──────────────┐                ┌──────────┐
│             │                │              │                │          │
│  GPIO 17 ───┼───────────────►│ IN1          │                │          │
│  (Pin 11)   │                │              │                │          │
│             │                │         OUT1 ├───────────────►│ Wire 1   │
│  GPIO 27 ───┼───────────────►│ IN2          │                │          │
│  (Pin 13)   │                │              │                │          │
│             │                │         OUT2 ├───────────────►│ Wire 2   │
│  GND     ───┼───────────────►│ GND          │                │          │
│  (Pin 9)    │                │              │                └──────────┘
│             │                │  +12V        │
└─────────────┘                │  GND         │
                               └──────┬───────┘
                                      │
                               12V Power Supply
                               ┌──────┴───────┐
                               │   +12V  GND  │
                               └──────────────┘
```

## Important Notes

### Power Supply
- **DO NOT** power the linear actuator from the Raspberry Pi's 5V or 3.3V pins
- Use a separate 12V power supply (or voltage matching your actuator specs)
- The L298N module acts as an intermediary, protecting the Pi from high current draw
- Connect the Pi's GND to the L298N's GND for a common ground reference

### L298N Jumper Settings
- Remove the 5V jumper on the L298N if present (we're using Pi's 3.3V logic)
- Some L298N modules have an enable jumper (ENA/ENB) - keep these connected

### GPIO Pin Selection
- Using GPIO 17 and 27 (BCM numbering)
- Physical pins 11 and 13 on the 40-pin header
- Avoiding pins 1 and 6 as requested

### Safety
- Always connect GND first when wiring
- Double-check polarity before powering on
- The actuator direction (extend/retract) depends on wire polarity - if it moves the wrong way, swap the two actuator wires on OUT1/OUT2

## Testing the Connection

1. Run the script: `sudo python3 RaspberryPiApple.py`
2. Open web browser to `http://[your-pi-ip]:5000`
3. Click "Trigger Apple Now 🍎" button
4. Actuator should extend for 10 seconds, then retract for 10 seconds

If the actuator moves in the wrong direction (retracts first instead of extending), swap the two wires connected to OUT1 and OUT2 on the L298N module.

## Raspberry Pi GPIO Pinout Reference

```
     3.3V  (1) (2)  5V
    GPIO2  (3) (4)  5V
    GPIO3  (5) (6)  GND      ← Pin 6 (in use for fan)
    GPIO4  (7) (8)  GPIO14
      GND  (9) (10) GPIO15
   GPIO17 (11) (12) GPIO18   ← Pin 11 (IN1 - used by script)
   GPIO27 (13) (14) GND      ← Pin 13 (IN2 - used by script)
   GPIO22 (15) (16) GPIO23
     3.3V (17) (18) GPIO24
   GPIO10 (19) (20) GND
    GPIO9 (21) (22) GPIO25
   GPIO11 (23) (24) GPIO8
      GND (25) (26) GPIO7
    GPIO0 (27) (28) GPIO1
    GPIO5 (29) (30) GND
    GPIO6 (31) (32) GPIO12
   GPIO13 (33) (34) GND
   GPIO19 (35) (36) GPIO16
   GPIO26 (37) (38) GPIO20
      GND (39) (40) GPIO21