"""Build a distributable from tracked source; never include user state or tests."""
import hashlib
import json
import subprocess
import sys
import zipfile
from pathlib import Path

repo = Path(__file__).resolve().parents[1]
package = repo / "plugins/tvlk-ai-router"
version = json.loads((package / "plugin.json").read_text())["version"]
assert json.loads((package / ".codex-plugin/plugin.json").read_text())["version"] == version
root = "FPR-Nexus-" + version + "-Local-Pack"
out = Path(sys.argv[1]) if len(sys.argv) > 1 else repo.parent / (root + ".zip")
if out.exists():
    raise SystemExit("Output exists; choose a new path to preserve previous packages")
paths = subprocess.check_output(["git", "ls-files", "-z"], cwd=repo).decode().split("\0")
selected = [p for p in paths if (p.startswith("plugins/tvlk-ai-router/") and "/tests/" not in p)
            or p in (".agents/plugins/marketplace.json", "README.md", "INSTALL.md", "OPERATIONS.md", "VALIDATION.md", "releases/policy.json")]
assert "plugins/tvlk-ai-router/src/tvlk_ai_router/history.py" in selected
with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as archive:
    for rel in sorted(selected):
        path = repo / rel
        assert path.is_file() and not path.is_symlink(), rel
        archive.write(path, root + "/" + rel)
with zipfile.ZipFile(out) as archive:
    assert archive.testzip() is None
    for rel in selected:
        assert archive.read(root + "/" + rel) == (repo / rel).read_bytes()
print(json.dumps({"path": str(out), "files": len(selected), "bytes": out.stat().st_size,
                  "sha256": hashlib.sha256(out.read_bytes()).hexdigest()}))
