#!/usr/bin/env python3
"""Django management entry point for VoxERP."""
import os
import sys


def main() -> None:
    if len(sys.argv) > 1 and sys.argv[1] == "test":
        # Management tests must not inherit the developer's live ERP .env.
        os.environ.update(VOXERP_USE_REAL_DB="False", VOXERP_ALLOW_REAL_WRITES="False",
                          VOXERP_INITIALIZE_DATABASE="False", VOXERP_ENV="development",
                          VOXERP_OFFLINE_MODE="False", HF_HUB_OFFLINE="1",
                          TRANSFORMERS_OFFLINE="1")
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
    from django.core.management import execute_from_command_line
    execute_from_command_line(sys.argv)


if __name__ == "__main__":
    main()
