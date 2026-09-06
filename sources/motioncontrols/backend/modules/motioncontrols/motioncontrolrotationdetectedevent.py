#!/usr/bin/env python
# -*- coding: utf-8 -*-

from cleep.libs.internals.event import Event


class MotioncontrolRotationDetectedEvent(Event):
    """
    motioncontrols.rotation.detected event
    """

    EVENT_NAME = "motioncontrols.rotation.detected"
    EVENT_PARAMS = [
        "direction",
        "axis",
        "angle",
        "threshold",
        "timestamp",
    ]

    def __init__(self, params):
        Event.__init__(self, params)
