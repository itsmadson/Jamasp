import enum

from sqlalchemy import Enum, String
from sqlalchemy.orm import Mapped, mapped_column

from jamasp.models.base import Base, TimestampMixin, UUIDMixin


class UserRole(enum.StrEnum):
    ADMIN = "admin"
    ANALYST = "analyst"


class User(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "users"

    email: Mapped[str] = mapped_column(String(320), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(200))
    role: Mapped[UserRole] = mapped_column(
        Enum(UserRole, native_enum=False), default=UserRole.ANALYST
    )
    locale: Mapped[str] = mapped_column(String(5), default="fa")
