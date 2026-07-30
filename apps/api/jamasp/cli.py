"""Operational entrypoints. Run with `python -m jamasp.cli <command>`."""

import asyncio
import os
import sys

from sqlalchemy import select

from jamasp.db import SessionLocal
from jamasp.models.user import User, UserRole
from jamasp.security.password import hash_password


async def seed_admin() -> int:
    """Create the first admin from env vars. Idempotent, so it is safe in an entrypoint."""
    email = os.environ.get("JAMASP_ADMIN_EMAIL")
    password = os.environ.get("JAMASP_ADMIN_PASSWORD")
    if not email or not password:
        print("JAMASP_ADMIN_EMAIL and JAMASP_ADMIN_PASSWORD must be set", file=sys.stderr)
        return 1

    async with SessionLocal() as session:
        existing = (
            await session.scalars(select(User).where(User.email == email))
        ).one_or_none()
        if existing is not None:
            print(f"admin {email} already exists")
            return 0

        session.add(
            User(email=email, password_hash=hash_password(password), role=UserRole.ADMIN)
        )
        await session.commit()

    print(f"created admin {email}")
    return 0


COMMANDS = {"seed-admin": seed_admin}


def main() -> int:
    if len(sys.argv) < 2 or sys.argv[1] not in COMMANDS:
        print(f"usage: python -m jamasp.cli [{'|'.join(COMMANDS)}]", file=sys.stderr)
        return 2
    return asyncio.run(COMMANDS[sys.argv[1]]())


if __name__ == "__main__":
    raise SystemExit(main())
