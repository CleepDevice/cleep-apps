#!/usr/bin/env python
# -*- coding: utf-8 -*-

import math
import queue
import time
from threading import Thread

try:
    import board
    from adafruit_lsm6ds.lsm6dsox import LSM6DSOX
except ImportError:  # pragma: no cover
    board = None
    LSM6DSOX = None

from cleep.common import CATEGORIES
from cleep.core import CleepModule
from cleep.exception import InvalidParameter

__all__ = ["Motioncontrols"]


class MotionDetector:
    """
    Software gesture detector for LSM6DSOX acceleration and gyro samples.
    """

    GRAVITY = 9.80665

    def __init__(self, config):
        self.config = config
        self.gravity = None
        self.rotation_candidate = None
        self.rotation_candidate_since = 0
        self.rotation_active = None
        self.rotation_cooldown_until = 0
        self.tap_cooldown_until = 0

    def process(self, acceleration, gyro, timestamp=None):
        """
        Process one sensor sample.

        Args:
            acceleration (tuple): acceleration in m/s^2
            gyro (tuple): angular velocity in rad/s
            timestamp (float, optional): sample timestamp

        Returns:
            list: detected motion events
        """
        timestamp = time.time() if timestamp is None else timestamp
        accel_g = tuple(value / self.GRAVITY for value in acceleration)
        gyro_dps = tuple(math.degrees(value) for value in gyro)

        previous_gravity = self.gravity
        if self.gravity is None:
            self.gravity = accel_g
        else:
            alpha = self.config["gravity_alpha"]
            self.gravity = tuple(
                alpha * accel_g[index] + (1.0 - alpha) * self.gravity[index]
                for index in range(3)
            )

        events = []
        rotation = self.__detect_rotation(timestamp)
        if rotation:
            events.append(rotation)

        tap = self.__detect_tap(accel_g, gyro_dps, timestamp, previous_gravity)
        if tap:
            events.append(tap)

        return events

    def __detect_rotation(self, timestamp):
        """
        Detect held right/left/front/back tilt.
        """
        roll = math.degrees(
            math.atan2(
                self.gravity[0],
                math.sqrt(self.gravity[1] * self.gravity[1] + self.gravity[2] * self.gravity[2]),
            )
        )
        pitch = math.degrees(
            math.atan2(
                self.gravity[1],
                math.sqrt(self.gravity[0] * self.gravity[0] + self.gravity[2] * self.gravity[2]),
            )
        )

        threshold = self.config["rotation_angle_deg"]
        release = max(0, threshold - self.config["rotation_hysteresis_deg"])
        direction = None
        axis = None
        angle = 0

        if abs(roll) >= threshold or abs(pitch) >= threshold:
            if abs(roll) >= abs(pitch):
                direction = "right" if roll > 0 else "left"
                axis = "x"
                angle = roll
            else:
                direction = "front" if pitch > 0 else "back"
                axis = "y"
                angle = pitch

        if self.rotation_active:
            if abs(roll) < release and abs(pitch) < release:
                self.rotation_active = None
            return None

        if not direction:
            self.rotation_candidate = None
            self.rotation_candidate_since = 0
            return None

        if timestamp < self.rotation_cooldown_until:
            return None

        if self.rotation_candidate != direction:
            self.rotation_candidate = direction
            self.rotation_candidate_since = timestamp
            return None

        hold_seconds = self.config["rotation_hold_ms"] / 1000.0
        if timestamp - self.rotation_candidate_since < hold_seconds:
            return None

        self.rotation_active = direction
        self.rotation_cooldown_until = timestamp + self.config["rotation_cooldown_ms"] / 1000.0
        self.rotation_candidate = None
        self.rotation_candidate_since = 0

        return {
            "type": "rotation",
            "direction": direction,
            "axis": axis,
            "angle": round(angle, 2),
            "threshold": threshold,
            "timestamp": int(timestamp),
        }

    def __detect_tap(self, accel_g, gyro_dps, timestamp, previous_gravity):
        """
        Detect right, left, and top taps from short acceleration impulses.
        """
        if timestamp < self.tap_cooldown_until:
            return None

        baseline = previous_gravity if previous_gravity is not None else self.gravity
        roll = math.degrees(
            math.atan2(
                baseline[0],
                math.sqrt(baseline[1] * baseline[1] + baseline[2] * baseline[2]),
            )
        )
        pitch = math.degrees(
            math.atan2(
                baseline[1],
                math.sqrt(baseline[0] * baseline[0] + baseline[2] * baseline[2]),
            )
        )
        if max(abs(roll), abs(pitch)) > self.config["tap_max_tilt_deg"]:
            return None

        gyro_magnitude = math.sqrt(sum(value * value for value in gyro_dps))
        if gyro_magnitude > self.config["tap_max_gyro_dps"]:
            return None

        linear = tuple(accel_g[index] - baseline[index] for index in range(3))
        magnitudes = [abs(value) for value in linear]
        max_index = magnitudes.index(max(magnitudes))
        acceleration_g = magnitudes[max_index]
        if acceleration_g < self.config["tap_threshold_g"]:
            return None

        sorted_magnitudes = sorted(magnitudes, reverse=True)
        second = sorted_magnitudes[1] if len(sorted_magnitudes) > 1 else 0
        confidence = acceleration_g / max(second, 0.01)
        if confidence < self.config["tap_axis_ratio"]:
            return None

        side = None
        axis = ("x", "y", "z")[max_index]
        if axis == "x":
            positive_side = self.config["positive_x_tap_side"]
            negative_side = "left" if positive_side == "right" else "right"
            side = positive_side if linear[0] >= 0 else negative_side
        elif axis == "z":
            side = "top"

        if side not in ("right", "left", "top"):
            return None

        self.tap_cooldown_until = timestamp + self.config["tap_cooldown_ms"] / 1000.0

        return {
            "type": "tap",
            "side": side,
            "axis": axis,
            "acceleration_g": round(acceleration_g, 3),
            "confidence": round(confidence, 2),
            "timestamp": int(timestamp),
        }


class MotionReaderThread(Thread):
    """
    Background LSM6DSOX reader.
    """

    def __init__(self, config, on_motion, on_status, logger):
        Thread.__init__(self)
        self.daemon = True
        self.continu = True
        self.config = config
        self.on_motion = on_motion
        self.on_status = on_status
        self.logger = logger
        self.detector = MotionDetector(config)

    def stop(self):
        """
        Stop thread loop.
        """
        self.continu = False

    def run(self):
        """
        Read sensor samples until stopped.
        """
        if board is None or LSM6DSOX is None:
            self.on_status(False, "Adafruit LSM6DSOX dependencies are not installed")
            return

        try:
            i2c = board.I2C()
            sensor = LSM6DSOX(i2c, address=self.config["i2c_address"])
            self.on_status(True, None)

            delay = 1.0 / self.config["sample_rate_hz"]
            while self.continu:
                events = self.detector.process(sensor.acceleration, sensor.gyro)
                for event in events:
                    self.on_motion(event)
                time.sleep(delay)

        except Exception as error:
            self.logger.exception("Motion controls sensor error:")
            self.on_status(False, str(error))


class Motioncontrols(CleepModule):
    """
    LSM6DSOX motion controls module.
    """

    MODULE_AUTHOR = "Cleep"
    MODULE_VERSION = "1.0.0"
    MODULE_DEPS = []
    MODULE_DESCRIPTION = "Detect tilt and tap gestures"
    MODULE_LONGDESCRIPTION = (
        "Detects right, left, front, and back rotations plus right, left, "
        "and top taps using an LSM6DSOX accelerometer/gyroscope breakout over I2C."
    )
    MODULE_TAGS = ["motion", "imu", "gyroscope", "accelerometer", "lsm6dsox", "gestures"]
    MODULE_CATEGORY = CATEGORIES.DRIVER
    MODULE_COUNTRY = None
    MODULE_URLINFO = "https://github.com/CleepDevice/cleep-apps"
    MODULE_URLHELP = None
    MODULE_URLSITE = "https://www.st.com/en/mems-and-sensors/lsm6dsox.html"
    MODULE_URLBUGS = "https://github.com/CleepDevice/cleep-apps/issues"

    MODULE_CONFIG_FILE = "motioncontrols.conf"
    DEFAULT_CONFIG = {
        "enabled": False,
        "i2c_address": 0x6A,
        "sample_rate_hz": 100,
        "rotation_angle_deg": 35.0,
        "rotation_hysteresis_deg": 8.0,
        "rotation_hold_ms": 250,
        "rotation_cooldown_ms": 1000,
        "tap_threshold_g": 1.6,
        "tap_axis_ratio": 1.6,
        "tap_cooldown_ms": 350,
        "tap_max_tilt_deg": 20.0,
        "tap_max_gyro_dps": 450.0,
        "gravity_alpha": 0.12,
        "positive_x_tap_side": "right",
    }

    RESTART_FIELDS = [
        "enabled",
        "i2c_address",
        "sample_rate_hz",
    ]

    DETECTOR_FIELDS = [
        "rotation_angle_deg",
        "rotation_hysteresis_deg",
        "rotation_hold_ms",
        "rotation_cooldown_ms",
        "tap_threshold_g",
        "tap_axis_ratio",
        "tap_cooldown_ms",
        "tap_max_tilt_deg",
        "tap_max_gyro_dps",
        "gravity_alpha",
        "positive_x_tap_side",
    ]

    def __init__(self, bootstrap, debug_enabled):
        CleepModule.__init__(self, bootstrap, debug_enabled)

        self.reader = None
        self.connected = False
        self.last_error = None
        self.last_motion = None
        self.motion_events = queue.Queue()
        self.statuses = queue.Queue()
        self.rotation_detected_event = self._get_event("motioncontrols.rotation.detected")
        self.tap_detected_event = self._get_event("motioncontrols.tap.detected")
        self.status_changed_event = self._get_event("motioncontrols.status.changed")

    def _configure(self):
        """
        Reset runtime state.
        """
        self.connected = False
        self.last_error = None
        self.last_motion = None

    def _on_start(self):
        """
        Start sensor reader when enabled.
        """
        self._start_reader()

    def _on_stop(self):
        """
        Stop sensor reader.
        """
        self._stop_reader()

    def _on_process(self):
        """
        Emit queued motion and status events.
        """
        while not self.statuses.empty():
            status = self.statuses.get()
            self.connected = status["connected"]
            self.last_error = status["message"]
            self.status_changed_event.send(status)

        while not self.motion_events.empty():
            event = self.motion_events.get()
            self.last_motion = event
            if event["type"] == "rotation":
                self.rotation_detected_event.send({
                    "direction": event["direction"],
                    "axis": event["axis"],
                    "angle": event["angle"],
                    "threshold": event["threshold"],
                    "timestamp": event["timestamp"],
                })
            elif event["type"] == "tap":
                self.tap_detected_event.send({
                    "side": event["side"],
                    "axis": event["axis"],
                    "acceleration_g": event["acceleration_g"],
                    "confidence": event["confidence"],
                    "timestamp": event["timestamp"],
                })

    def get_module_config(self):
        """
        Return module configuration with runtime status.

        Returns:
            dict: module configuration
        """
        config = self._get_config()
        config["connected"] = self.connected
        config["last_error"] = self.last_error
        config["last_motion"] = self.last_motion
        config["reader_running"] = self.reader is not None and self.reader.is_alive()
        return config

    def get_status(self):
        """
        Return sensor status.

        Returns:
            dict: status
        """
        config = self._get_config()
        return {
            "enabled": config["enabled"],
            "connected": self.connected,
            "reader_running": self.reader is not None and self.reader.is_alive(),
            "last_error": self.last_error,
            "last_motion": self.last_motion,
        }

    def get_last_motion(self):
        """
        Return last detected motion.

        Returns:
            dict|None: last motion
        """
        return self.last_motion

    def clear_last_motion(self):
        """
        Clear last detected motion.

        Returns:
            dict: cleared state
        """
        self.last_motion = None
        return {"last_motion": None}

    def update_settings(
        self,
        enabled=None,
        i2c_address=None,
        sample_rate_hz=None,
        rotation_angle_deg=None,
        rotation_hysteresis_deg=None,
        rotation_hold_ms=None,
        rotation_cooldown_ms=None,
        tap_threshold_g=None,
        tap_axis_ratio=None,
        tap_cooldown_ms=None,
        tap_max_tilt_deg=None,
        tap_max_gyro_dps=None,
        gravity_alpha=None,
        positive_x_tap_side=None,
    ):
        """
        Update motion control settings.

        Returns:
            dict: updated module configuration
        """
        updates = {}
        self.__add_update(updates, "enabled", enabled, bool)
        self.__add_update(updates, "i2c_address", i2c_address, int)
        self.__add_update(updates, "sample_rate_hz", sample_rate_hz, int)
        self.__add_update(updates, "rotation_angle_deg", rotation_angle_deg, (int, float))
        self.__add_update(updates, "rotation_hysteresis_deg", rotation_hysteresis_deg, (int, float))
        self.__add_update(updates, "rotation_hold_ms", rotation_hold_ms, int)
        self.__add_update(updates, "rotation_cooldown_ms", rotation_cooldown_ms, int)
        self.__add_update(updates, "tap_threshold_g", tap_threshold_g, (int, float))
        self.__add_update(updates, "tap_axis_ratio", tap_axis_ratio, (int, float))
        self.__add_update(updates, "tap_cooldown_ms", tap_cooldown_ms, int)
        self.__add_update(updates, "tap_max_tilt_deg", tap_max_tilt_deg, (int, float))
        self.__add_update(updates, "tap_max_gyro_dps", tap_max_gyro_dps, (int, float))
        self.__add_update(updates, "gravity_alpha", gravity_alpha, (int, float))
        self.__add_update(updates, "positive_x_tap_side", positive_x_tap_side, str)

        self.__validate_updates(updates)

        restart = any(field in updates for field in self.RESTART_FIELDS)
        self._update_config(updates)

        if restart:
            self._stop_reader()
            self._start_reader()

        return self.get_module_config()

    def _start_reader(self):
        """
        Start reader thread when enabled.

        Returns:
            bool: True when started
        """
        config = self._get_config()
        if not config["enabled"]:
            self.connected = False
            self.last_error = None
            return False
        if self.reader and self.reader.is_alive():
            return True

        self.reader = MotionReaderThread(
            config,
            self.__queue_motion,
            self.__queue_status,
            self.logger,
        )
        self.reader.start()
        return True

    def _stop_reader(self):
        """
        Stop reader thread.
        """
        if not self.reader:
            self.connected = False
            return

        self.reader.stop()
        self.reader.join(2.0)
        self.reader = None
        self.connected = False

    def __queue_motion(self, event):
        """
        Queue motion event from reader thread.
        """
        self.motion_events.put(event)

    def __queue_status(self, connected, message):
        """
        Queue status event from reader thread.
        """
        config = self._get_config()
        self.statuses.put({
            "enabled": config["enabled"],
            "connected": connected,
            "message": message,
            "timestamp": int(time.time()),
        })

    def __validate_updates(self, updates):
        """
        Validate setting updates.
        """
        if "i2c_address" in updates and (updates["i2c_address"] < 0x03 or updates["i2c_address"] > 0x77):
            raise InvalidParameter('Parameter "i2c_address" must be a valid 7-bit I2C address')
        if "sample_rate_hz" in updates and (updates["sample_rate_hz"] < 25 or updates["sample_rate_hz"] > 400):
            raise InvalidParameter('Parameter "sample_rate_hz" must be between 25 and 400')
        if "rotation_angle_deg" in updates and (updates["rotation_angle_deg"] < 5 or updates["rotation_angle_deg"] > 85):
            raise InvalidParameter('Parameter "rotation_angle_deg" must be between 5 and 85')
        if "rotation_hysteresis_deg" in updates and updates["rotation_hysteresis_deg"] < 0:
            raise InvalidParameter('Parameter "rotation_hysteresis_deg" must be zero or positive')
        if "rotation_hold_ms" in updates and updates["rotation_hold_ms"] < 0:
            raise InvalidParameter('Parameter "rotation_hold_ms" must be zero or positive')
        if "rotation_cooldown_ms" in updates and updates["rotation_cooldown_ms"] < 0:
            raise InvalidParameter('Parameter "rotation_cooldown_ms" must be zero or positive')
        if "tap_threshold_g" in updates and updates["tap_threshold_g"] <= 0:
            raise InvalidParameter('Parameter "tap_threshold_g" must be positive')
        if "tap_axis_ratio" in updates and updates["tap_axis_ratio"] < 1:
            raise InvalidParameter('Parameter "tap_axis_ratio" must be at least 1')
        if "tap_cooldown_ms" in updates and updates["tap_cooldown_ms"] < 0:
            raise InvalidParameter('Parameter "tap_cooldown_ms" must be zero or positive')
        if "tap_max_tilt_deg" in updates and updates["tap_max_tilt_deg"] < 0:
            raise InvalidParameter('Parameter "tap_max_tilt_deg" must be zero or positive')
        if "tap_max_gyro_dps" in updates and updates["tap_max_gyro_dps"] <= 0:
            raise InvalidParameter('Parameter "tap_max_gyro_dps" must be positive')
        if "gravity_alpha" in updates and (updates["gravity_alpha"] <= 0 or updates["gravity_alpha"] > 1):
            raise InvalidParameter('Parameter "gravity_alpha" must be between 0 and 1')
        if "positive_x_tap_side" in updates and updates["positive_x_tap_side"] not in ("right", "left"):
            raise InvalidParameter('Parameter "positive_x_tap_side" must be "right" or "left"')

    def __add_update(self, updates, field, value, expected_type):
        """
        Add typed optional update.
        """
        if value is None:
            return
        if not isinstance(value, expected_type):
            if isinstance(expected_type, tuple):
                expected = ", ".join(item.__name__ for item in expected_type)
            else:
                expected = expected_type.__name__
            raise InvalidParameter(
                'Parameter "%s" must be of type "%s"' % (field, expected)
            )
        updates[field] = value
