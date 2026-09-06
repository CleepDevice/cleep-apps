#!/usr/bin/env python
# -*- coding: utf-8 -*-

from cleep.libs.internals.event import Event


class MotioncontrolStatusChangedEvent(Event):
    """
    motioncontrols.status.changed event
    """

    EVENT_NAME = "motioncontrols.status.changed"
    EVENT_PARAMS = [
        "enabled",
        "connected",
        "message",
        "timestamp",
    ]

    def __init__(self, params):
        Event.__init__(self, params)
