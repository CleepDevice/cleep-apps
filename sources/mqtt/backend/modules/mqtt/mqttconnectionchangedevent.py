#!/usr/bin/env python
# -*- coding: utf-8 -*-

from cleep.libs.internals.event import Event


class MqttConnectionChangedEvent(Event):
    """
    mqtt.connection.changed event
    """

    EVENT_NAME = "mqtt.connection.changed"
    EVENT_PARAMS = ["connected", "host", "port", "code", "message", "timestamp"]

    def __init__(self, params):
        Event.__init__(self, params)
