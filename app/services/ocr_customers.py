"""Customer authentication and atomic monthly request accounting."""

import hashlib
import secrets
from datetime import UTC, datetime
from uuid import UUID

from fastapi import Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.models.customer import Customer, CustomerApiKey, OcrUsage


def current_period() -> str:
    return datetime.now(UTC).strftime("%Y-%m")


def create_key(customer_id: UUID, name: str) -> tuple[CustomerApiKey, str]:
    token = f"ocr_{secrets.token_urlsafe(32)}"
    key = CustomerApiKey(
        customer_id=customer_id,
        name=name,
        key_prefix=token[:12],
        key_hash=hashlib.sha256(token.encode()).hexdigest(),
    )
    return key, token


async def require_customer(
    request: Request, db: AsyncSession = Depends(get_db)
) -> Customer:
    customer = await customer_from_authorization(db, request.headers.get("authorization", ""))
    if customer is None:
        raise HTTPException(401, "Invalid customer API key",
                            headers={"WWW-Authenticate": "Bearer"})
    return customer


async def customer_from_authorization(db: AsyncSession, authorization: str) -> Customer | None:
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token.startswith("ocr_"):
        return None
    digest = hashlib.sha256(token.encode()).hexdigest()
    key = await db.scalar(select(CustomerApiKey).where(
        CustomerApiKey.key_hash == digest, CustomerApiKey.revoked_at.is_(None)
    ))
    customer = await db.get(Customer, key.customer_id) if key else None
    if customer is None or not customer.active:
        return None
    return customer


async def reserve_request(db: AsyncSession, customer: Customer) -> str:
    # Serialize quota changes per customer. The lock is released at commit before OCR runs.
    locked = await db.scalar(select(Customer).where(Customer.id == customer.id).with_for_update())
    if locked is None or not locked.active:
        raise HTTPException(401, "Customer account is inactive")
    period = current_period()
    usage = await db.get(OcrUsage, (customer.id, period))
    if usage is None:
        usage = OcrUsage(customer_id=customer.id, period=period, requests=0)
        db.add(usage)
    if usage.requests >= locked.monthly_request_limit:
        raise HTTPException(429, "Monthly OCR request limit reached")
    usage.requests += 1
    await db.commit()
    return period


async def refund_request(db: AsyncSession, customer: Customer, period: str) -> None:
    await db.scalar(select(Customer).where(Customer.id == customer.id).with_for_update())
    usage = await db.get(OcrUsage, (customer.id, period))
    if usage is not None and usage.requests > 0:
        usage.requests -= 1
        await db.commit()
