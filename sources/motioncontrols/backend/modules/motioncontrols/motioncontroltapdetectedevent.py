#!/usr/bin/env python
# -*- coding: utf-8 -*-

from cleep.libs.internals.event import Event


class MotioncontrolTapDetectedEvent(Event):
    """
    motioncontrols.tap.detected event
    """

    EVENT_NAME = "motioncontrols.tap.detected"
    EVENT_PARAMS = [
        "side",
        "axis",
        "acceleration_g",
        "confidence",
        "timestamp",
    ]

    def __init__(self, params):
        Event.__init__(self, params)
