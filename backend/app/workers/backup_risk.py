"""Consistent risk-engine snapshot streamed to the operator, never logged."""
from io import BytesIO
from pathlib import Path
import sqlite3
import sys
import tarfile
import tempfile

from risk_engine.config import DATA_DIR


def main():
    with tempfile.TemporaryDirectory() as directory:
        snapshots = Path(directory)
        with tarfile.open(fileobj=sys.stdout.buffer, mode="w|gz") as archive:
            for source in sorted(DATA_DIR.iterdir()):
                if source.name in {"rba.db", "audit.db"}:
                    target = snapshots / source.name
                    with sqlite3.connect(f"file:{source}?mode=ro", uri=True) as original, sqlite3.connect(target) as copy:
                        original.backup(copy)
                    archive.add(target, arcname=source.name)
                elif source.name in {"engine_state.json", "risk_config.json"}:
                    content = source.read_bytes()
                    info = tarfile.TarInfo(source.name)
                    info.size = len(content)
                    info.mode = 0o600
                    archive.addfile(info, BytesIO(content))


if __name__ == "__main__":
    main()
