"""Persist document actions in the same transaction as their changes."""

from typing import Any
from uuid import UUID

from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit_log import AuditLog


def record_audit(session: AsyncSession, request: Request, action: str,
                 document_id: UUID | None, details: dict[str, Any] | None = None) -> None:
    session.add(AuditLog(
        actor_id=request.state.api_key,
        action=action,
        document_id=document_id,
        details=details,
        ip=request.client.host if request.client else None,
    ))
