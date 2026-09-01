#!/usr/bin/env python
# -*- coding: utf-8 -*-

from cleep.libs.internals.event import Event


class NfcreaderTagDetectedEvent(Event):
    """
    nfcreader.tag.detected event
    """

    EVENT_NAME = "nfcreader.tag.detected"
    EVENT_PARAMS = [
        "uid",
        "uid_normalized",
        "source",
        "tag_type",
        "raw",
        "timestamp",
    ]

    def __init__(self, params):
        Event.__init__(self, params)
