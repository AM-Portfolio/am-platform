import logging
from fastapi import Request, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
import jwt
from jwt.exceptions import ExpiredSignatureError, InvalidSignatureError, InvalidTokenError

from app.config import settings
from app.security.jwks_cache import jwks_cache
from app.security.models import TokenPayload

logger = logging.getLogger(__name__)

class JWTBearer(HTTPBearer):
    def __init__(self, auto_error: bool = True):
        super().__init__(auto_error=auto_error)

    async def __call__(self, request: Request) -> TokenPayload:
        credentials: HTTPAuthorizationCredentials = await super().__call__(request)
        if not credentials:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid authorization credentials",
            )

        token = credentials.credentials
        try:
            # 1. Decode header to extract kid (Key ID)
            unverified_header = jwt.get_unverified_header(token)
            kid = unverified_header.get("kid")
            if not kid:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Token header missing 'kid'",
                )

            # 2. Retrieve the public key matching kid
            public_key = await jwks_cache.get_public_key(kid)

            # 3. Verify signature and standard claims
            # Keycloak tokens may or may not specify client_id in the aud claim.
            # Usually Keycloak token aud is the client_id or account.
            # We can verify the issuer, and verify signature. We can pass options to verify audience if needed.
            options = {
                "verify_aud": False, # Aud verification can sometimes fail if audience is custom in Keycloak, but let's make it robust
            }
            
            payload = jwt.decode(
                token,
                public_key,
                algorithms=["RS256"],
                issuer=settings.OIDC_ISSUER,
                options=options
            )

            # Optional: Manually check client audience if settings.AM_MCP_CLIENT_ID is specified and verify_aud is disabled
            aud = payload.get("aud")
            # If audience is a list or single string, check if client_id is present
            if aud and settings.AM_MCP_CLIENT_ID:
                audiences = aud if isinstance(aud, list) else [aud]
                # Keycloak client ID might also be mapped in 'azp' (Authorized party)
                azp = payload.get("azp")
                if settings.AM_MCP_CLIENT_ID not in audiences and azp != settings.AM_MCP_CLIENT_ID:
                    logger.warning(f"Audience/AZP mismatch. Token aud: {aud}, azp: {azp}. Expected client: {settings.AM_MCP_CLIENT_ID}")
                    # In some environments, we might want to warn or raise. Let's warn but allow to pass if signature is valid, 
                    # or restrict based on requirements. Let's make it raise an error if client ID doesn't match either aud or azp.
                    # Wait, let's make it check if azp == client_id or client_id in aud.
                    if azp != settings.AM_MCP_CLIENT_ID:
                        raise HTTPException(
                            status_code=status.HTTP_401_UNAUTHORIZED,
                            detail="Invalid token audience",
                        )

            # 4. Extract Keycloak roles (realm and client level)
            roles = []
            realm_access = payload.get("realm_access", {})
            if "roles" in realm_access:
                roles.extend(realm_access["roles"])
            
            resource_access = payload.get("resource_access", {})
            client_access = resource_access.get(settings.AM_MCP_CLIENT_ID, {})
            if "roles" in client_access:
                roles.extend(client_access["roles"])

            return TokenPayload(
                sub=payload.get("sub", ""),
                email=payload.get("email"),
                preferred_username=payload.get("preferred_username"),
                roles=roles,
                client_id=payload.get("azp"),
                iss=payload.get("iss", ""),
                exp=payload.get("exp", 0)
            )

        except ExpiredSignatureError as e:
            logger.warning("JWT token signature has expired")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="token_expired",
            )
        except InvalidSignatureError as e:
            logger.warning("JWT token signature verification failed")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="token_invalid_signature",
            )
        except KeyError as e:
            logger.warning(f"Signing key not found in JWKS: {str(e)}")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="signing_key_not_found",
            )
        except InvalidTokenError as e:
            logger.warning(f"Invalid token format or claims: {str(e)}")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="token_invalid",
            )
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Unexpected error validating token: {str(e)}")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="token_validation_error",
            )

# Global Dependency
get_current_user = JWTBearer()
