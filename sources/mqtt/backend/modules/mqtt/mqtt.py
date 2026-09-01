#!/usr/bin/env python
# -*- coding: utf-8 -*-

import json
import queue
import time

try:
    import paho.mqtt.client as paho_mqtt
except ImportError:  # pragma: no cover
    paho_mqtt = None

from cleep.common import CATEGORIES
from cleep.core import CleepModule
from cleep.exception import CommandError, InvalidParameter

__all__ = ["Mqtt"]


class Mqtt(CleepModule):
    """
    MQTT bridge module.

    It can publish messages to an MQTT broker and convert subscribed MQTT
    messages into Cleep events.
    """

    MODULE_AUTHOR = "Cleep"
    MODULE_VERSION = "1.0.0"
    MODULE_DEPS = []
    MODULE_DESCRIPTION = "Send and receive MQTT messages"
    MODULE_LONGDESCRIPTION = (
        "Connects Cleep to an MQTT broker. Other modules can publish MQTT "
        "messages through this module, and incoming MQTT messages are exposed "
        "as Cleep events."
    )
    MODULE_TAGS = ["mqtt", "iot", "broker", "messages"]
    MODULE_CATEGORY = CATEGORIES.SERVICE
    MODULE_COUNTRY = None
    MODULE_URLINFO = "https://github.com/CleepDevice/cleep-apps"
    MODULE_URLHELP = None
    MODULE_URLSITE = "https://mqtt.org/"
    MODULE_URLBUGS = "https://github.com/CleepDevice/cleep-apps/issues"

    MODULE_CONFIG_FILE = "mqtt.conf"
    DEFAULT_CONFIG = {
        "enabled": False,
        "host": "localhost",
        "port": 1883,
        "client_id": "cleep",
        "username": "",
        "password": "",
        "tls": False,
        "ca_cert": "",
        "client_cert": "",
        "client_key": "",
        "insecure_tls": False,
        "keepalive": 60,
        "default_qos": 0,
        "retain": False,
        "subscriptions": [],
        "publish_events": False,
        "event_topic_prefix": "cleep/events",
    }

    RECONNECT_FIELDS = [
        "enabled",
        "host",
        "port",
        "client_id",
        "username",
        "password",
        "tls",
        "ca_cert",
        "client_cert",
        "client_key",
        "insecure_tls",
        "keepalive",
        "subscriptions",
    ]

    def __init__(self, bootstrap, debug_enabled):
        CleepModule.__init__(self, bootstrap, debug_enabled)

        self.client = None
        self.connected = False
        self.last_error = None
        self.messages = queue.Queue()
        self.message_received_event = self._get_event("mqtt.message.received")
        self.connection_changed_event = self._get_event("mqtt.connection.changed")

    def _configure(self):
        """
        Configure MQTT runtime state.
        """
        self.connected = False
        self.last_error = None

    def _on_start(self):
        """
        Connect to the MQTT broker after all Cleep modules are ready.
        """
        self._connect()

    def _on_stop(self):
        """
        Disconnect cleanly when Cleep stops.
        """
        self._disconnect()

    def _on_process(self):
        """
        Emit queued MQTT messages as Cleep events.
        """
        while not self.messages.empty():
            self.message_received_event.send(self.messages.get())

    def on_event(self, event):
        """
        Optionally publish Cleep events to MQTT.

        Args:
            event (dict): Cleep event data
        """
        config = self._get_config()
        if not config["publish_events"] or event.get("startup"):
            return
        if event.get("event", "").startswith("mqtt."):
            return

        topic = "%s/%s" % (
            config["event_topic_prefix"].rstrip("/"),
            event["event"].replace(".", "/"),
        )
        payload = {
            "event": event.get("event"),
            "params": event.get("params"),
            "device_id": event.get("device_id"),
            "sender": event.get("sender"),
            "timestamp": int(time.time()),
        }
        try:
            self.publish(topic, payload)
        except Exception:
            self.logger.exception('Unable to publish Cleep event "%s"', event.get("event"))

    def get_module_config(self):
        """
        Return MQTT configuration without leaking the password.

        Returns:
            dict: module configuration
        """
        config = self._get_config()
        config["password_set"] = bool(config.get("password"))
        config["password"] = ""
        config["connected"] = self.connected
        config["last_error"] = self.last_error
        return config

    def get_status(self):
        """
        Return MQTT connection status.

        Returns:
            dict: connection status
        """
        config = self._get_config()
        return {
            "enabled": config["enabled"],
            "connected": self.connected,
            "host": config["host"],
            "port": config["port"],
            "subscriptions": self._normalize_subscriptions(config["subscriptions"]),
            "last_error": self.last_error,
        }

    def publish(self, topic, payload, qos=None, retain=None):
        """
        Publish an MQTT message.

        Args:
            topic (str): MQTT topic
            payload (str|dict|list|int|float|bool|None): message payload
            qos (int, optional): MQTT QoS level. Defaults to configured value.
            retain (bool, optional): retain flag. Defaults to configured value.

        Returns:
            dict: publish result containing topic, message id, and result code
        """
        self._check_parameters([
            {"name": "topic", "value": topic, "type": str, "empty": False},
        ])

        config = self._get_config()
        qos = config["default_qos"] if qos is None else qos
        retain = config["retain"] if retain is None else retain
        self.__check_qos(qos)

        if not self.client or not self.connected:
            raise CommandError("MQTT client is not connected")

        result = self.client.publish(
            topic,
            self.__encode_payload(payload),
            qos=qos,
            retain=retain,
        )
        return {
            "topic": topic,
            "mid": result.mid,
            "rc": result.rc,
        }

    def subscribe(self, topic, qos=None):
        """
        Subscribe to an MQTT topic and save it in configuration.

        Args:
            topic (str): MQTT topic filter
            qos (int, optional): MQTT QoS level. Defaults to configured value.

        Returns:
            list: configured subscriptions
        """
        self._check_parameters([
            {"name": "topic", "value": topic, "type": str, "empty": False},
        ])

        config = self._get_config()
        qos = config["default_qos"] if qos is None else qos
        self.__check_qos(qos)

        subscriptions = [
            sub for sub in self._normalize_subscriptions(config["subscriptions"])
            if sub["topic"] != topic
        ]
        subscriptions.append({"topic": topic, "qos": qos})
        self._update_config({"subscriptions": subscriptions})

        if self.client and self.connected:
            self.client.subscribe(topic, qos=qos)

        return subscriptions

    def unsubscribe(self, topic):
        """
        Unsubscribe from an MQTT topic and remove it from configuration.

        Args:
            topic (str): MQTT topic filter

        Returns:
            list: configured subscriptions
        """
        self._check_parameters([
            {"name": "topic", "value": topic, "type": str, "empty": False},
        ])

        config = self._get_config()
        subscriptions = [
            sub for sub in self._normalize_subscriptions(config["subscriptions"])
            if sub["topic"] != topic
        ]
        self._update_config({"subscriptions": subscriptions})

        if self.client and self.connected:
            self.client.unsubscribe(topic)

        return subscriptions

    def update_settings(
        self,
        enabled=None,
        host=None,
        port=None,
        client_id=None,
        username=None,
        password=None,
        tls=None,
        ca_cert=None,
        client_cert=None,
        client_key=None,
        insecure_tls=None,
        keepalive=None,
        default_qos=None,
        retain=None,
        subscriptions=None,
        publish_events=None,
        event_topic_prefix=None,
    ):
        """
        Update MQTT settings.

        Args:
            enabled (bool, optional): enable broker connection
            host (str, optional): MQTT broker host
            port (int, optional): MQTT broker port
            client_id (str, optional): MQTT client identifier
            username (str, optional): MQTT username
            password (str, optional): MQTT password
            tls (bool, optional): enable TLS
            ca_cert (str, optional): CA certificate path
            client_cert (str, optional): client certificate path
            client_key (str, optional): client key path
            insecure_tls (bool, optional): allow insecure TLS certificates
            keepalive (int, optional): MQTT keepalive value in seconds
            default_qos (int, optional): default MQTT QoS
            retain (bool, optional): default retain flag
            subscriptions (list, optional): list of topic strings or dicts
            publish_events (bool, optional): publish Cleep events to MQTT
            event_topic_prefix (str, optional): MQTT prefix for Cleep events

        Returns:
            dict: sanitized module configuration
        """
        updates = {}
        self.__add_update(updates, "enabled", enabled, bool)
        self.__add_update(updates, "host", host, str)
        self.__add_update(updates, "port", port, int)
        self.__add_update(updates, "client_id", client_id, str)
        self.__add_update(updates, "username", username, str)
        self.__add_update(updates, "password", password, str)
        self.__add_update(updates, "tls", tls, bool)
        self.__add_update(updates, "ca_cert", ca_cert, str)
        self.__add_update(updates, "client_cert", client_cert, str)
        self.__add_update(updates, "client_key", client_key, str)
        self.__add_update(updates, "insecure_tls", insecure_tls, bool)
        self.__add_update(updates, "keepalive", keepalive, int)
        self.__add_update(updates, "default_qos", default_qos, int)
        self.__add_update(updates, "retain", retain, bool)
        self.__add_update(updates, "publish_events", publish_events, bool)
        self.__add_update(updates, "event_topic_prefix", event_topic_prefix, str)

        if subscriptions is not None:
            updates["subscriptions"] = self._normalize_subscriptions(subscriptions)

        if "default_qos" in updates:
            self.__check_qos(updates["default_qos"])
        if "subscriptions" in updates:
            for subscription in updates["subscriptions"]:
                self.__check_qos(subscription["qos"])

        reconnect = any(field in updates for field in self.RECONNECT_FIELDS)
        self._update_config(updates)

        if reconnect:
            self._disconnect()
            self._connect()

        return self.get_module_config()

    def _connect(self):
        """
        Connect to MQTT broker.

        Returns:
            bool: True if connection was started
        """
        config = self._get_config()
        if not config["enabled"]:
            self.last_error = None
            return False
        if paho_mqtt is None:
            raise CommandError("paho-mqtt is not installed")

        try:
            client = paho_mqtt.Client(client_id=config["client_id"] or "")
            client.on_connect = self.__on_connect
            client.on_disconnect = self.__on_disconnect
            client.on_message = self.__on_message

            if config["username"]:
                client.username_pw_set(config["username"], config["password"] or None)

            if config["tls"]:
                client.tls_set(
                    ca_certs=config["ca_cert"] or None,
                    certfile=config["client_cert"] or None,
                    keyfile=config["client_key"] or None,
                )
                if config["insecure_tls"]:
                    client.tls_insecure_set(True)

            client.connect(config["host"], config["port"], config["keepalive"])
            client.loop_start()
            self.client = client
            self.last_error = None
            return True

        except Exception as error:
            self.connected = False
            self.last_error = str(error)
            self.logger.exception("Unable to connect to MQTT broker:")
            raise CommandError("Unable to connect to MQTT broker") from error

    def _disconnect(self):
        """
        Disconnect current MQTT client.
        """
        if not self.client:
            self.connected = False
            return

        try:
            self.client.loop_stop()
            self.client.disconnect()
        except Exception:
            self.logger.exception("Unable to disconnect MQTT client:")
        finally:
            self.client = None
            self.connected = False

    def _normalize_subscriptions(self, subscriptions):
        """
        Normalize subscription config.

        Args:
            subscriptions (list): list of topic strings or dicts

        Returns:
            list: list of dicts with topic and qos fields
        """
        if subscriptions is None:
            return []
        if not isinstance(subscriptions, list):
            raise InvalidParameter('Parameter "subscriptions" must be a list')

        normalized = []
        default_qos = self._get_config_field("default_qos", 0)
        for subscription in subscriptions:
            if isinstance(subscription, str):
                topic = subscription
                qos = default_qos
            elif isinstance(subscription, dict):
                topic = subscription.get("topic")
                qos = subscription.get("qos", default_qos)
            else:
                raise InvalidParameter("Subscription must be a topic string or dict")

            if not topic or not isinstance(topic, str):
                raise InvalidParameter("Subscription topic must be a non empty string")
            self.__check_qos(qos)
            normalized.append({"topic": topic, "qos": qos})

        return normalized

    def __on_connect(self, client, userdata, flags, code, *args):
        """
        MQTT connected callback.
        """
        config = self._get_config()
        self.connected = code == 0
        self.last_error = None if self.connected else "Connection failed with code %s" % code

        if self.connected:
            for subscription in self._normalize_subscriptions(config["subscriptions"]):
                client.subscribe(subscription["topic"], qos=subscription["qos"])

        self.connection_changed_event.send({
            "connected": self.connected,
            "host": config["host"],
            "port": config["port"],
            "code": code,
            "message": self.last_error,
            "timestamp": int(time.time()),
        })

    def __on_disconnect(self, client, userdata, code, *args):
        """
        MQTT disconnected callback.
        """
        config = self._get_config()
        self.connected = False
        self.last_error = None if code == 0 else "Disconnected with code %s" % code
        self.connection_changed_event.send({
            "connected": False,
            "host": config["host"],
            "port": config["port"],
            "code": code,
            "message": self.last_error,
            "timestamp": int(time.time()),
        })

    def __on_message(self, client, userdata, message):
        """
        MQTT message callback.
        """
        payload_raw = message.payload.decode("utf-8", errors="replace")
        payload = payload_raw
        payload_type = "string"

        try:
            payload = json.loads(payload_raw)
            payload_type = type(payload).__name__
        except ValueError:
            pass

        self.messages.put({
            "topic": message.topic,
            "payload": payload,
            "payload_raw": payload_raw,
            "payload_type": payload_type,
            "qos": message.qos,
            "retained": message.retain,
            "timestamp": int(time.time()),
        })

    def __encode_payload(self, payload):
        """
        Encode payload before publishing.
        """
        if isinstance(payload, bytes):
            return payload
        if isinstance(payload, str):
            return payload
        return json.dumps(payload)

    def __check_qos(self, qos):
        """
        Validate MQTT QoS.
        """
        if not isinstance(qos, int) or qos < 0 or qos > 2:
            raise InvalidParameter("MQTT QoS must be 0, 1, or 2")

    def __add_update(self, updates, field, value, expected_type):
        """
        Add a typed optional setting update.
        """
        if value is None:
            return
        if not isinstance(value, expected_type):
            raise InvalidParameter(
                'Parameter "%s" must be of type "%s"' % (field, expected_type.__name__)
            )
        updates[field] = value
