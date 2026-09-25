#!/usr/bin/env python3
"""
Accounts from the server, for when the console cannot help: the only
administrator forgot the password, or every administrator is disabled.

    docker compose exec manager python tools/user.py list
    docker compose exec manager python tools/user.py reset admin
    docker compose exec manager python tools/user.py reset admin --password 'a long passphrase'
    docker compose exec manager python tools/user.py enable admin
    docker compose exec manager python tools/user.py promote alice

`reset` without --password prints a generated one. Whatever the password,
the holder must change it at next sign-in, and every open session of the
account ends. Runs inside the container: it reads DATABASE_URL from there.
"""

import argparse
import os
import secrets
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import auth    # noqa: E402
import users   # noqa: E402


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("list")
    reset = sub.add_parser("reset")
    reset.add_argument("username")
    reset.add_argument("--password")
    enable = sub.add_parser("enable")
    enable.add_argument("username")
    promote = sub.add_parser("promote")
    promote.add_argument("username")
    args = parser.parse_args()

    auth.ensureBootstrap()
    if args.command == "list":
        for row in users.listUsers():
            flags = ("" if row["enabled"] else " disabled") + (" must-change" if row["must_change_password"] else "")
            print(f"{row['username']:24} {row['role']:9} {row['source']:11}{flags}")
        return
    account = users.getUser(args.username)
    if not account:
        sys.exit(f"no such user: {args.username}")
    if args.command == "reset":
        if account["source"] != "local":
            sys.exit("this account has no local password")
        password = args.password or secrets.token_urlsafe(12)
        problem = auth.passwordProblem(password, account["username"])
        if problem:
            sys.exit(problem)
        users.setPassword(account["username"], auth.hashPassword(password), mustChange=True,
                          audit=("cli", "password.reset", account["username"], {}))
        print(f"password of {account['username']} reset; to be changed at next sign-in")
        if not args.password:
            print(f"temporary password: {password}")
    elif args.command == "enable":
        users.updateAccount(account["username"], enabled=True,
                            audit=("cli", "update", account["username"], {"enabled": True}))
        print(f"{account['username']} enabled")
    elif args.command == "promote":
        users.updateAccount(account["username"], role=auth.ROLE_ADMIN,
                            audit=("cli", "update", account["username"], {"role": auth.ROLE_ADMIN}))
        print(f"{account['username']} is now an administrator")


if __name__ == "__main__":
    main()
