"""Promote (or demote) a user to the admin role.

Roles are deliberately not editable from the UI, so a compromised account
can't escalate itself. Run on the server with DB access:

    python scripts/make_admin.py alice@example.com
    python scripts/make_admin.py alice@example.com --revoke
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from finveritas.auth.db import get_users  # noqa: E402
from finveritas.security import audit  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("email")
    ap.add_argument("--revoke", action="store_true")
    args = ap.parse_args()

    role = "analyst" if args.revoke else "admin"
    user = get_users().find_one_and_update({"email": args.email.lower().strip()}, {"$set": {"role": role}})
    if not user:
        sys.exit(f"No user with email {args.email}")
    audit.log_event("role_changed", email=user["email"], user_id=str(user["_id"]),
                    detail={"from": user.get("role", "analyst"), "to": role, "via": "cli"})
    print(f"{user['email']} is now '{role}'.")


if __name__ == "__main__":
    main()
