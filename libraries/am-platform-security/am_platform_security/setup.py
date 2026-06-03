from fastapi import FastAPI
from am_platform_security.config import SecuritySettings, get_security_settings
from am_platform_security.validator import TokenValidator
from am_platform_security.middleware import SecurityMiddleware

def install_security(app: FastAPI, settings: SecuritySettings = None):
    """
    Auto-wires the global security filter into the FastAPI application
    if security is enabled in the settings.
    """
    if settings is None:
        settings = get_security_settings()
        
    if settings.enabled:
        validator = TokenValidator(settings)
        app.add_middleware(SecurityMiddleware, settings=settings, validator=validator)
