from functools import lru_cache

from am_identity.core.config import IdentitySettings, get_settings
from am_identity.providers.interface import IIdentityProvider
from am_identity.providers.keycloak_provider import KeycloakIdentityProvider


@lru_cache(maxsize=1)
def get_identity_provider() -> IIdentityProvider:
    settings: IdentitySettings = get_settings()
    return KeycloakIdentityProvider(settings)
