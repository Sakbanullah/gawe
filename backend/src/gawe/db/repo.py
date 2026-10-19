"""MySQL connection, schema safety, and versioned migrations.

The application never shares a connection between requests. Each request gets
its own connection; transactions are explicit through ``with connection:``.
A failed migration raises; the server must not start serving in that case.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Iterable

import pymysql
from pymysql.cursors import DictCursor

from ..config import DatabaseConfig

MIGRATIONS_DIR = Path(__file__).with_name("migrations")
TEST_SCHEMA_PREFIX = "gawe_test_"
RESERVED_SCHEMAS = {"mysql", "information_schema", "performance_schema", "sys"}
SCHEMA_RE = re.compile(r"^[A-Za-z0-9_]{1,64}$")


class MigrationError(Exception):
    pass


class SchemaNameError(ValueError):
    """A schema name is not safe for the requested operation."""


def validate_schema_name(name: str, *, for_drop: bool = False) -> str:
    if not SCHEMA_RE.fullmatch(name):
        raise SchemaNameError("schema name must be 1-64 letters, digits, or underscores")
    if name.lower() in RESERVED_SCHEMAS:
        raise SchemaNameError("reserved schema name")
    if for_drop and not name.startswith(TEST_SCHEMA_PREFIX):
        raise SchemaNameError("only test schemas may be dropped")
    return name


def require_test_schema(name: str) -> str:
    """Reject any schema that is not a disposable ``gawe_test_*`` schema."""
    validate_schema_name(name)
    if not name.startswith(TEST_SCHEMA_PREFIX):
        raise SchemaNameError(f"test operations require a {TEST_SCHEMA_PREFIX}* schema")
    return name


class Row(dict):
    """Mapping row that also supports positional access used by legacy code."""

    def __getitem__(self, key: Any) -> Any:
        if isinstance(key, int):
            return list(self.values())[key]
        return super().__getitem__(key)


class Cursor:
    def __init__(self, cursor: Any) -> None:
        self._cursor = cursor

    def fetchone(self) -> Row | None:
        row = self._cursor.fetchone()
        return Row(row) if row is not None else None

    def fetchall(self) -> list[Row]:
        return [Row(row) for row in self._cursor.fetchall()]

    @property
    def rowcount(self) -> int:
        return self._cursor.rowcount

    def close(self) -> None:
        self._cursor.close()


class Connection:
    """Thin DB-API wrapper with ``?`` placeholders and nested transactions."""

    def __init__(self, raw: Any) -> None:
        self._raw = raw
        self._depth = 0

    def execute(self, sql: str, params: Iterable[Any] | None = None) -> Cursor:
        cursor = self._raw.cursor(DictCursor)
        # shortcut: `?` is rewritten to `%s`, so literal `%` in SQL must be
        # escaped as `%%`. Switch to named placeholders if LIKE queries arrive.
        statement = sql.replace("?", "%s")
        if params is None:
            cursor.execute(statement)
        else:
            cursor.execute(statement, tuple(params))
        return Cursor(cursor)

    def __enter__(self) -> "Connection":
        if self._depth == 0:
            self._raw.begin()
        self._depth += 1
        return self

    def __exit__(self, exc_type: Any, exc: Any, traceback: Any) -> None:
        self._depth -= 1
        if self._depth:
            return
        if exc_type is None:
            self._raw.commit()
        else:
            self._raw.rollback()

    def commit(self) -> None:
        self._raw.commit()

    def rollback(self) -> None:
        self._raw.rollback()

    def close(self) -> None:
        self._raw.close()


def _raw_connect(config: DatabaseConfig, *, database: str | None) -> Any:
    return pymysql.connect(
        host=config.host,
        port=config.port,
        user=config.user,
        password=config.resolved_password,
        database=database,
        charset=config.charset,
        autocommit=True,
        cursorclass=DictCursor,
    )


def connect(config: DatabaseConfig) -> Connection:
    validate_schema_name(config.name)
    return Connection(_raw_connect(config, database=config.name))


def create_schema(config: DatabaseConfig) -> None:
    validate_schema_name(config.name)
    raw = _raw_connect(config, database=None)
    try:
        with raw.cursor() as cursor:
            cursor.execute(
                f"CREATE DATABASE `{config.name}` "
                "CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci"
            )
    finally:
        raw.close()


def ensure_schema(config: DatabaseConfig) -> None:
    validate_schema_name(config.name)
    raw = _raw_connect(config, database=None)
    try:
        with raw.cursor() as cursor:
            cursor.execute(
                f"CREATE DATABASE IF NOT EXISTS `{config.name}` "
                "CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci"
            )
    finally:
        raw.close()


def drop_schema(config: DatabaseConfig) -> None:
    """Drop a test schema only. Development schemas are never dropped here."""
    validate_schema_name(config.name, for_drop=True)
    raw = _raw_connect(config, database=None)
    try:
        with raw.cursor() as cursor:
            cursor.execute(f"DROP DATABASE IF EXISTS `{config.name}`")
    finally:
        raw.close()


def applied_versions(connection: Connection) -> list[str]:
    row = connection.execute(
        "SELECT 1 FROM information_schema.tables "
        "WHERE table_schema = DATABASE() AND table_name = 'schema_version'"
    ).fetchone()
    if row is None:
        return []
    rows = connection.execute("SELECT version FROM schema_version ORDER BY version").fetchall()
    return [row["version"] for row in rows]


def _statements(script: str) -> list[str]:
    """Split a SQL script on semicolons outside quotes, dropping -- comments."""
    statements: list[str] = []
    buffer: list[str] = []
    quote: str | None = None
    index = 0
    while index < len(script):
        char = script[index]
        if quote is not None:
            buffer.append(char)
            if char == quote:
                if index + 1 < len(script) and script[index + 1] == quote:
                    buffer.append(script[index + 1])
                    index += 2
                    continue
                quote = None
            index += 1
            continue
        if char in {"'", '"', "`"}:
            quote = char
            buffer.append(char)
            index += 1
            continue
        if char == "-" and script[index:index + 2] == "--":
            newline = script.find("\n", index)
            index = len(script) if newline < 0 else newline + 1
            buffer.append("\n")
            continue
        if char == ";":
            statement = "".join(buffer).strip()
            if statement:
                statements.append(statement)
            buffer = []
            index += 1
            continue
        buffer.append(char)
        index += 1
    statement = "".join(buffer).strip()
    if statement:
        statements.append(statement)
    return statements


def migrate(connection: Connection, migrations_dir: Path = MIGRATIONS_DIR) -> list[str]:
    applied: list[str] = []
    for path in sorted(migrations_dir.glob("*.sql")):
        version = path.stem
        if version in applied_versions(connection):
            continue
        script = path.read_text(encoding="utf-8")
        try:
            for statement in _statements(script):
                connection.execute(statement)
        except pymysql.Error as exc:
            raise MigrationError(f"migration {version} failed") from exc
        connection.execute(
            "INSERT INTO schema_version (version, applied_at) VALUES (%s, %s)",
            (version, _now()),
        )
        applied.append(version)
    return applied


def reset(connection: Connection) -> None:
    """Clear test data while keeping the schema and migration history."""
    tables = connection.execute(
        "SELECT table_name AS name FROM information_schema.tables "
        "WHERE table_schema = DATABASE() AND table_type = 'BASE TABLE'"
    ).fetchall()
    connection.execute("SET FOREIGN_KEY_CHECKS = 0")
    try:
        for table in tables:
            name = table["name"]
            if name != "schema_version":
                connection.execute(f"TRUNCATE TABLE `{name}`")
    finally:
        connection.execute("SET FOREIGN_KEY_CHECKS = 1")


def schema_version(connection: Connection) -> str:
    versions = applied_versions(connection)
    return versions[-1] if versions else "none"


def _now() -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
