#!/bin/bash

set -e

apt-get update
apt-get install -y -q libusb-1.0-0
python3 -m pip install --trusted-host pypi.org "pyserial>=3.5,<4.0" "nfcpy>=1.0.4,<2.0.0"
