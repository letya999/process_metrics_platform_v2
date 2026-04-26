import hmac
import json
import os
import time

import httpx
from fastapi import HTTPException

from app.services.admin_auth import _b64url_decode, _b64url_encode, _sign


def build_google_redirect_url(return_to: str) -> str:
    """
    Build Google OAuth authorization URL.
    - Generate state token: JSON {return_to, iat} signed with HMAC-SHA256
    - Validate return_to starts with ADMIN_UI_URL env var (open-redirect protection).
    - Scopes: openid email profile
    - response_type: code
    - access_type: online
    - URL: https://accounts.google.com/o/oauth2/v2/auth
    - Returns full redirect URL string.
    """
    client_id = os.getenv("GOOGLE_CLIENT_ID")
    redirect_uri = os.getenv("ADMIN_GOOGLE_REDIRECT_URI")
    admin_ui_url = os.getenv("ADMIN_UI_URL", "http://localhost:8501")

    if not client_id or not os.getenv("GOOGLE_CLIENT_SECRET"):
        raise HTTPException(status_code=503, detail="Google OAuth is not configured")

    if not return_to.startswith(admin_ui_url):
        # Fallback to base admin UI URL if return_to is suspicious
        return_to = admin_ui_url

    state_payload = {
        "return_to": return_to,
        "iat": int(time.time()),
    }
    encoded_payload = _b64url_encode(
        json.dumps(state_payload, separators=(",", ":")).encode("utf-8")
    )
    signature = _sign(encoded_payload)
    state = f"{encoded_payload}.{signature}"

    params = {
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": "openid email profile",
        "state": state,
        "access_type": "online",
    }

    query_params = httpx.QueryParams(params)
    return f"https://accounts.google.com/o/oauth2/v2/auth?{query_params}"


def verify_state_and_get_return_to(state: str) -> str | None:
    """
    Verify state token signature and TTL (max 10 minutes).
    Returns return_to URL if valid, None if invalid/expired.
    """
    if not state or "." not in state:
        return None

    parts = state.split(".")
    if len(parts) != 2:
        return None

    encoded_payload, signature = parts
    try:
        expected_signature = _sign(encoded_payload)
    except RuntimeError:
        return None

    if not hmac.compare_digest(signature, expected_signature):
        return None

    try:
        payload = json.loads(_b64url_decode(encoded_payload))
        return_to = payload.get("return_to")
        iat = payload.get("iat", 0)

        # 10 minute TTL
        if time.time() - iat > 600:
            return None

        return return_to
    except (ValueError, json.JSONDecodeError):
        return None


async def exchange_code_for_email(code: str) -> str | None:
    """
    Exchange authorization code for tokens via Google token endpoint.
    - POST to https://oauth2.googleapis.com/token
    - Extract id_token from response
    - Verify id_token by calling GET https://oauth2.googleapis.com/tokeninfo?id_token=<token>
    - Return email claim from tokeninfo response.
    - Use httpx.AsyncClient.
    - Return None on any error (network, bad token, missing email).
    """
    client_id = os.getenv("GOOGLE_CLIENT_ID")
    client_secret = os.getenv("GOOGLE_CLIENT_SECRET")
    redirect_uri = os.getenv("ADMIN_GOOGLE_REDIRECT_URI")

    if not client_id or not client_secret:
        return None

    async with httpx.AsyncClient() as client:
        try:
            # 1. Exchange code for token
            token_resp = await client.post(
                "https://oauth2.googleapis.com/token",
                data={
                    "code": code,
                    "client_id": client_id,
                    "client_secret": client_secret,
                    "redirect_uri": redirect_uri,
                    "grant_type": "authorization_code",
                },
                timeout=10.0,
            )
            if token_resp.status_code != 200:
                return None

            id_token = token_resp.json().get("id_token")
            if not id_token:
                return None

            # 2. Verify id_token
            info_resp = await client.get(
                "https://oauth2.googleapis.com/tokeninfo",
                params={"id_token": id_token},
                timeout=10.0,
            )
            if info_resp.status_code != 200:
                return None

            data = info_resp.json()
            email = data.get("email")
            email_verified = data.get("email_verified")

            # Google returns email_verified as "true" (string) or true (bool) sometimes
            if email and (email_verified is True or email_verified == "true"):
                return email

            return None
        except Exception:
            return None
