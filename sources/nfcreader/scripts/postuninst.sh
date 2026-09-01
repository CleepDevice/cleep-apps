#!/bin/bash

set -e

python3 -m pip uninstall -y pyserial nfcpy || true
