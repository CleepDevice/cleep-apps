#!/bin/bash

set -e

python3 -m pip uninstall -y adafruit-circuitpython-lsm6ds adafruit-blinka || true
