import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

DATA = ROOT / "data"


def load_dir(directory):
    return {p.stem: json.loads(p.read_text(encoding="utf-8")) for p in sorted(Path(directory).glob("*.json"))}


def run_cli(*args):
    return subprocess.run(
        [sys.executable, "-m", "extraction_demo", *args],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
