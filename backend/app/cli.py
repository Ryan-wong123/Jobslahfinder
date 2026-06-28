from __future__ import annotations

import argparse
import getpass
import sys

from sqlalchemy.exc import SQLAlchemyError

from app.core.database import SessionLocal
from app.services.admin_bootstrap import InitialAdminCreationError, create_initial_admin

MIGRATION_HELP = (
    "Database is not ready. Apply migrations first with: "
    "docker compose run --rm backend alembic upgrade head"
)


def prompt_password() -> str:
    password = getpass.getpass("Initial admin password: ")
    confirmation = getpass.getpass("Confirm initial admin password: ")
    if password != confirmation:
        raise InitialAdminCreationError("Passwords do not match.")
    return password


def create_initial_admin_command(args: argparse.Namespace) -> int:
    password = prompt_password()
    with SessionLocal() as db:
        user = create_initial_admin(db, email=args.email, password=password)
    print(f"Initial admin created for {user.email}.")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Operational commands for the secure job platform.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    create_admin = subparsers.add_parser(
        "create-initial-admin",
        description="Create the first admin account. Refuses to run after an admin exists.",
    )
    create_admin.add_argument("--email", required=True, help="Email address for the initial admin.")
    create_admin.set_defaults(func=create_initial_admin_command)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except (InitialAdminCreationError, ValueError) as exc:
        print(f"Unable to create initial admin: {exc}", file=sys.stderr)
        return 1
    except SQLAlchemyError:
        print(f"Unable to create initial admin: {MIGRATION_HELP}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
