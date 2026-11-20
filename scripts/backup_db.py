"""P5 (plan, section 5): dump the database before demos.  python -m scripts.backup_db

Writes storage/backups/docs_db-YYYYmmdd-HHMMSS.dump (custom format, git-ignored). Restore with:
    docker exec -i document-managment-system pg_restore -U postgres -d docs_db --clean < storage/backups/<file>.dump
The uploaded files live in storage/uploads; copy that folder together with the dump.
"""
import subprocess
import sys
from datetime import datetime
from pathlib import Path

from database.config import get_db_settings

CONTAINER = "document-managment-system"


def main() -> None:
    settings = get_db_settings()
    folder = Path("storage/backups")
    folder.mkdir(parents=True, exist_ok=True)
    target = folder / f"{settings['pgdb']}-{datetime.now():%Y%m%d-%H%M%S}.dump"
    with target.open("wb") as out:
        result = subprocess.run(["docker", "exec", CONTAINER, "pg_dump", "-U", settings["pguser"], "-Fc",
                                 settings["pgdb"]], stdout=out, stderr=subprocess.PIPE)
    if result.returncode != 0:
        target.unlink(missing_ok=True)
        sys.exit("pg_dump failed: " + result.stderr.decode(errors="replace"))
    print(f"backup written: {target} ({target.stat().st_size // 1024} KB)")


if __name__ == "__main__":
    main()
