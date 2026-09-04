from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from am_platform_security import AuthContext, require_service_account
from am_user_platform.core.config import UserPlatformSettings, get_settings
from am_user_platform.core.database import get_db_session
from am_user_platform.modules.ai.services.feedback_service import FeedbackService
from am_user_platform.modules.ai.services.message_service import MessageService
from am_user_platform.modules.ai.services.session_service import SessionService

# Service-to-service auth for internal routers (Sprint C §4).
RequireServiceAccount = Depends(require_service_account())


def get_session_service(
    session: AsyncSession = Depends(get_db_session),
) -> SessionService:
    return SessionService(session)


def get_message_service(
    session: AsyncSession = Depends(get_db_session),
) -> MessageService:
    return MessageService(session)


def get_feedback_service(
    session: AsyncSession = Depends(get_db_session),
) -> FeedbackService:
    return FeedbackService(session)


__all__ = [
    "AuthContext",
    "FeedbackService",
    "MessageService",
    "RequireServiceAccount",
    "SessionService",
    "UserPlatformSettings",
    "get_db_session",
    "get_feedback_service",
    "get_message_service",
    "get_session_service",
    "get_settings",
    "require_service_account",
]
