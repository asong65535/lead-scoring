"""CLI tool for managing API keys.

Usage:
    poetry run python scripts/manage_keys.py create --label "dev-key"
    poetry run python scripts/manage_keys.py revoke --key <raw-key>
    poetry run python scripts/manage_keys.py list
"""

import argparse
import asyncio
import hashlib
import secrets
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from config.settings import get_settings
from src.models.api_key import APIKey


async def create_key(label: str) -> None:
    settings = get_settings()
    engine = create_async_engine(settings.database.url)
    session_factory = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)

    raw_key = secrets.token_urlsafe(32)
    key_hash = hashlib.sha256(raw_key.encode()).hexdigest()

    async with session_factory() as session:
        api_key = APIKey(key_hash=key_hash, label=label)
        session.add(api_key)
        await session.commit()

    print(f"API key created:")
    print(f"  Label: {label}")
    print(f"  Key:   {raw_key}")
    print(f"  (save this key — it cannot be recovered)")

    await engine.dispose()


async def revoke_key(raw_key: str) -> None:
    settings = get_settings()
    engine = create_async_engine(settings.database.url)
    session_factory = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)

    key_hash = hashlib.sha256(raw_key.encode()).hexdigest()

    async with session_factory() as session:
        result = await session.execute(
            update(APIKey)
            .where(APIKey.key_hash == key_hash)
            .values(is_active=False)
            .returning(APIKey.label)
        )
        row = result.scalar_one_or_none()
        await session.commit()

    if row:
        print(f"Key revoked: {row}")
    else:
        print("Key not found")

    await engine.dispose()


async def list_keys() -> None:
    settings = get_settings()
    engine = create_async_engine(settings.database.url)
    session_factory = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)

    async with session_factory() as session:
        result = await session.execute(
            select(APIKey.label, APIKey.is_active, APIKey.created_at)
            .order_by(APIKey.created_at.desc())
        )
        rows = result.all()

    if not rows:
        print("No API keys found")
        return

    for label, is_active, created_at in rows:
        status = "active" if is_active else "revoked"
        print(f"  [{status}] {label} (created {created_at:%Y-%m-%d})")

    await engine.dispose()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Manage API keys")
    sub = parser.add_subparsers(dest="command", required=True)

    create_p = sub.add_parser("create")
    create_p.add_argument("--label", required=True, help="Human-readable label for the key")

    revoke_p = sub.add_parser("revoke")
    revoke_p.add_argument("--key", required=True, help="Raw API key to revoke")

    sub.add_parser("list")

    args = parser.parse_args()

    if args.command == "create":
        asyncio.run(create_key(args.label))
    elif args.command == "revoke":
        asyncio.run(revoke_key(args.key))
    elif args.command == "list":
        asyncio.run(list_keys())
