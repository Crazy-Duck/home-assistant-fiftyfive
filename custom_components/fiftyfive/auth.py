"""
Authentication helpers for the 50five (EVC-Net) portal.

The 50five / EVC-Net portal now protects the account with e-mail based
two-factor authentication (2FA).  The upstream ``fiftyfive`` PyPI package only
knows how to perform the first (username/password) step, so this module
implements the complete interactive flow that is required to obtain an
authenticated session:

1. ``POST /Login/Login`` with the e-mail and password.  A successful login
   causes the portal to e-mail a one time code to the user and redirect the
   browser to ``/2fa``.
2. ``GET /2fa`` to render the OTP form.  The rendered HTML contains a hidden
   CSRF ``_token`` field that must be echoed back.
3. ``POST /2fa_check`` with the ``_token``, the ``_auth_code`` typed by the
   user and the ``VerifyOtp`` submit field.  On success the portal redirects
   to ``/`` (and then ``/Overview``) and the session is fully authenticated.

The flow was reverse engineered from a HAR capture of a real login.

Because the one time code is delivered out of band (via e-mail) the login has
to be interactive, which is why the Home Assistant config flow drives these
functions across two form steps and stores the resulting session cookies in
the config entry so that regular polling does not need to re-authenticate.
"""

from __future__ import annotations

import re
from enum import StrEnum
from http.cookies import SimpleCookie
from typing import TYPE_CHECKING

from yarl import URL

from fiftyfive import CustomerType, Market

if TYPE_CHECKING:
    from aiohttp import ClientSession

# HTTP status returned by the portal on a successful (redirecting) form post.
_HTTP_FOUND = 302

# The hidden CSRF token can appear with the ``value`` attribute either after or
# before the ``name`` attribute depending on the template, so match both.
_TOKEN_PATTERNS = (
    re.compile(
        r"""name=["']_token["'][^>]*?value=["']([^"']+)["']""",
        re.IGNORECASE,
    ),
    re.compile(
        r"""value=["']([^"']+)["'][^>]*?name=["']_token["']""",
        re.IGNORECASE,
    ),
)


class LoginResult(StrEnum):
    """Outcome of the first (username/password) login step."""

    OK = "ok"
    """Fully logged in, no 2FA required (legacy behaviour)."""

    TWO_FACTOR_REQUIRED = "2fa_required"
    """Credentials accepted, a one time code was e-mailed to the user."""

    INVALID_CREDENTIALS = "invalid_credentials"
    """Username/password (or market/customer type) were rejected."""


def build_base_url(market: Market, customer_type: CustomerType) -> str:
    """
    Build the portal base URL.

    This mirrors the URL construction used by ``fiftyfive.Api`` so that the
    config flow and the runtime client always talk to the same host.
    """
    prefix = "-s" if customer_type == CustomerType.FORMER_SHELL else ""
    return f"https://50five{prefix}{market}.evc-net.com"


async def async_start_login(
    session: ClientSession,
    base_url: str,
    email: str,
    password: str,
) -> LoginResult:
    """
    Perform the username/password step.

    Returns a :class:`LoginResult` describing whether a 2FA code is now
    required, the login already fully succeeded, or the credentials were
    rejected.
    """
    data = {
        "emailField": email,
        "passwordField": password,
        "Login": "Log in",
    }
    async with session.post(
        f"{base_url}/Login/Login", data=data, allow_redirects=False
    ) as response:
        # A non redirect response means the login form was re-rendered with an
        # error, i.e. the credentials were not accepted.
        if response.status != _HTTP_FOUND:
            return LoginResult.INVALID_CREDENTIALS

    # The reliable way to know the resulting session state is to ask the portal
    # where the landing page redirects us to.
    async with session.get(f"{base_url}/", allow_redirects=False) as response:
        location = response.headers.get("Location", "").lower()

    if "2fa" in location:
        return LoginResult.TWO_FACTOR_REQUIRED
    if "login" in location or not location:
        return LoginResult.INVALID_CREDENTIALS
    return LoginResult.OK


async def async_fetch_2fa_token(session: ClientSession, base_url: str) -> str | None:
    """Fetch the ``/2fa`` page and extract the hidden CSRF ``_token``."""
    async with session.get(f"{base_url}/2fa") as response:
        html = await response.text()

    for pattern in _TOKEN_PATTERNS:
        match = pattern.search(html)
        if match:
            return match.group(1)
    return None


async def async_submit_2fa(
    session: ClientSession,
    base_url: str,
    code: str,
    token: str | None = None,
) -> bool:
    """
    Submit the one time code to ``/2fa_check``.

    Returns ``True`` when the code was accepted (the portal redirects away from
    the ``/2fa`` page), ``False`` otherwise.
    """
    if token is None:
        token = await async_fetch_2fa_token(session, base_url)

    data = {
        "_auth_code": code.strip(),
        "VerifyOtp": "Verify",
    }
    if token:
        data["_token"] = token

    async with session.post(
        f"{base_url}/2fa_check", data=data, allow_redirects=False
    ) as response:
        # A valid code redirects (302) back to the portal root.  An invalid
        # code either re-renders the 2FA page (200) or redirects back to it.
        if response.status != _HTTP_FOUND:
            return False
        location = response.headers.get("Location", "").lower()

    return "2fa" not in location


def extract_cookies(session: ClientSession) -> dict[str, str]:
    """
    Extract the current session cookies as a simple ``{name: value}`` dict.

    The config flow uses a dedicated (fresh) client session that only ever
    talks to the portal, so every cookie in the jar belongs to it.
    """
    return {cookie.key: cookie.value for cookie in session.cookie_jar}


def seed_cookies(
    session: ClientSession, base_url: str, cookies: dict[str, str]
) -> None:
    """
    Seed previously stored session cookies into ``session``'s cookie jar.

    This lets the runtime client reuse the already authenticated session
    (obtained during the config flow) so that normal polling does not trigger
    another login -- which would require a fresh, un-obtainable 2FA code.
    """
    if not cookies:
        return

    simple: SimpleCookie = SimpleCookie()
    for name, value in cookies.items():
        simple[name] = value

    session.cookie_jar.update_cookies(simple, response_url=URL(base_url))
