"""Fail fast when the configured PostgreSQL port is not the project's Docker server.

The lab runs PostgreSQL in Docker on host port 5433 by default so it can coexist
with a native PostgreSQL install that already owns 5432. The app, the ingestion
CLI, the reconciler, Alembic and Docker Compose all read ``POSTGRES_PORT``; if
something else occupies that port, refuse to start rather than silently write to
the wrong database.
"""

import asyncio
import socket
import sys

import asyncpg  # type: ignore[import-untyped]

from app.core.config import Settings, get_settings

DOCKER_DATA_DIR = "/var/lib/postgresql"


def _port_is_open(host: str, port: int) -> bool:
    try:
        infos = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    except socket.gaierror:
        return False

    for family, socktype, proto, _, sockaddr in infos:
        sock = socket.socket(family, socktype, proto)
        sock.settimeout(0.5)
        try:
            if sock.connect_ex(sockaddr) == 0:
                return True
        except OSError:
            continue
        finally:
            sock.close()
    return False


async def _inspect_listener(host: str, port: int, settings: Settings) -> tuple[str, str]:
    """Return (kind, detail) where kind is free/docker/other/unknown."""
    if not _port_is_open(host, port):
        return ("free", "")

    try:
        conn = await asyncpg.connect(
            host=host,
            port=port,
            user=settings.POSTGRES_USER,
            password=settings.POSTGRES_PASSWORD,
            database=settings.POSTGRES_DB,
            timeout=3,
        )
        try:
            data_dir = await conn.fetchval("select current_setting('data_directory')")
        finally:
            await conn.close()
    except Exception as exc:  # noqa: BLE001 - report the reason, do not hide it
        return ("unknown", f"{type(exc).__name__}: {exc}")

    if DOCKER_DATA_DIR in str(data_dir):
        return ("docker", str(data_dir))
    return ("other", str(data_dir))


def _targets(host: str) -> list[str]:
    if host in {"localhost", "127.0.0.1", "::1"}:
        return ["127.0.0.1", "::1"]
    return [host]


async def main() -> int:
    settings = get_settings()
    port = settings.POSTGRES_PORT
    print(f"Checking PostgreSQL port {port} for a non-Docker server...")

    failures: list[str] = []
    for host in _targets(settings.POSTGRES_HOST):
        kind, detail = await _inspect_listener(host, port, settings)
        label = f"{host}:{port}"
        if kind == "free":
            print(f"  {label} -> free")
        elif kind == "docker":
            print(f"  {label} -> Docker Postgres ({detail})")
        elif kind == "other":
            print(f"  {label} -> NON-DOCKER PostgreSQL ({detail})")
            failures.append(f"{label} is served by {detail}")
        else:
            print(f"  {label} -> unknown listener ({detail})")
            failures.append(f"{label} is already in use ({detail})")

    if failures:
        print()
        print("ERROR: refusing to start the Docker stack.")
        for failure in failures:
            print(f"  - {failure}")
        print()
        print(f"Port {port} must be served by the project's Docker PostgreSQL.")
        print("Stop whatever owns it, or choose a free POSTGRES_PORT in .env")
        print("(it must match infra/docker-compose.yml and .env.example).")
        print()
        print("If it is a native PostgreSQL service, on Windows run in an elevated PowerShell:")
        print("  Get-Service *postgres*")
        print("  Stop-Service <name>")
        print("On macOS: brew services stop postgresql@17")
        print("On Linux: sudo systemctl stop postgresql")
        print()
        print("Then re-run: make up")
        return 1

    print(f"OK: no conflicting PostgreSQL server on {port}.")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
