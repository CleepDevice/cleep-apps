#!/usr/bin/env python
# -*- coding: utf-8 -*-

from cleep.libs.internals.event import Event


class MqttMessageReceivedEvent(Event):
    """
    mqtt.message.received event
    """

    EVENT_NAME = "mqtt.message.received"
    EVENT_PARAMS = [
        "topic",
        "payload",
        "payload_raw",
        "payload_type",
        "qos",
        "retained",
        "timestamp",
    ]

    def __init__(self, params):
        Event.__init__(self, params)
