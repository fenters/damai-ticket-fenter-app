"""Compatibility wrapper that proxies to the modular Appium runner."""

from __future__ import annotations

import sys

from damai_appium.damai_app_v2 import main


if __name__ == "__main__":
    sys.exit(main())
