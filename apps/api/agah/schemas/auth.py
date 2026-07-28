from uuid import UUID

from pydantic import BaseModel


class LoginRequest(BaseModel):
    # Plain str, not EmailStr: self-hosted deployments legitimately use internal
    # domains such as admin@agah.local, which strict validation rejects.
    email: str
    password: str


class UserOut(BaseModel):
    """Has no password field at all: leaking the hash would require adding one."""

    id: UUID
    email: str
    role: str
    locale: str
