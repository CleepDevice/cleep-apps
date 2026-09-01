#!/bin/bash

set -e

python3 -m pip uninstall -y paho-mqtt || /bin/true
