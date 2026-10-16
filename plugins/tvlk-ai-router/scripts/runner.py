"""Isolated entry point: only the durable installed source directory is added."""
import os
import sys
from pathlib import Path

root = Path(__file__).resolve().parent
os.environ["TVLK_ROUTER_SHELL_ROOT"] = str(root)
os.environ["TVLK_ROUTER_BACKEND"] = "plugin"
sys.path.insert(0, str(root))
from runtime import selected_source
source = root / "src" if sys.argv[1:2] == ["shell-install"] or not (root / "active.json").exists() else selected_source(root)
sys.path.insert(0, str(source))
from tvlk_ai_router.cli import main

sys.exit(main())
