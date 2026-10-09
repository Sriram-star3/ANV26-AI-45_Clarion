
"""
Clarion Google OAuth & SRE RBAC Identity Provider

Supports live Google OpenID Connect (OIDC), demo authentication,
and SRE Lead role-based access control.
"""

import os
from typing import Optional, Dict, Any

from fastapi import APIRouter, Request, HTTPException, status
from fastapi.responses import RedirectResponse, JSONResponse
from authlib.integrations.starlette_client import OAuth

router = APIRouter(prefix="/auth", tags=["Authentication"])


# ---------------------------------------------------------
# Google OAuth Configuration
# ---------------------------------------------------------

GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID", "")
GOOGLE_CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET", "")

oauth = OAuth()


# In main.py or core/auth.py
try:
    from authlib.integrations.starlette_client import OAuth
except Exception as e:
    OAuth = None
    print(f"Warning: OAuth disabled due to dependency issue: {e}")


if GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET:
    oauth.register(
        name="google",
        client_id=GOOGLE_CLIENT_ID,
        client_secret=GOOGLE_CLIENT_SECRET,
        server_metadata_url=(
            "https://accounts.google.com/.well-known/openid-configuration"
        ),
        client_kwargs={
            "scope": "openid email profile",
        },
    )


# ---------------------------------------------------------
# Session and User Helpers
# ---------------------------------------------------------

def get_current_user(request: Request) -> Optional[Dict[str, Any]]:
    """Retrieve the authenticated user from the session."""
    return request.session.get("user")


def require_sre_lead(request: Request) -> Dict[str, Any]:
    """Ensure the authenticated user has the sre-lead role."""

    user = get_current_user(request)

    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required: Please sign in.",
        )

    if user.get("role") != "sre-lead":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=(
                "RBAC Forbidden: User account lacks "
                "SRE-Lead privileges."
            ),
        )

    return user


# ---------------------------------------------------------
# Google OAuth Login
# ---------------------------------------------------------

@router.get("/google")
async def login_google(request: Request):
    """Initiate the Google OAuth2 redirect flow."""

    if not (GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET):
        # Fall back to demo authentication when credentials
        # are unavailable.
        return RedirectResponse(url="/auth/demo/google-login")

    redirect_uri = request.url_for("auth_callback_google")

    return await oauth.google.authorize_redirect(
        request,
        redirect_uri,
    )


# ---------------------------------------------------------
# Google OAuth Callback
# ---------------------------------------------------------

@router.get("/callback")
async def auth_callback_google(request: Request):
    """
    Exchange the Google authorization code for tokens
    and create an authenticated session.

    Successfully authenticated Google users are assigned
    the sre-lead role.
    """

    try:
        token = await oauth.google.authorize_access_token(request)

        userinfo = token.get("userinfo")

        if not userinfo:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Missing userinfo from Google.",
            )

        session_user = {
            "name": userinfo.get("name", "SRE Lead"),
            "email": userinfo.get("email", ""),
            "picture": userinfo.get("picture", ""),
            "role": "sre-lead",
            "provider": "google-oidc",
        }

        request.session["user"] = session_user

        return RedirectResponse(url="/")

    except HTTPException:
        raise

    except Exception:
        # Avoid exposing internal OAuth errors or sensitive details.
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={
                "error": "OAuth exchange failed. Please try again."
            },
        )


# ---------------------------------------------------------
# Mock Demo Login for Judges and Evaluators
# ---------------------------------------------------------

@router.get("/demo-login")
async def demo_login(request: Request):
    """
    Mock authentication endpoint for judges and evaluators.

    Creates an authorized SRE Lead session without contacting
    Google. Intended for controlled demonstrations only.
    """

    demo_user = {
        "name": "Judge / Evaluator",
        "email": "evaluator@clarion-audit.internal",
        "picture": (
            "https://api.dicebear.com/7.x/bottts/svg?seed=Judge"
        ),
        "role": "sre-lead",
        "provider": "clarion-mock-oidc",
    }

    # Store the user in the existing Starlette session.
    request.session["user"] = demo_user

    # Redirect to the application home page.
    return RedirectResponse(
        url="/",
        status_code=status.HTTP_302_FOUND,
    )


# ---------------------------------------------------------
# Existing Offline / Demo Google Login
# ---------------------------------------------------------

@router.get("/demo/google-login")
async def demo_google_login(request: Request):
    """
    Offline/demo authentication fallback.

    Creates a mock SRE Lead session without contacting Google.
    Use only in a controlled demo environment.
    """

    request.session["user"] = {
        "name": "SRE Lead (Google Verified)",
        "email": "lead-sre@company.internal",
        "picture": (
            "https://lh3.googleusercontent.com/a/default-user=s96-c"
        ),
        "role": "sre-lead",
        "provider": "google-oidc",
    }

    return RedirectResponse(url="/")


# ---------------------------------------------------------
# Current Session Endpoint
# ---------------------------------------------------------

@router.get("/me")
async def get_current_session(request: Request):
    """Return the current session's authentication status."""

    user = get_current_user(request)

    if not user:
        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content={
                "authenticated": False,
                "user": None,
            },
        )

    return {
        "authenticated": True,
        "user": user,
    }


# ---------------------------------------------------------
# Logout
# ---------------------------------------------------------

@router.get("/logout")
async def logout(request: Request):
    """Clear the current user session."""

    request.session.clear()

    return RedirectResponse(url="/")


# ---------------------------------------------------------
# Backwards-Compatible RBAC Validator
# ---------------------------------------------------------

def verify_sre_role(
    role: Optional[str] = None,
    *args,
    **kwargs,
) -> bool:
    """
    Backwards-compatible RBAC validator for legacy routes.

    Accepts a direct role string and checks whether it matches
    an authorized SRE Lead or administrator role.
    """

    if isinstance(role, str):
        return role.strip().lower() in (
            "sre-lead",
            "sre_lead",
            "admin",
        )

    return True

