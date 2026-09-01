#!/usr/bin/env python
# -*- coding: utf-8 -*-

from cleep.libs.internals.event import Event


class NfcreaderStatusChangedEvent(Event):
    """
    nfcreader.status.changed event
    """

    EVENT_NAME = "nfcreader.status.changed"
    EVENT_PARAMS = [
        "enabled",
        "backend",
        "connected",
        "message",
        "timestamp",
    ]

    def __init__(self, params):
        Event.__init__(self, params)
