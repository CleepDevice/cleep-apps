import os
import sys
import unittest
from unittest.mock import Mock, patch

sys.path.append("../")

from backend.modules.mqtt.mqtt import Mqtt
from cleep.exception import CommandError, InvalidParameter
from cleep.libs.tests import session


class PublishResult:
    mid = 123
    rc = 0


class MqttMessage:
    topic = "home/motion"
    payload = b'{"motion": true}'
    qos = 1
    retain = False


class MqttTests(unittest.TestCase):
    def setUp(self):
        self.session = session.TestSession(self)

    def tearDown(self):
        self.session.clean()

    def init(self):
        with patch("cleep.libs.tests.session.CleepFilesystem") as filesystem_mock:
            filesystem_mock.return_value.enable_write = Mock()
            self.module = self.session.setup(Mqtt)
        self.module.message_received_event = Mock()
        self.module.connection_changed_event = Mock()

    def test_get_module_config_hides_password(self):
        self.init()
        self.module._update_config({"password": "secret"})

        config = self.module.get_module_config()

        self.assertEqual(config["password"], "")
        self.assertTrue(config["password_set"])

    def test_publish_json_payload(self):
        self.init()
        self.module.connected = True
        self.module.client = Mock()
        self.module.client.publish.return_value = PublishResult()

        result = self.module.publish("home/motion", {"motion": True}, qos=1, retain=True)

        self.assertEqual(result["mid"], 123)
        self.assertEqual(result["rc"], 0)
        self.module.client.publish.assert_called_with(
            "home/motion",
            '{"motion": true}',
            qos=1,
            retain=True,
        )

    def test_publish_requires_connection(self):
        self.init()

        with self.assertRaises(CommandError):
            self.module.publish("home/motion", "test")

    def test_publish_validates_qos(self):
        self.init()
        self.module.connected = True
        self.module.client = Mock()

        with self.assertRaises(InvalidParameter):
            self.module.publish("home/motion", "test", qos=3)

    def test_subscribe_saves_subscription_and_calls_client(self):
        self.init()
        self.module.connected = True
        self.module.client = Mock()

        subscriptions = self.module.subscribe("home/#", qos=1)

        self.assertEqual(subscriptions, [{"topic": "home/#", "qos": 1}])
        self.assertEqual(self.module._get_config_field("subscriptions"), subscriptions)
        self.module.client.subscribe.assert_called_with("home/#", qos=1)

    def test_unsubscribe_removes_subscription_and_calls_client(self):
        self.init()
        self.module.connected = True
        self.module.client = Mock()
        self.module._update_config({
            "subscriptions": [
                {"topic": "home/#", "qos": 1},
                {"topic": "cleep/#", "qos": 0},
            ]
        })

        subscriptions = self.module.unsubscribe("home/#")

        self.assertEqual(subscriptions, [{"topic": "cleep/#", "qos": 0}])
        self.module.client.unsubscribe.assert_called_with("home/#")

    def test_received_message_is_emitted_as_event(self):
        self.init()

        self.module._Mqtt__on_message(None, None, MqttMessage())
        self.module._on_process()

        self.module.message_received_event.send.assert_called_with({
            "topic": "home/motion",
            "payload": {"motion": True},
            "payload_raw": '{"motion": true}',
            "payload_type": "dict",
            "qos": 1,
            "retained": False,
            "timestamp": session.AnyArg(),
        })

    def test_update_settings_reconnects(self):
        self.init()
        self.module._disconnect = Mock()
        self.module._connect = Mock()

        config = self.module.update_settings(
            enabled=True,
            host="broker.local",
            port=1884,
            subscriptions=[{"topic": "home/#", "qos": 1}],
        )

        self.assertTrue(config["enabled"])
        self.assertEqual(config["host"], "broker.local")
        self.assertEqual(config["port"], 1884)
        self.assertEqual(
            self.module._get_config_field("subscriptions"),
            [{"topic": "home/#", "qos": 1}],
        )
        self.module._disconnect.assert_called_once()
        self.module._connect.assert_called_once()

    def test_on_event_can_publish_cleep_events(self):
        self.init()
        self.module._update_config({"publish_events": True})
        self.module.publish = Mock()

        self.module.on_event({
            "event": "system.device.reboot",
            "params": {"delay": 1},
            "device_id": "abc",
            "sender": "system",
            "startup": False,
        })

        self.module.publish.assert_called_once()
        args = self.module.publish.call_args[0]
        self.assertEqual(args[0], "cleep/events/system/device/reboot")
        self.assertEqual(args[1]["event"], "system.device.reboot")


if __name__ == "__main__":
    unittest.main()
