import math
import sys
import unittest
from unittest.mock import Mock, patch

sys.path.append("../")

from backend.modules.motioncontrols.motioncontrols import MotionDetector, Motioncontrols
from cleep.exception import InvalidParameter
from cleep.libs.tests import session


def accel_from_g(x, y, z):
    return (
        x * MotionDetector.GRAVITY,
        y * MotionDetector.GRAVITY,
        z * MotionDetector.GRAVITY,
    )


class MotioncontrolsTests(unittest.TestCase):
    def setUp(self):
        self.session = session.TestSession(self)

    def tearDown(self):
        self.session.clean()

    def init(self):
        with patch("cleep.libs.tests.session.CleepFilesystem") as filesystem_mock:
            filesystem_mock.return_value.enable_write = Mock()
            self.module = self.session.setup(Motioncontrols)
        self.module.rotation_detected_event = Mock()
        self.module.tap_detected_event = Mock()
        self.module.status_changed_event = Mock()

    def config(self, **overrides):
        config = Motioncontrols.DEFAULT_CONFIG.copy()
        config.update(overrides)
        return config

    def test_detects_right_rotation_after_hold_time(self):
        detector = MotionDetector(self.config(gravity_alpha=1.0, rotation_hold_ms=200))

        self.assertEqual(detector.process(accel_from_g(0.7, 0, 0.7), (0, 0, 0), 1.0), [])
        events = detector.process(accel_from_g(0.7, 0, 0.7), (0, 0, 0), 1.25)

        self.assertEqual(events[0]["type"], "rotation")
        self.assertEqual(events[0]["direction"], "right")
        self.assertEqual(events[0]["axis"], "x")

    def test_detects_front_rotation(self):
        detector = MotionDetector(self.config(gravity_alpha=1.0, rotation_hold_ms=0))

        detector.process(accel_from_g(0, 0.8, 0.6), (0, 0, 0), 1.0)
        events = detector.process(accel_from_g(0, 0.8, 0.6), (0, 0, 0), 1.01)

        self.assertEqual(events[0]["direction"], "front")

    def test_rotation_waits_for_release_before_retrigger(self):
        detector = MotionDetector(self.config(gravity_alpha=1.0, rotation_hold_ms=0))

        detector.process(accel_from_g(0.8, 0, 0.6), (0, 0, 0), 1.0)
        first = detector.process(accel_from_g(0.8, 0, 0.6), (0, 0, 0), 1.01)
        second = detector.process(accel_from_g(0.8, 0, 0.6), (0, 0, 0), 2.50)

        self.assertEqual(len(first), 1)
        self.assertEqual(second, [])

    def test_detects_right_tap(self):
        detector = MotionDetector(self.config(gravity_alpha=1.0, tap_threshold_g=1.0))
        detector.process(accel_from_g(0, 0, 1), (0, 0, 0), 1.0)

        events = detector.process(accel_from_g(1.4, 0.1, 1), (0, 0, 0), 1.1)

        self.assertEqual(events[0]["type"], "tap")
        self.assertEqual(events[0]["side"], "right")
        self.assertEqual(events[0]["axis"], "x")

    def test_detects_top_tap(self):
        detector = MotionDetector(self.config(gravity_alpha=1.0, tap_threshold_g=1.0))
        detector.process(accel_from_g(0, 0, 1), (0, 0, 0), 1.0)

        events = detector.process(accel_from_g(0.1, 0.1, 2.4), (0, 0, 0), 1.1)

        self.assertEqual(events[0]["side"], "top")

    def test_tap_rejects_weak_axis_dominance(self):
        detector = MotionDetector(self.config(gravity_alpha=1.0, tap_threshold_g=1.0, tap_axis_ratio=1.8))
        detector.process(accel_from_g(0, 0, 1), (0, 0, 0), 1.0)

        events = detector.process(accel_from_g(1.3, 1.0, 1), (0, 0, 0), 1.1)

        self.assertEqual(events, [])

    def test_queued_rotation_is_emitted(self):
        self.init()

        self.module._Motioncontrols__queue_motion({
            "type": "rotation",
            "direction": "right",
            "axis": "x",
            "angle": 40.0,
            "threshold": 35.0,
            "timestamp": session.AnyArg(),
        })
        self.module._on_process()

        self.module.rotation_detected_event.send.assert_called_with({
            "direction": "right",
            "axis": "x",
            "angle": 40.0,
            "threshold": 35.0,
            "timestamp": session.AnyArg(),
        })

    def test_queued_tap_is_emitted(self):
        self.init()

        self.module._Motioncontrols__queue_motion({
            "type": "tap",
            "side": "top",
            "axis": "z",
            "acceleration_g": 1.9,
            "confidence": 4.0,
            "timestamp": session.AnyArg(),
        })
        self.module._on_process()

        self.module.tap_detected_event.send.assert_called_with({
            "side": "top",
            "axis": "z",
            "acceleration_g": 1.9,
            "confidence": 4.0,
            "timestamp": session.AnyArg(),
        })

    def test_update_settings_saves_and_restarts(self):
        self.init()
        self.module._stop_reader = Mock()
        self.module._start_reader = Mock()

        config = self.module.update_settings(
            enabled=True,
            i2c_address=0x6B,
            sample_rate_hz=200,
            rotation_angle_deg=40,
        )

        self.assertTrue(config["enabled"])
        self.assertEqual(config["i2c_address"], 0x6B)
        self.assertEqual(config["sample_rate_hz"], 200)
        self.assertEqual(config["rotation_angle_deg"], 40)
        self.module._stop_reader.assert_called_once()
        self.module._start_reader.assert_called_once()

    def test_update_settings_validates_sample_rate(self):
        self.init()

        with self.assertRaises(InvalidParameter):
            self.module.update_settings(sample_rate_hz=10)

    def test_status_update_is_emitted(self):
        self.init()

        self.module._Motioncontrols__queue_status(True, None)
        self.module._on_process()

        self.assertTrue(self.module.connected)
        self.module.status_changed_event.send.assert_called_with({
            "enabled": False,
            "connected": True,
            "message": None,
            "timestamp": session.AnyArg(),
        })

    def test_clear_last_motion(self):
        self.init()
        self.module.last_motion = {"type": "tap", "side": "top"}

        self.assertEqual(self.module.clear_last_motion(), {"last_motion": None})
        self.assertIsNone(self.module.get_last_motion())


if __name__ == "__main__":
    unittest.main()
