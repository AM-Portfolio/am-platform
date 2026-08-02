from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status

from am_identity.api_key_store import ApiKeyStore
from am_identity.core.database import get_database_pool
from am_identity.deps import get_identity_provider
from am_identity.email.rate_limit import enforce_rate_limit
from am_identity.providers.interface import IIdentityProvider
from am_identity.schemas.api_key import (
    ApiKeyCreateRequest,
    ApiKeyCreateResponse,
    ApiKeyExchangeRequest,
    ApiKeyResponse,
)
from am_identity.schemas.auth import TokenResponse
from am_platform_security import AuthContext, require_auth_context

router = APIRouter(tags=["api-keys"])


def get_api_key_store() -> ApiKeyStore:
    pool = get_database_pool()
    if pool is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="API key storage is not configured",
        )
    return ApiKeyStore(pool)


@router.get("/users/me/api-keys", response_model=list[ApiKeyResponse])
async def list_api_keys(
    context: AuthContext = Depends(require_auth_context()),
    store: ApiKeyStore = Depends(get_api_key_store),
):
    return await store.list_for_user(context.subject)


@router.post(
    "/users/me/api-keys",
    response_model=ApiKeyCreateResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_api_key(
    payload: ApiKeyCreateRequest,
    context: AuthContext = Depends(require_auth_context()),
    store: ApiKeyStore = Depends(get_api_key_store),
):
    return await store.create(context.subject, payload)


@router.delete("/users/me/api-keys/{record_id}", status_code=status.HTTP_204_NO_CONTENT)
async def revoke_api_key(
    record_id: UUID,
    context: AuthContext = Depends(require_auth_context()),
    store: ApiKeyStore = Depends(get_api_key_store),
):
    if not await store.revoke(context.subject, record_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="API key not found",
        )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/auth/api-key", response_model=TokenResponse)
async def exchange_api_key(
    payload: ApiKeyExchangeRequest,
    request: Request,
    store: ApiKeyStore = Depends(get_api_key_store),
    provider: IIdentityProvider = Depends(get_identity_provider),
):
    enforce_rate_limit(request, name="api-key", limit=10)
    record = await store.verify(payload.key_id, payload.secret)
    if record is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API key",
        )

    tokens = await provider.issue_tokens_for_user(record["user_id"])
    await store.mark_used(record["id"])
    return tokens
