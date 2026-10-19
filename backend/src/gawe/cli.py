"""Admin CLI. Not the main UI."""

from __future__ import annotations

import argparse
import json
import platform
import sys
from pathlib import Path

from .config import ConfigError, load_config
from .db import repo
from .security.consent import key_source


def doctor(config_path: Path | str | None = None) -> dict:
    report: dict = {
        "python": platform.python_version(),
        "platform": platform.platform(),
        "config": None,
        "bind_host": None,
        "bind_loopback": None,
        "provider": None,
        "key_source": None,
        "database": None,
        "schema_version": None,
        "frontend_build": None,
        "pdf_engine": None,
        "pdf_decision": "open",
        "errors": [],
    }
    try:
        config = load_config(config_path)
    except ConfigError as exc:
        report["errors"].append(str(exc))
        return report

    report["config"] = str(config.source_path)
    report["bind_host"] = config.server.host
    report["bind_loopback"] = config.server.host in {"127.0.0.1", "::1", "localhost"}
    report["provider"] = config.llm.active_provider
    provider = config.llm.providers.get(config.llm.active_provider)
    report["key_source"] = key_source(provider.api_key_ref if provider else None)
    report["database"] = config.database.describe()
    try:
        repo.ensure_schema(config.database)
        connection = repo.connect(config.database)
        repo.migrate(connection)
        report["schema_version"] = repo.schema_version(connection)
        connection.close()
    except Exception as exc:
        report["errors"].append(f"database: {type(exc).__name__}")
    report["frontend_build"] = "present" if (config.dist_dir / "index.html").is_file() else "missing"
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="gawe")
    parser.add_argument("--config", default=None, help="path to config.toml")
    sub = parser.add_subparsers(dest="command")

    sub.add_parser("doctor", help="report environment without secrets")
    serve = sub.add_parser("serve", help="run the local server")
    serve.add_argument("--host", default=None)
    serve.add_argument("--port", type=int, default=None)

    args = parser.parse_args(argv)
    if args.command == "doctor":
        report = doctor(args.config)
        print(json.dumps(report, indent=2))
        return 0 if not report["errors"] else 1
    if args.command == "serve":
        import uvicorn

        from .api.app import create_app

        try:
            config = load_config(args.config)
        except ConfigError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 1
        if args.host:
            config.server.host = args.host
        if args.port:
            config.server.port = args.port
        if config.server.host not in {"127.0.0.1", "::1", "localhost"}:
            print("error: server must bind to loopback", file=sys.stderr)
            return 1
        uvicorn.run(create_app(config), host=config.server.host, port=config.server.port)
        return 0
    parser.print_help()
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
