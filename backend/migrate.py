import hashlib
import os
from pathlib import Path

import psycopg


MIGRATION_LOCK_ID = 726381947201
MIGRATION_DIR = Path(os.environ.get("MIGRATION_DIR", "/migrations"))


def main():
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        raise RuntimeError("DATABASE_URL is required")

    migrations = sorted(MIGRATION_DIR.glob("*.sql"))
    if not migrations:
        raise RuntimeError(f"No migrations found in {MIGRATION_DIR}")

    with psycopg.connect(database_url, autocommit=True) as connection:
        connection.execute("SELECT pg_advisory_lock(%s)", (MIGRATION_LOCK_ID,))
        try:
            connection.execute(
                """CREATE TABLE IF NOT EXISTS schema_migrations (
                     version text PRIMARY KEY,
                     checksum text NOT NULL,
                     applied_at timestamptz NOT NULL DEFAULT now()
                   )"""
            )
            for path in migrations:
                sql = path.read_text(encoding="utf-8")
                checksum = hashlib.sha256(sql.encode("utf-8")).hexdigest()
                applied = connection.execute(
                    "SELECT checksum FROM schema_migrations WHERE version = %s",
                    (path.name,),
                ).fetchone()
                if applied:
                    if applied[0] != checksum:
                        raise RuntimeError(f"Applied migration checksum changed: {path.name}")
                    print(f"Skipping {path.name} (already applied)", flush=True)
                    continue

                print(f"Applying {path.name}", flush=True)
                connection.execute(sql)
                connection.execute(
                    "INSERT INTO schema_migrations (version, checksum) VALUES (%s, %s)",
                    (path.name, checksum),
                )
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.execute("SELECT pg_advisory_unlock(%s)", (MIGRATION_LOCK_ID,))


if __name__ == "__main__":
    main()
