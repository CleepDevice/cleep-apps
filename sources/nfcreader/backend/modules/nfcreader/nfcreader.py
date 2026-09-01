#!/usr/bin/env python
# -*- coding: utf-8 -*-

import queue
import re
import time
from threading import Thread

try:
    import serial
except ImportError:  # pragma: no cover
    serial = None

try:
    import nfc
except ImportError:  # pragma: no cover
    nfc = None

from cleep.common import CATEGORIES
from cleep.core import CleepModule
from cleep.exception import InvalidParameter

__all__ = ["Nfcreader"]


class TagReaderThread(Thread):
    """
    Background NFC reader loop.

    The serial backend expects a reader or bridge firmware that prints one UID
    per line. This is the most practical path for ISO15693 readers used with
    Tonie-style tags because reader hardware support varies a lot.
    """

    UID_PATTERN = re.compile(r"(?:[0-9A-Fa-f]{2}[\s:.\-]?){4,16}")

    def __init__(self, config, on_tag, on_status, logger):
        Thread.__init__(self)
        self.daemon = True
        self.continu = True
        self.config = config
        self.on_tag = on_tag
        self.on_status = on_status
        self.logger = logger
        self.reader = None

    def stop(self):
        """
        Stop reader loop.
        """
        self.continu = False
        self.__close_reader()

    def run(self):
        """
        Start selected reader backend.
        """
        backend = self.config["backend"]
        if backend == "serial":
            self.__run_serial()
        elif backend == "nfcpy":
            self.__run_nfcpy()
        else:
            self.on_status(False, 'Unsupported backend "%s"' % backend)

    @classmethod
    def normalize_uid(cls, uid, uppercase=True):
        """
        Normalize UID string to hexadecimal characters.

        Args:
            uid (str|bytes): raw UID
            uppercase (bool): return uppercase UID

        Returns:
            str|None: normalized UID or None when invalid
        """
        if uid is None:
            return None
        if isinstance(uid, bytes):
            value = uid.hex()
        else:
            value = str(uid)

        normalized = re.sub(r"[^0-9A-Fa-f]", "", value)
        if len(normalized) < 8 or len(normalized) > 32 or len(normalized) % 2:
            return None
        if not re.match(r"^[0-9A-Fa-f]+$", normalized):
            return None

        return normalized.upper() if uppercase else normalized.lower()

    @classmethod
    def parse_uid_from_line(cls, line, uppercase=True):
        """
        Extract the first UID-like value from a serial reader line.

        Args:
            line (str|bytes): reader output
            uppercase (bool): return uppercase UID

        Returns:
            str|None: parsed UID
        """
        if isinstance(line, bytes):
            text = line.decode("utf-8", errors="replace")
        else:
            text = str(line)

        for match in cls.UID_PATTERN.finditer(text):
            uid = cls.normalize_uid(match.group(0), uppercase)
            if uid:
                return uid
        return None

    def __run_serial(self):
        """
        Read UID lines from serial reader.
        """
        if serial is None:
            self.on_status(False, "pyserial is not installed")
            return
        if not self.config["serial_port"]:
            self.on_status(False, "Serial port is not configured")
            return

        while self.continu:
            try:
                self.reader = serial.Serial(
                    self.config["serial_port"],
                    self.config["serial_baudrate"],
                    timeout=self.config["serial_timeout"],
                )
                self.on_status(True, None)

                while self.continu:
                    line = self.reader.readline()
                    if not line:
                        continue

                    uid = self.parse_uid_from_line(line, self.config["uppercase"])
                    if uid:
                        self.__emit_tag(uid, "serial", "unknown", line)

            except Exception as error:
                self.logger.exception("NFC serial reader error:")
                self.on_status(False, str(error))
                time.sleep(max(1.0, self.config["poll_delay"]))
            finally:
                self.__close_reader()

    def __run_nfcpy(self):
        """
        Read tags with nfcpy-compatible USB readers.
        """
        if nfc is None:
            self.on_status(False, "nfcpy is not installed")
            return

        while self.continu:
            try:
                with nfc.ContactlessFrontend(self.config["nfcpy_path"]) as reader:
                    self.reader = reader
                    self.on_status(True, None)

                    while self.continu:
                        reader.connect(
                            rdwr={"on-connect": self.__on_nfcpy_connect},
                            terminate=lambda: not self.continu,
                        )
                        time.sleep(self.config["poll_delay"])

            except Exception as error:
                self.logger.exception("NFC nfcpy reader error:")
                self.on_status(False, str(error))
                time.sleep(max(1.0, self.config["poll_delay"]))
            finally:
                self.reader = None

    def __on_nfcpy_connect(self, tag):
        """
        nfcpy tag callback.
        """
        identifier = getattr(tag, "identifier", None)
        uid = self.normalize_uid(identifier, self.config["uppercase"])
        if uid:
            self.__emit_tag(uid, "nfcpy", getattr(tag, "type", type(tag).__name__), repr(tag))
        return False

    def __emit_tag(self, uid, source, tag_type, raw):
        """
        Queue a detected tag.
        """
        raw_value = raw.decode("utf-8", errors="replace").strip() if isinstance(raw, bytes) else str(raw)
        self.on_tag({
            "uid": uid,
            "uid_normalized": uid,
            "source": source,
            "tag_type": tag_type,
            "raw": raw_value,
            "timestamp": int(time.time()),
        })

    def __close_reader(self):
        """
        Close current reader when supported.
        """
        if not self.reader:
            return

        try:
            close = getattr(self.reader, "close", None)
            if close:
                close()
        except Exception:
            self.logger.exception("Unable to close NFC reader:")
        finally:
            self.reader = None


class Nfcreader(CleepModule):
    """
    Read-only NFC UID reader.
    """

    MODULE_AUTHOR = "Cleep"
    MODULE_VERSION = "1.0.0"
    MODULE_DEPS = []
    MODULE_DESCRIPTION = "Read NFC tag UIDs"
    MODULE_LONGDESCRIPTION = (
        "Reads NFC tag UIDs and emits Cleep events when a tag is detected. "
        "For Tonie characters, use reader hardware that supports ISO15693/NFC-V tags."
    )
    MODULE_TAGS = ["nfc", "rfid", "uid", "toniebox", "iso15693"]
    MODULE_CATEGORY = CATEGORIES.DRIVER
    MODULE_COUNTRY = None
    MODULE_URLINFO = "https://github.com/CleepDevice/cleep-apps"
    MODULE_URLHELP = None
    MODULE_URLSITE = None
    MODULE_URLBUGS = "https://github.com/CleepDevice/cleep-apps/issues"

    MODULE_CONFIG_FILE = "nfcreader.conf"
    DEFAULT_CONFIG = {
        "enabled": False,
        "backend": "serial",
        "serial_port": "/dev/ttyUSB0",
        "serial_baudrate": 115200,
        "serial_timeout": 0.5,
        "nfcpy_path": "usb",
        "poll_delay": 0.2,
        "dedupe_seconds": 2.0,
        "allowed_prefixes": [],
        "uppercase": True,
    }

    RESTART_FIELDS = [
        "enabled",
        "backend",
        "serial_port",
        "serial_baudrate",
        "serial_timeout",
        "nfcpy_path",
        "poll_delay",
        "uppercase",
    ]

    BACKENDS = ["serial", "nfcpy"]

    def __init__(self, bootstrap, debug_enabled):
        CleepModule.__init__(self, bootstrap, debug_enabled)

        self.reader = None
        self.reader_connected = False
        self.last_error = None
        self.last_tag = None
        self.last_uid = None
        self.last_uid_time = 0
        self.tags = queue.Queue()
        self.statuses = queue.Queue()
        self.tag_detected_event = self._get_event("nfcreader.tag.detected")
        self.status_changed_event = self._get_event("nfcreader.status.changed")

    def _configure(self):
        """
        Reset runtime state.
        """
        self.reader_connected = False
        self.last_error = None
        self.last_tag = None
        self.last_uid = None
        self.last_uid_time = 0

    def _on_start(self):
        """
        Start reader when enabled.
        """
        self._start_reader()

    def _on_stop(self):
        """
        Stop reader cleanly.
        """
        self._stop_reader()

    def _on_process(self):
        """
        Emit queued status and tag events.
        """
        while not self.statuses.empty():
            status = self.statuses.get()
            self.reader_connected = status["connected"]
            self.last_error = status["message"]
            self.status_changed_event.send(status)

        while not self.tags.empty():
            tag = self.tags.get()
            if self.__should_ignore_tag(tag):
                continue

            self.last_tag = tag
            self.last_uid = tag["uid_normalized"]
            self.last_uid_time = time.time()
            self.tag_detected_event.send(tag)

    def get_module_config(self):
        """
        Return module configuration and runtime status.

        Returns:
            dict: module configuration
        """
        config = self._get_config()
        config["reader_connected"] = self.reader_connected
        config["last_error"] = self.last_error
        config["last_tag"] = self.last_tag
        config["reader_running"] = self.reader is not None and self.reader.is_alive()
        return config

    def get_status(self):
        """
        Return current reader status.

        Returns:
            dict: reader status
        """
        config = self._get_config()
        return {
            "enabled": config["enabled"],
            "backend": config["backend"],
            "reader_connected": self.reader_connected,
            "reader_running": self.reader is not None and self.reader.is_alive(),
            "last_error": self.last_error,
            "last_tag": self.last_tag,
        }

    def get_last_tag(self):
        """
        Return last detected tag.

        Returns:
            dict|None: last detected tag
        """
        return self.last_tag

    def clear_last_tag(self):
        """
        Clear last detected tag.

        Returns:
            dict: cleared state
        """
        self.last_tag = None
        self.last_uid = None
        self.last_uid_time = 0
        return {"last_tag": None}

    def update_settings(
        self,
        enabled=None,
        backend=None,
        serial_port=None,
        serial_baudrate=None,
        serial_timeout=None,
        nfcpy_path=None,
        poll_delay=None,
        dedupe_seconds=None,
        allowed_prefixes=None,
        uppercase=None,
    ):
        """
        Update NFC reader settings.

        Args:
            enabled (bool, optional): enable reader
            backend (str, optional): serial or nfcpy
            serial_port (str, optional): serial reader device path
            serial_baudrate (int, optional): serial baudrate
            serial_timeout (float, optional): serial read timeout
            nfcpy_path (str, optional): nfcpy reader path, usually "usb"
            poll_delay (float, optional): delay between polling loops
            dedupe_seconds (float, optional): ignore same UID during this window
            allowed_prefixes (list, optional): optional UID prefixes to accept
            uppercase (bool, optional): normalize UIDs uppercase

        Returns:
            dict: updated module configuration
        """
        updates = {}
        self.__add_update(updates, "enabled", enabled, bool)
        self.__add_update(updates, "backend", backend, str)
        self.__add_update(updates, "serial_port", serial_port, str)
        self.__add_update(updates, "serial_baudrate", serial_baudrate, int)
        self.__add_update(updates, "serial_timeout", serial_timeout, (int, float))
        self.__add_update(updates, "nfcpy_path", nfcpy_path, str)
        self.__add_update(updates, "poll_delay", poll_delay, (int, float))
        self.__add_update(updates, "dedupe_seconds", dedupe_seconds, (int, float))
        self.__add_update(updates, "uppercase", uppercase, bool)

        if "backend" in updates and updates["backend"] not in self.BACKENDS:
            raise InvalidParameter('Parameter "backend" must be "serial" or "nfcpy"')
        if "serial_baudrate" in updates and updates["serial_baudrate"] <= 0:
            raise InvalidParameter('Parameter "serial_baudrate" must be positive')
        if "serial_timeout" in updates and updates["serial_timeout"] <= 0:
            raise InvalidParameter('Parameter "serial_timeout" must be positive')
        if "poll_delay" in updates and updates["poll_delay"] <= 0:
            raise InvalidParameter('Parameter "poll_delay" must be positive')
        if "dedupe_seconds" in updates and updates["dedupe_seconds"] < 0:
            raise InvalidParameter('Parameter "dedupe_seconds" must be zero or positive')

        if allowed_prefixes is not None:
            updates["allowed_prefixes"] = self.__normalize_prefixes(allowed_prefixes)

        restart = any(field in updates for field in self.RESTART_FIELDS)
        self._update_config(updates)

        if restart:
            self._stop_reader()
            self._start_reader()

        return self.get_module_config()

    def _start_reader(self):
        """
        Start reader thread when configured.

        Returns:
            bool: True when reader thread was started
        """
        config = self._get_config()
        if not config["enabled"]:
            self.reader_connected = False
            self.last_error = None
            return False
        if self.reader and self.reader.is_alive():
            return True

        self.reader = TagReaderThread(
            config,
            self.__queue_tag,
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
            self.reader_connected = False
            return

        self.reader.stop()
        self.reader.join(2.0)
        self.reader = None
        self.reader_connected = False

    def __queue_tag(self, tag):
        """
        Queue tag event from reader thread.
        """
        self.tags.put(tag)

    def __queue_status(self, connected, message):
        """
        Queue status event from reader thread.
        """
        config = self._get_config()
        self.statuses.put({
            "enabled": config["enabled"],
            "backend": config["backend"],
            "connected": connected,
            "message": message,
            "timestamp": int(time.time()),
        })

    def __should_ignore_tag(self, tag):
        """
        Return True when tag should not emit an event.
        """
        config = self._get_config()
        uid = tag["uid_normalized"]

        prefixes = self.__normalize_prefixes(config["allowed_prefixes"])
        if prefixes and not any(uid.startswith(prefix) for prefix in prefixes):
            return True

        now = time.time()
        if (
            self.last_uid == uid
            and config["dedupe_seconds"] > 0
            and now - self.last_uid_time < config["dedupe_seconds"]
        ):
            return True

        return False

    def __normalize_prefixes(self, prefixes):
        """
        Normalize UID prefixes.
        """
        if prefixes is None:
            return []
        if isinstance(prefixes, str):
            prefixes = [part.strip() for part in prefixes.split(",") if part.strip()]
        if not isinstance(prefixes, list):
            raise InvalidParameter('Parameter "allowed_prefixes" must be a list')

        normalized = []
        uppercase = self._get_config_field("uppercase", True)
        for prefix in prefixes:
            value = self.__normalize_prefix(prefix, uppercase)
            if not value:
                raise InvalidParameter("Allowed prefix must contain hexadecimal bytes")
            normalized.append(value)
        return normalized

    def __normalize_prefix(self, prefix, uppercase):
        """
        Normalize a UID prefix, allowing shorter values than complete UIDs.
        """
        value = re.sub(r"[^0-9A-Fa-f]", "", str(prefix))
        if len(value) < 2 or len(value) > 32 or len(value) % 2:
            return None
        if not re.match(r"^[0-9A-Fa-f]+$", value):
            return None
        return value.upper() if uppercase else value.lower()

    def __add_update(self, updates, field, value, expected_type):
        """
        Add a typed optional setting update.
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
