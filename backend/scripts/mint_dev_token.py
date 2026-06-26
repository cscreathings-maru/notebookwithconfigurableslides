"""Mint an HS256 dev bearer token for a QA account (requires OIDC_DEV_MODE=true).

The orchestrator's dev mode accepts tokens signed with ORCH_SECRET_KEY whose `sub`
claim maps to a provisioned User's oidc_subject. The QA seed sets each subject to the
user's email, so you pass the email here.

Usage:
    python -m scripts.mint_dev_token --sub author@qa-acme.test
    python -m scripts.mint_dev_token --sub admin@qa-globex.test --ttl 86400

Paste the printed token into the frontend login "Dev token" box, or send it as
`Authorization: Bearer <token>` to the API.
"""

from __future__ import annotations

import argparse
import time

import jwt

from src.core.config import get_settings


def mint(subject: str, ttl_seconds: int) -> str:
    settings = get_settings()
    now = int(time.time())
    claims = {"sub": subject, "iat": now, "exp": now + ttl_seconds}
    return jwt.encode(claims, settings.orch_secret_key, algorithm="HS256")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Mint a dev bearer token.")
    parser.add_argument("--sub", required=True, help="oidc_subject (the account email)")
    parser.add_argument(
        "--ttl", type=int, default=28800, help="Lifetime in seconds (default 8h)"
    )
    args = parser.parse_args(argv)

    settings = get_settings()
    if not settings.oidc_dev_mode:
        print("WARNING: OIDC_DEV_MODE is not true; this token will be rejected.")

    print(mint(args.sub, args.ttl))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
