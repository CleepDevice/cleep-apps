import sys
import unittest
from unittest.mock import Mock, patch

sys.path.append("../")

from backend.modules.nfcreader.nfcreader import Nfcreader, TagReaderThread
from cleep.exception import InvalidParameter
from cleep.libs.tests import session


class NfcreaderTests(unittest.TestCase):
    def setUp(self):
        self.session = session.TestSession(self)

    def tearDown(self):
        self.session.clean()

    def init(self):
        with patch("cleep.libs.tests.session.CleepFilesystem") as filesystem_mock:
            filesystem_mock.return_value.enable_write = Mock()
            self.module = self.session.setup(Nfcreader)
        self.module.tag_detected_event = Mock()
        self.module.status_changed_event = Mock()

    def test_normalize_uid_accepts_common_formats(self):
        self.assertEqual(
            TagReaderThread.normalize_uid("E0 04 03 12 34 56 78 90"),
            "E004031234567890",
        )
        self.assertEqual(
            TagReaderThread.normalize_uid("e0:04:03:12:34:56:78:90"),
            "E004031234567890",
        )
        self.assertEqual(
            TagReaderThread.normalize_uid(bytes.fromhex("e004031234567890")),
            "E004031234567890",
        )

    def test_parse_uid_from_serial_line(self):
        self.assertEqual(
            TagReaderThread.parse_uid_from_line(b"UID:E0-04-03-12-34-56-78-90\r\n"),
            "E004031234567890",
        )

    def test_update_settings_saves_and_restarts(self):
        self.init()
        self.module._stop_reader = Mock()
        self.module._start_reader = Mock()

        config = self.module.update_settings(
            enabled=True,
            backend="serial",
            serial_port="/dev/ttyACM0",
            serial_baudrate=9600,
            allowed_prefixes=["E00403"],
        )

        self.assertTrue(config["enabled"])
        self.assertEqual(config["serial_port"], "/dev/ttyACM0")
        self.assertEqual(config["serial_baudrate"], 9600)
        self.assertEqual(config["allowed_prefixes"], ["E00403"])
        self.module._stop_reader.assert_called_once()
        self.module._start_reader.assert_called_once()

    def test_update_settings_validates_backend(self):
        self.init()

        with self.assertRaises(InvalidParameter):
            self.module.update_settings(backend="unknown")

    def test_queued_tag_is_emitted_as_event(self):
        self.init()

        self.module._Nfcreader__queue_tag({
            "uid": "E004031234567890",
            "uid_normalized": "E004031234567890",
            "source": "serial",
            "tag_type": "unknown",
            "raw": "UID:E0 04 03 12 34 56 78 90",
            "timestamp": session.AnyArg(),
        })
        self.module._on_process()

        self.module.tag_detected_event.send.assert_called_once()
        self.assertEqual(
            self.module.tag_detected_event.send.call_args[0][0]["uid_normalized"],
            "E004031234567890",
        )
        self.assertEqual(
            self.module.get_last_tag()["uid_normalized"],
            "E004031234567890",
        )

    def test_duplicate_tag_is_ignored_inside_dedupe_window(self):
        self.init()

        tag = {
            "uid": "E004031234567890",
            "uid_normalized": "E004031234567890",
            "source": "serial",
            "tag_type": "unknown",
            "raw": "UID:E0 04 03 12 34 56 78 90",
            "timestamp": session.AnyArg(),
        }
        self.module._Nfcreader__queue_tag(tag)
        self.module._Nfcreader__queue_tag(tag)
        self.module._on_process()

        self.module.tag_detected_event.send.assert_called_once()

    def test_allowed_prefix_filters_tag(self):
        self.init()
        self.module._update_config({"allowed_prefixes": ["E00403"]})

        self.module._Nfcreader__queue_tag({
            "uid": "0102030405060708",
            "uid_normalized": "0102030405060708",
            "source": "serial",
            "tag_type": "unknown",
            "raw": "UID:0102030405060708",
            "timestamp": session.AnyArg(),
        })
        self.module._on_process()

        self.module.tag_detected_event.send.assert_not_called()

    def test_status_update_is_emitted_as_event(self):
        self.init()

        self.module._Nfcreader__queue_status(True, None)
        self.module._on_process()

        self.assertTrue(self.module.reader_connected)
        self.module.status_changed_event.send.assert_called_with({
            "enabled": False,
            "backend": "serial",
            "connected": True,
            "message": None,
            "timestamp": session.AnyArg(),
        })

    def test_clear_last_tag(self):
        self.init()
        self.module.last_tag = {"uid_normalized": "E004031234567890"}

        self.assertEqual(self.module.clear_last_tag(), {"last_tag": None})
        self.assertIsNone(self.module.get_last_tag())


if __name__ == "__main__":
    unittest.main()
