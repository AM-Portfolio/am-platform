from typing import List, Optional
from pydantic import BaseModel, Field

class TokenPayload(BaseModel):
    sub: str
    email: Optional[str] = None
    preferred_username: Optional[str] = None
    roles: List[str] = Field(default_factory=list)
    client_id: Optional[str] = None
    iss: str
    exp: int
