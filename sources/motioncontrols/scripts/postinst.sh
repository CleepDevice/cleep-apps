#!/bin/bash

set -e

apt-get update
apt-get install -y -q python3-smbus i2c-tools
python3 -m pip install --trusted-host pypi.org "adafruit-blinka>=8.0.0,<9.0.0" "adafruit-circuitpython-lsm6ds>=4.0.0,<5.0.0"
