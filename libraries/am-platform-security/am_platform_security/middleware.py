import re
from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from am_platform_security.config import SecuritySettings
from am_platform_security.validator import TokenValidator
from am_platform_security.models import AuthContext

class SecurityMiddleware(BaseHTTPMiddleware):
    """
    Global security filter that enforces authentication on all routes
    except those explicitly listed in public_paths.
    """
    def __init__(self, app, settings: SecuritySettings, validator: TokenValidator):
        super().__init__(app)
        self.settings = settings
        self.validator = validator
        
        # Compile public paths to regexes for efficient matching
        self.public_patterns = []
        for path in self.settings.public_paths:
            # Convert simple ant-style paths like /api/v1/public/* to regex
            pattern = path.replace("*", ".*")
            self.public_patterns.append(re.compile(f"^{pattern}$"))

    async def dispatch(self, request: Request, call_next):
        path = request.url.path
        
        # 1. Check if path is public
        for pattern in self.public_patterns:
            if pattern.match(path):
                return await call_next(request)
                
        # 2. Local mock support (matches LocalMockUserContextFilter from Java)
        if self.settings.local_mock_enabled:
            mock_context = AuthContext(
                subject="mock-user",
                client_id="mock-client",
                token_type="user",
                roles=[self.settings.service_role_name, "user", "admin"],
                scopes=["all"],
                claims={"mock": True},
                access_token="mock-token"
            )
            request.state.auth_context = mock_context
            return await call_next(request)

        # 3. Enforce Bearer Token
        auth_header = request.headers.get("Authorization")
        if not auth_header or not auth_header.lower().startswith("bearer "):
            return JSONResponse(
                status_code=401, 
                content={"error_code": "UNAUTHORIZED", "message": "Bearer token is required"}
            )
            
        token = auth_header[7:]
        
        # 4. Validate Token
        try:
            context = await self.validator.validate(token)
            request.state.auth_context = context
        except Exception as e:
            import logging
            logging.getLogger("am_platform_security").warning(f"Token validation failed: {str(e)}")
            return JSONResponse(
                status_code=401, 
                content={"error_code": "UNAUTHORIZED", "message": "Invalid access token"}
            )
            
        return await call_next(request)
