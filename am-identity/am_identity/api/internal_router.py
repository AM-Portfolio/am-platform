from fastapi import APIRouter, Depends

from am_identity.deps import get_identity_provider
from am_identity.providers.interface import IIdentityProvider
from am_identity.schemas.auth import ServiceTokenRequest, ServiceTokenResponse
from am_platform_security import AuthContext, require_service_account

router = APIRouter(prefix="/internal", tags=["internal"])


@router.get("/users/{user_id}")
async def get_internal_user(
    user_id: str,
    _: AuthContext = Depends(require_service_account()),
):
    return {"sub": user_id}


@router.post("/auth/service-token", response_model=ServiceTokenResponse)
async def issue_service_token(
    payload: ServiceTokenRequest,
    _: AuthContext = Depends(require_service_account()),
    provider: IIdentityProvider = Depends(get_identity_provider),
):
    token = await provider.issue_service_token(audience=payload.audience)
    return {
        "access_token": token["access_token"],
        "expires_in": token["expires_in"],
        "token_type": token.get("token_type", "Bearer"),
    }
