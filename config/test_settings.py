"""Explicit pytest settings; production settings retain fail-closed defaults."""
import os

os.environ.update(
    VOXERP_ENV="development", VOXERP_USE_REAL_DB="False",
    VOXERP_ALLOW_REAL_WRITES="False", VOXERP_INITIALIZE_DATABASE="False",
    VOXERP_DISABLE_GEMMA="True", VOXERP_OFFLINE_MODE="False",
    HF_HUB_OFFLINE="1", TRANSFORMERS_OFFLINE="1",
)
from .settings import *  # noqa: E402,F403
