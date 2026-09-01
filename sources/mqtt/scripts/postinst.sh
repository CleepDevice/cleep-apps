#!/bin/bash

set -e

python3 -m pip install --trusted-host pypi.org "paho-mqtt>=1.6.1,<2.0.0"
