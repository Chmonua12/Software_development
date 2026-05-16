#!/usr/bin/env python3
from __future__ import annotations

import os
import sys


def check_environment() -> bool:
    if os.getenv("TELEGRAM_BOT_TOKEN"):
        return True
    print("TELEGRAM_BOT_TOKEN is not set.")
    print("PowerShell: $env:TELEGRAM_BOT_TOKEN='your_bot_token_here'")
    return False


def main() -> None:
    if not check_environment():
        sys.exit(1)
    from bot.main import main as run_aiogram_bot

    run_aiogram_bot()


if __name__ == "__main__":
    main()
