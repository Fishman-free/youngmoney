"""Configuration loading (JSON; stdlib only).

Path fields inside the config are resolved relative to the project root so
`python -m bnbot...` behaves the same regardless of the working directory.
"""

import json
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_CONFIG_PATH = os.path.join(ROOT, "config.json")

# config keys holding filesystem paths that should be resolved against ROOT
_PATH_KEYS = (
    ("data", "data_dir"),
    ("risk", "kill_switch_file"),
    ("live", "state_file"),
    ("live", "log_dir"),
)


def _resolve(path):
    return path if os.path.isabs(path) else os.path.normpath(os.path.join(ROOT, path))


def load_config(path=None):
    """Load config.json and resolve relative path fields against ROOT."""
    path = path or os.environ.get("BNBOT_CONFIG") or DEFAULT_CONFIG_PATH
    with open(path, "r", encoding="utf-8") as f:
        cfg = json.load(f)
    for section, key in _PATH_KEYS:
        if section in cfg and key in cfg[section]:
            cfg[section][key] = _resolve(cfg[section][key])
    return cfg
