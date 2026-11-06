#!/usr/bin/env python3
"""
K13 AI Hub - Automated Daily Backup Service (Qdrant + PostgreSQL)
=================================================================
Backs up:
  1. Qdrant vector collections (via Qdrant Snapshot REST API -> streamed to disk)
  2. PostgreSQL database (via pg_dump if installed, or pure-Python psycopg2 streaming SQL dump)

Destination:
  Reads BACKUP_PATH from .env, defaulting to: C:\\fetch42\\space
  - <BACKUP_PATH>\\qdrant\\<collection>_<YYYYMMDD_HHMMSS>.snapshot
  - <BACKUP_PATH>\\postgres\\<dbname>_<YYYYMMDD_HHMMSS>.sql.gz
  - <BACKUP_PATH>\\latest_backup.json

Schedule:
  - Runs at 04:00 AM local time every day in daemon mode (default)
  - Pass --once to run an immediate backup and exit
"""

import os
import sys
import gzip
import json
import time
import shutil
import logging
import datetime
import argparse
import subprocess
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple

import requests
import psycopg2
import psycopg2.extras

# Force UTF-8 output on Windows consoles
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] k13-backup: %(message)s",
)
logger = logging.getLogger("k13-backup")

BASE_DIR = Path(__file__).resolve().parent.parent
ENV_FILE = BASE_DIR / ".env"
DEFAULT_BACKUP_PATH = r"C:\fetch42\space"


def load_dotenv_vars() -> None:
    """Reads .env from project root and updates os.environ so runtime edits take effect."""
    candidates = [ENV_FILE, Path.cwd() / ".env"]
    for env_path in candidates:
        if env_path.is_file():
            try:
                for raw_line in env_path.read_text(encoding="utf-8", errors="ignore").splitlines():
                    line = raw_line.strip()
                    if not line or line.startswith("#") or "=" not in line:
                        continue
                    k, v = line.split("=", 1)
                    k = k.strip()
                    v = v.strip()
                    if (v.startswith('"') and v.endswith('"')) or (v.startswith("'") and v.endswith("'")):
                        v = v[1:-1]
                    if k and v:
                        os.environ[k] = v
            except Exception as e:
                logger.warning(f"Could not parse {env_path}: {e}")
            break


def get_env_opt(*keys: str, default: str = "") -> str:
    for k in keys:
        v = (os.environ.get(k) or "").strip()
        if v:
            return v
    return default


def get_backup_config() -> Dict[str, Any]:
    load_dotenv_vars()
    backup_path = get_env_opt("BACKUP_PATH", default=DEFAULT_BACKUP_PATH)

    qdrant_host = get_env_opt("QDRANT_HOST", default="127.0.0.1")
    qdrant_port = get_env_opt("QDRANT_PORT", default="6333")
    qdrant_url = get_env_opt("QDRANT_URL", default=f"http://{qdrant_host}:{qdrant_port}").rstrip("/")
    qdrant_collection = get_env_opt("QDRANT_COLLECTION", default="rss_articles")

    pg_host = get_env_opt("PG_HOST", "POSTGRES_HOST", "NAS_HOST", "NAS_IP", "DB_HOST", default="127.0.0.1")
    pg_port = int(get_env_opt("PG_PORT", "POSTGRES_PORT", default="5432"))
    pg_user = get_env_opt("PG_USER", "POSTGRES_USER", "DB_USER", default="freshrss")
    pg_pass = get_env_opt(
        "PG_PASS",
        "PG_PASSWORD",
        "PGPASSWORD",
        "POSTGRES_PASSWORD",
        "POSTGRES_PASS",
        "DB_PASS",
        "DB_PASSWORD",
        "FRESHRSS_DB_PASS",
        default="",
    )
    pg_dbname = get_env_opt("PG_DB", "PG_DBNAME", "POSTGRES_DB", default="fetch42")
    schedule_time = get_env_opt("BACKUP_SCHEDULE_TIME", default="04:00")

    return {
        "backup_path": Path(backup_path),
        "qdrant_url": qdrant_url,
        "qdrant_collection": qdrant_collection,
        "pg_host": pg_host,
        "pg_port": pg_port,
        "pg_user": pg_user,
        "pg_pass": pg_pass,
        "pg_dbname": pg_dbname,
        "schedule_time": schedule_time,
    }


# ==============================================================================
# 1. Qdrant Backup (Snapshot API -> Stream to BACKUP_PATH\qdrant)
# ==============================================================================

def backup_qdrant(cfg: Dict[str, Any], timestamp_str: str) -> List[Dict[str, Any]]:
    qdrant_url: str = cfg["qdrant_url"]
    qdrant_backup_dir: Path = cfg["backup_path"] / "qdrant"
    qdrant_backup_dir.mkdir(parents=True, exist_ok=True)

    results: List[Dict[str, Any]] = []
    collections: List[str] = []

    try:
        r = requests.get(f"{qdrant_url}/collections", timeout=15)
        r.raise_for_status()
        data = r.json()
        cols_raw = (data.get("result") or {}).get("collections") or []
        for c in cols_raw:
            name = c.get("name")
            if name:
                collections.append(name)
    except Exception as e:
        logger.error(f"Failed to list Qdrant collections at {qdrant_url}: {e}")
        return results

    if not collections:
        logger.warning(f"No collections found in Qdrant at {qdrant_url}.")
        return results

    for col_name in collections:
        t0 = time.perf_counter()
        logger.info(f"[Qdrant] Creating snapshot for collection '{col_name}'...")
        snapshot_name = None
        try:
            snap_res = requests.post(
                f"{qdrant_url}/collections/{col_name}/snapshots?wait=true",
                timeout=300,
            )
            if snap_res.status_code not in (200, 201):
                logger.error(
                    f"[Qdrant] Failed creating snapshot for '{col_name}': "
                    f"HTTP {snap_res.status_code} {snap_res.text[:200]}"
                )
                continue

            snap_info = (snap_res.json().get("result") or {})
            snapshot_name = snap_info.get("name")
            if not snapshot_name:
                logger.error(f"[Qdrant] Snapshot response for '{col_name}' missing name: {snap_res.text[:200]}")
                continue

            dest_file = qdrant_backup_dir / f"{col_name}_{timestamp_str}.snapshot"
            download_url = f"{qdrant_url}/collections/{col_name}/snapshots/{snapshot_name}"
            logger.info(f"[Qdrant] Downloading snapshot '{snapshot_name}' -> {dest_file} ...")

            with requests.get(download_url, stream=True, timeout=600) as dl:
                dl.raise_for_status()
                with open(dest_file, "wb") as f_out:
                    for chunk in dl.iter_content(chunk_size=1024 * 1024):
                        if chunk:
                            f_out.write(chunk)

            size_bytes = dest_file.stat().st_size
            elapsed = round(time.perf_counter() - t0, 2)
            logger.info(
                f"[✓] [Qdrant] Backed up '{col_name}' to {dest_file} "
                f"({size_bytes / (1024 * 1024):.2f} MB in {elapsed}s)"
            )
            results.append(
                {
                    "collection": col_name,
                    "file": str(dest_file),
                    "size_bytes": size_bytes,
                    "duration_sec": elapsed,
                    "status": "ok",
                }
            )
        except Exception as e:
            logger.error(f"[Qdrant] Error backing up collection '{col_name}': {e}")
            results.append({"collection": col_name, "status": "error", "error": str(e)})
        finally:
            # Remove temporary snapshot from Qdrant's internal storage after copying to BACKUP_PATH
            if snapshot_name:
                try:
                    requests.delete(
                        f"{qdrant_url}/collections/{col_name}/snapshots/{snapshot_name}?wait=true",
                        timeout=30,
                    )
                except Exception:
                    pass

    return results


# ==============================================================================
# 2. PostgreSQL Backup (pg_dump or Pure-Python Streaming SQL.GZ)
# ==============================================================================

def _sql_literal(val: Any) -> str:
    """Safely formats a Python value as a PostgreSQL SQL literal for pure-Python dumps."""
    if val is None:
        return "NULL"
    if isinstance(val, bool):
        return "TRUE" if val else "FALSE"
    if isinstance(val, (int, float)):
        return str(val)
    if isinstance(val, (datetime.datetime, datetime.date)):
        return "'" + val.isoformat().replace("'", "''") + "'"
    if isinstance(val, (dict, list)):
        s = json.dumps(val, ensure_ascii=False).replace("'", "''")
        return f"'{s}'"
    if isinstance(val, (bytes, bytearray, memoryview)):
        hex_str = bytes(val).hex()
        return f"'\\x{hex_str}'"
    s = str(val).replace("'", "''")
    return f"'{s}'"


def _backup_postgres_pure_python(cfg: Dict[str, Any], dest_file: Path) -> Tuple[int, int]:
    """
    Streams all user tables in PostgreSQL to a compressed .sql.gz file using psycopg2.
    Returns (tables_count, total_rows_exported).
    """
    conn = psycopg2.connect(
        host=cfg["pg_host"],
        port=cfg["pg_port"],
        user=cfg["pg_user"],
        password=cfg["pg_pass"],
        dbname=cfg["pg_dbname"],
        connect_timeout=15,
    )
    total_rows = 0
    tables_exported = 0

    try:
        with conn.cursor() as meta_cur:
            meta_cur.execute(
                """
                SELECT table_schema, table_name
                FROM information_schema.tables
                WHERE table_type = 'BASE TABLE'
                  AND table_schema NOT IN ('pg_catalog', 'information_schema')
                ORDER BY table_schema, table_name;
                """
            )
            tables = meta_cur.fetchall()

        with gzip.open(dest_file, "wt", encoding="utf-8") as gz:
            gz.write("-- ============================================================================\n")
            gz.write(f"-- K13 AI Hub - PostgreSQL Full Database Backup ({cfg['pg_dbname']})\n")
            gz.write(f"-- Generated at: {datetime.datetime.now(datetime.timezone.utc).isoformat()}\n")
            gz.write(f"-- Source: {cfg['pg_host']}:{cfg['pg_port']}/{cfg['pg_dbname']}\n")
            gz.write("-- ============================================================================\n\n")
            gz.write("SET client_encoding = 'UTF8';\n")
            gz.write("SET standard_conforming_strings = on;\n\n")

            for schema_name, table_name in tables:
                qualified = f'"{schema_name}"."{table_name}"'
                with conn.cursor() as col_cur:
                    col_cur.execute(
                        """
                        SELECT column_name, data_type, is_nullable, column_default
                        FROM information_schema.columns
                        WHERE table_schema = %s AND table_name = %s
                        ORDER BY ordinal_position;
                        """,
                        (schema_name, table_name),
                    )
                    cols_meta = col_cur.fetchall()

                if not cols_meta:
                    continue

                col_names = [c[0] for c in cols_meta]
                col_names_quoted = ", ".join(f'"{c}"' for c in col_names)

                # Write CREATE TABLE IF NOT EXISTS DDL header
                col_defs = []
                for c_name, c_type, c_null, c_def in cols_meta:
                    line_def = f'    "{c_name}" {c_type}'
                    if c_def is not None:
                        line_def += f" DEFAULT {c_def}"
                    if c_null == "NO":
                        line_def += " NOT NULL"
                    col_defs.append(line_def)

                gz.write(f"-- Table: {qualified}\n")
                gz.write(f'CREATE SCHEMA IF NOT EXISTS "{schema_name}";\n')
                gz.write(f"CREATE TABLE IF NOT EXISTS {qualified} (\n")
                gz.write(",\n".join(col_defs))
                gz.write("\n);\n\n")

                # Stream table rows using a named server-side cursor to keep memory flat
                table_rows = 0
                cursor_name = f"k13_bkp_{table_name}_{int(time.time())}"
                with conn.cursor(name=cursor_name) as data_cur:
                    data_cur.itersize = 500
                    data_cur.execute(f"SELECT {col_names_quoted} FROM {qualified};")
                    while True:
                        rows = data_cur.fetchmany(200)
                        if not rows:
                            break
                        values_sql_list = []
                        for row in rows:
                            row_lits = ", ".join(_sql_literal(v) for v in row)
                            values_sql_list.append(f"({row_lits})")
                        gz.write(
                            f"INSERT INTO {qualified} ({col_names_quoted}) VALUES\n"
                            + ",\n".join(values_sql_list)
                            + "\nON CONFLICT DO NOTHING;\n"
                        )
                        table_rows += len(rows)
                        total_rows += len(rows)

                gz.write(f"\n-- Completed {qualified}: {table_rows:,} rows\n\n")
                tables_exported += 1
                logger.info(f"[PostgreSQL] Exported {table_rows:,} rows from {qualified}")
    finally:
        conn.close()

    return tables_exported, total_rows


def backup_postgres(cfg: Dict[str, Any], timestamp_str: str) -> Dict[str, Any]:
    pg_backup_dir: Path = cfg["backup_path"] / "postgres"
    pg_backup_dir.mkdir(parents=True, exist_ok=True)

    db_name = cfg["pg_dbname"]
    dest_file = pg_backup_dir / f"{db_name}_{timestamp_str}.sql.gz"
    t0 = time.perf_counter()

    # Check if native pg_dump is available on PATH
    pg_dump_bin = shutil.which("pg_dump")
    if pg_dump_bin:
        logger.info(
            f"[PostgreSQL] Running pg_dump on {cfg['pg_host']}:{cfg['pg_port']}/{db_name} -> {dest_file} ..."
        )
        env = os.environ.copy()
        if cfg["pg_pass"]:
            env["PGPASSWORD"] = cfg["pg_pass"]
        try:
            with gzip.open(dest_file, "wb") as gz_out:
                proc = subprocess.Popen(
                    [
                        pg_dump_bin,
                        "-h",
                        str(cfg["pg_host"]),
                        "-p",
                        str(cfg["pg_port"]),
                        "-U",
                        str(cfg["pg_user"]),
                        "-d",
                        str(db_name),
                        "--no-owner",
                        "--no-privileges",
                    ],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    env=env,
                )
                assert proc.stdout is not None
                for chunk in iter(lambda: proc.stdout.read(1024 * 256), b""):
                    gz_out.write(chunk)
                _, stderr_bytes = proc.communicate()
                if proc.returncode == 0 and dest_file.stat().st_size > 0:
                    size_bytes = dest_file.stat().st_size
                    elapsed = round(time.perf_counter() - t0, 2)
                    logger.info(
                        f"[✓] [PostgreSQL] pg_dump completed: {dest_file} "
                        f"({size_bytes / (1024 * 1024):.2f} MB in {elapsed}s)"
                    )
                    return {
                        "database": db_name,
                        "method": "pg_dump",
                        "file": str(dest_file),
                        "size_bytes": size_bytes,
                        "duration_sec": elapsed,
                        "status": "ok",
                    }
                else:
                    err_msg = stderr_bytes.decode("utf-8", errors="ignore").strip()
                    logger.warning(f"[PostgreSQL] pg_dump exited with {proc.returncode} ({err_msg}); falling back to Python psycopg2 dump...")
        except Exception as e:
            logger.warning(f"[PostgreSQL] pg_dump failed ({e}); falling back to Python psycopg2 dump...")

    # Pure-Python psycopg2 streaming SQL.GZ backup
    logger.info(
        f"[PostgreSQL] Streaming full database backup from {cfg['pg_host']}:{cfg['pg_port']}/{db_name} "
        f"via Python psycopg2 -> {dest_file} ..."
    )
    try:
        tables_count, rows_count = _backup_postgres_pure_python(cfg, dest_file)
        size_bytes = dest_file.stat().st_size
        elapsed = round(time.perf_counter() - t0, 2)
        logger.info(
            f"[✓] [PostgreSQL] Backed up {tables_count} table(s), {rows_count:,} total rows to {dest_file} "
            f"({size_bytes / (1024 * 1024):.2f} MB in {elapsed}s)"
        )
        return {
            "database": db_name,
            "method": "psycopg2-stream",
            "tables": tables_count,
            "rows": rows_count,
            "file": str(dest_file),
            "size_bytes": size_bytes,
            "duration_sec": elapsed,
            "status": "ok",
        }
    except Exception as e:
        logger.error(f"[PostgreSQL] Backup failed for {db_name}: {e}")
        return {"database": db_name, "status": "error", "error": str(e)}


# ==============================================================================
# 3. Full Backup Execution & Daily 04:00 AM Scheduler
# ==============================================================================

def run_full_backup() -> Dict[str, Any]:
    cfg = get_backup_config()
    backup_root: Path = cfg["backup_path"]
    backup_root.mkdir(parents=True, exist_ok=True)

    now = datetime.datetime.now()
    timestamp_str = now.strftime("%Y%m%d_%H%M%S")

    logger.info("=" * 70)
    logger.info(f"Starting K13 Full Backup (Qdrant + PostgreSQL) -> {backup_root}")
    logger.info("=" * 70)

    t_start = time.perf_counter()
    qdrant_res = backup_qdrant(cfg, timestamp_str)
    pg_res = backup_postgres(cfg, timestamp_str)
    total_duration = round(time.perf_counter() - t_start, 2)

    manifest = {
        "timestamp": now.isoformat(),
        "backup_path": str(backup_root),
        "duration_sec": total_duration,
        "qdrant": qdrant_res,
        "postgres": pg_res,
    }

    latest_manifest_path = backup_root / "latest_backup.json"
    try:
        latest_manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    except Exception as e:
        logger.warning(f"Could not write {latest_manifest_path}: {e}")

    logger.info("=" * 70)
    logger.info(f"[✓] K13 Backup Finished in {total_duration}s. Stored in: {backup_root}")
    logger.info("=" * 70)
    return manifest


def seconds_until_next_run(target_hm: str = "04:00") -> Tuple[float, datetime.datetime]:
    """Calculates seconds remaining until the next occurrence of HH:MM (default 04:00 AM local time)."""
    try:
        parts = target_hm.strip().split(":")
        target_hour = int(parts[0])
        target_min = int(parts[1]) if len(parts) > 1 else 0
    except Exception:
        target_hour, target_min = 4, 0

    now = datetime.datetime.now()
    next_run = now.replace(hour=target_hour, minute=target_min, second=0, microsecond=0)
    if next_run <= now:
        next_run += datetime.timedelta(days=1)
    diff = (next_run - now).total_seconds()
    return max(1.0, diff), next_run


def main() -> None:
    parser = argparse.ArgumentParser(description="K13 AI Hub - Qdrant & PostgreSQL Daily Backup Service")
    parser.add_argument("--once", action="store_true", help="Run a single immediate backup and exit")
    parser.add_argument("--run-on-start", action="store_true", help="Run an immediate backup before entering the 4:00 AM schedule loop")
    args = parser.parse_args()

    if args.once:
        run_full_backup()
        return

    cfg = get_backup_config()
    logger.info(
        f"[+] K13 Backup Service initialized. Target directory: {cfg['backup_path']} "
        f"(Scheduled daily at {cfg['schedule_time']} local time)"
    )

    if args.run_on_start or get_env_opt("BACKUP_RUN_ON_START").lower() in ("1", "true", "on", "yes"):
        run_full_backup()

    while True:
        cfg = get_backup_config()
        wait_secs, next_dt = seconds_until_next_run(cfg["schedule_time"])
        logger.info(
            f"Next scheduled Qdrant + PostgreSQL backup at: {next_dt.strftime('%Y-%m-%d %H:%M:%S')} "
            f"(in {wait_secs / 3600:.2f} hours) -> {cfg['backup_path']}"
        )

        # Sleep in short chunks so clock adjustments or stop signals are handled cleanly
        while True:
            remaining = (next_dt - datetime.datetime.now()).total_seconds()
            if remaining <= 0:
                break
            time.sleep(min(30.0, max(1.0, remaining)))

        try:
            run_full_backup()
        except Exception as e:
            logger.error(f"Unexpected error during scheduled backup: {e}")

        # Brief pause to ensure we don't trigger twice within the same second
        time.sleep(5)


if __name__ == "__main__":
    main()

