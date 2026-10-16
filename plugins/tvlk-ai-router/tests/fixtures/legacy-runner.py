"""Isolated entry point: only the durable installed source directory is added."""
import os
import sys
from pathlib import Path

root = Path(__file__).resolve().parent
os.environ["TVLK_ROUTER_SHELL_ROOT"] = str(root)
sys.path.insert(0, str(root / "src"))
from tvlk_ai_router.cli import main

sys.exit(main())
