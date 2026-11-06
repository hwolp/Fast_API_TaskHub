"""Run with: python -m unittest discover -s tests -v."""

import os
from contextlib import closing
from pathlib import Path
import sqlite3
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest


ROOT = Path(__file__).resolve().parents[1]
TABLES = {
    "users", "workspaces", "workspace_members", "projects",
    "tasks", "labels", "task_labels", "comments",
}


class MigrationTests(unittest.TestCase):
    def run_alembic(self, url, *args):
        result = subprocess.run(
            [sys.executable, "-m", "alembic", *args],
            cwd=ROOT,
            env={**os.environ, "DATABASE_URL": url},
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        return result.stdout

    def test_upgrade_preserves_data_and_downgrade_rebuilds_schema(self):
        with TemporaryDirectory() as directory:
            database = Path(directory) / "migration.db"
            url = f"sqlite+aiosqlite:///{database.as_posix()}"
            self.run_alembic(url, "upgrade", "head")
            with closing(sqlite3.connect(database)) as connection, connection:
                tables = {
                    row[0] for row in connection.execute(
                        "SELECT name FROM sqlite_master WHERE type = 'table'"
                    )
                }
                self.assertEqual(tables, TABLES | {"alembic_version"})
                self.assertEqual(
                    connection.execute("SELECT version_num FROM alembic_version").fetchone(),
                    ("0001",),
                )
                connection.execute(
                    "INSERT INTO users "
                    "(email, full_name, hashed_password, role, is_active, created_at) "
                    "VALUES (?, ?, ?, ?, ?, ?)",
                    ("migration@example.com", "Migration", "test", "MEMBER", 1,
                     "2026-01-01 00:00:00"),
                )
            self.run_alembic(url, "check")
            self.run_alembic(url, "upgrade", "head")
            with closing(sqlite3.connect(database)) as connection, connection:
                self.assertEqual(connection.execute("SELECT count(*) FROM users").fetchone(), (1,))
            self.run_alembic(url, "downgrade", "base")
            with closing(sqlite3.connect(database)) as connection, connection:
                tables = {
                    row[0] for row in connection.execute(
                        "SELECT name FROM sqlite_master WHERE type = 'table'"
                    )
                }
                self.assertEqual(tables, {"alembic_version"})
                self.assertEqual(connection.execute("SELECT * FROM alembic_version").fetchall(), [])
            self.run_alembic(url, "upgrade", "head")
            self.run_alembic(url, "check")

    def test_mysql_offline_sql_handles_percent_encoded_password(self):
        url = "mysql+aiomysql://test:encoded%25password@localhost/taskhub_test"
        sql = self.run_alembic(url, "upgrade", "head", "--sql")
        for table in TABLES:
            self.assertIn(f"CREATE TABLE {table}", sql)
        self.assertIn("INSERT INTO alembic_version", sql)
        rollback_sql = self.run_alembic(url, "downgrade", "0001:base", "--sql")
        for table in TABLES:
            self.assertIn(f"DROP TABLE {table}", rollback_sql)


if __name__ == "__main__":
    unittest.main()
