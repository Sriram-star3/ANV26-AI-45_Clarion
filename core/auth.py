"""Lightweight FastAPI security dependencies for Clarion Phase 4.

Provides role verification and SRE lead approval guardrails.
"""

from __future__ import annotations

from typing import Optional
from fastapi import Depends, Header, HTTPException, status


def verify_sre_role(
    x_clarion_role: Optional[str] = Header(None, alias="x-clarion-role"),
    authorization: Optional[str] = Header(None, alias="authorization"),
) -> dict:
    """Verify operator role from request headers."""
    role_header = str(x_clarion_role) if isinstance(x_clarion_role, str) else None
    auth_header = str(authorization) if isinstance(authorization, str) else None

    is_sre = (role_header == "sre-lead") or (
        auth_header is not None and "bearer" in auth_header.lower()
    )
    if is_sre:
        return {
            "user": "sre-operator",
            "role": "sre-lead",
            "can_approve_remediation": True,
        }
    return {
        "user": "anonymous",
        "role": "viewer",
        "can_approve_remediation": False,
    }


def require_sre_lead(operator: dict = Depends(verify_sre_role)) -> dict:
    """Guardrail dependency requiring elevated SRE Lead approval."""
    if not operator.get("can_approve_remediation", False):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="HUMAN APPROVAL GUARDRAIL: Elevated SRE Lead role required to execute remediation.",
        )
    return operator
