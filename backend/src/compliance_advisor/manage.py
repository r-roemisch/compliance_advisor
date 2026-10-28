"""compliance-advisor-accounts: the Operator role (ADR 0006) is granted by whoever runs the
backend, with this command, because registration is open and unverified.

  uv run compliance-advisor-accounts operator grant <email>
  uv run compliance-advisor-accounts operator revoke <email>
  uv run compliance-advisor-accounts operator list
"""

import argparse

from sqlalchemy import create_engine

from .accounts import AccountStore
from .settings import get_settings


def main() -> None:
    parser = argparse.ArgumentParser(description="Manage accounts of the Compliance Advisor.")
    sub = parser.add_subparsers(dest="what", required=True)
    operator = sub.add_parser("operator", help="grant, revoke or list the Operator role")
    operator.add_argument("action", choices=["grant", "revoke", "list"])
    operator.add_argument("email", nargs="?")
    args = parser.parse_args()

    store = AccountStore(create_engine(get_settings().database_url))
    if args.action == "list":
        print("\n".join(store.operators()) or "no operators")
        return
    if not args.email:
        raise SystemExit("an email address is needed")
    if store.set_operator(args.email, args.action == "grant"):
        print(f"{args.action}ed: {args.email.strip().lower()}")
    else:
        raise SystemExit(f"no account with the email {args.email!r}; it must register first")
