# C.A.R.E Feed State Update

## Purpose

This update prevents the robot from returning to plate selection while a feeding cycle is active. This avoids unexpected selection-view motion during feeding.

## New high-level state variables

In `main_controller_phase4.py`:

```python
system_state = "IDLE"
feed_cycle_state = "END_FEED"
feeding_active = False
```

Main notification points for the future app/Firebase connection:

- `START_FEED`: set when the FEED button starts a full feeding cycle.
- `FEEDING_STARTED`: high-level system state after FEED is pressed.
- `FEEDING_HOLD_AT_MOUTH`: set when the ToF threshold is reached and the arm is holding still for the bite.
- `FEEDING_RETURN_HOME`: set when the arm is returning to the default/home position.
- `END_FEED`: set only after the arm has returned to the default/home position.
- `EMERGENCY`: set when emergency stop is latched.

The helper functions are:

```python
set_system_state(new_state, reason=None)
start_feed_cycle(section)
end_feed_cycle(reason="FEED_COMPLETE")
mark_emergency_state(reason)
```

These functions are the best place to add Firebase/app notification writes later.

## Updated button behavior

### SELECT button

SELECT is ignored during an active feeding cycle.

The robot can use SELECT again only after:

1. the feeding cycle reaches the ToF threshold,
2. the robot holds still for the bite,
3. the robot returns to the default/home position, and
4. `end_feed_cycle()` sets `feeding_active = False`.

### FEED button

Pressing FEED again during mouth tracking is also ignored. This prevents accidental button presses from stopping the feed sequence in the middle of motion.

### Emergency button

Emergency still has priority. When emergency is pressed:

1. Jetson latches emergency state.
2. Jetson sends STOP to the Raspberry Pi.
3. The emergency recovery phase returns the robot to the default/home position.
4. After recovery, SELECT/FEED polling resumes.

## ToF threshold and bite hold

The stop threshold is now:

```python
STOP_DISTANCE_CM = 30.0
```

After ToF reaches the threshold:

1. the Jetson stops sending forward approach commands,
2. the robot holds still for:

```python
BITE_HOLD_SECONDS = 5.0
```

3. then the Jetson sends HOME to the Raspberry Pi.

## Default/home position

The default position is the same one used by emergency recovery:

```python
request_home_position(sock, "FEED_COMPLETE_RETURN_HOME")
```

On the Raspberry Pi side, `HOME` calls:

```python
move_to_startup_position()
```

which sends the myCobot to the all-zero startup joint-angle position.

## Files changed

- `main_controller_phase4.py`

`pi_arm_server.py` did not need a functional change for this update because it already supports the required `HOME` command.
