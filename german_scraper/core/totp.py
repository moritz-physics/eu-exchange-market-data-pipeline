"""TOTP (RFC 6238) helper for unattended 2FA flows.

The original ICE scrapers blocked on ``input()`` for a 2FA code,
which made unattended cron / k8s deploys impossible. If a TOTP secret
is provisioned (most ICE accounts can opt into authenticator-app TOTP
in their security settings), we generate the code from
``ICE_TOTP_SECRET`` instead of prompting.

Falls back to ``input()`` only when no TOTP secret is configured AND
the process has a real stdin attached. In a non-interactive
environment the fallback raises so the scraper fails fast rather than
hanging.
"""
from __future__ import annotations

import os
import sys

from german_scraper.core.logging_config import get_logger

logger = get_logger(__name__)


def get_totp_code(env_var: str, *, prompt_label: str) -> str:
    """Return a 6-digit TOTP code.

    Args:
        env_var: Env var name holding the base-32 TOTP secret.
        prompt_label: Shown to the user only when falling back to input().

    Raises:
        RuntimeError: If neither a secret nor an interactive stdin is available.
    """
    secret = os.environ.get(env_var)
    if secret:
        try:
            import pyotp
        except ImportError as exc:
            raise RuntimeError(
                f"{env_var} is set but pyotp is not installed; "
                "add 'pyotp>=2.9.0' to dependencies"
            ) from exc
        code = pyotp.TOTP(secret.replace(" ", "")).now()
        logger.info("Generated TOTP via %s (no user prompt)", env_var)
        return code

    if not sys.stdin or not sys.stdin.isatty():
        raise RuntimeError(
            f"No {env_var} configured and stdin is not a TTY — "
            "cannot prompt for {prompt_label}. Provision a TOTP secret "
            "or run interactively."
        )
    return input(f"\nPlease enter your {prompt_label} 2FA code: ").strip()


__all__ = ["get_totp_code"]
