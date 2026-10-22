import asyncio
import hashlib
import secrets
from datetime import UTC, datetime, timedelta

from argon2 import PasswordHasher
from argon2.exceptions import VerificationError
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import col

from myapp.core.config import Settings
from myapp.core.exceptions import AppError
from myapp.modules.auth.models import LoginSession
from myapp.modules.users.models import User

hasher = PasswordHasher()


def token_digest(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


class AuthService:
    async def register(self, session: AsyncSession, username: str, password: str) -> User:
        user = User.model_validate(
            {
                "username": username.casefold(),
                "password_hash": await asyncio.to_thread(hasher.hash, password),
            }
        )
        session.add(user)
        try:
            await session.flush()
        except IntegrityError as exc:
            raise AppError(409, "CONFLICT", "Username unavailable") from exc
        return user

    async def login(
        self, session: AsyncSession, settings: Settings, username: str, password: str
    ) -> tuple[User, str, str]:
        user = await session.scalar(select(User).where(col(User.username) == username.casefold()))
        # Unknown users take the same expensive hashing path, without a module-import side effect.
        if user is None:
            await asyncio.to_thread(hasher.hash, password)
            raise AppError(401, "INVALID_CREDENTIALS", "Invalid credentials")
        try:
            await asyncio.to_thread(hasher.verify, user.password_hash, password)
        except VerificationError as exc:
            raise AppError(401, "INVALID_CREDENTIALS", "Invalid credentials") from exc
        if hasher.check_needs_rehash(user.password_hash):
            user.password_hash = await asyncio.to_thread(hasher.hash, password)
        token, csrf = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
        session.add(
            LoginSession(
                user_id=user.id,
                token_hash=token_digest(token),
                csrf_hash=token_digest(csrf),
                expires_at=datetime.now(UTC) + timedelta(seconds=settings.session.ttl_seconds),
            )
        )
        await session.flush()
        return user, token, csrf

    async def authenticate(self, session: AsyncSession, token: str) -> tuple[User, LoginSession]:
        if len(token) > 256:
            raise AppError(401, "UNAUTHORIZED", "Invalid session")
        result = await session.execute(
            select(User, LoginSession)
            .join(LoginSession, col(LoginSession.user_id) == col(User.id))
            .where(
                col(LoginSession.token_hash) == token_digest(token),
                col(LoginSession.expires_at) > datetime.now(UTC),
            )
        )
        pair = result.first()
        if pair is None:
            raise AppError(401, "UNAUTHORIZED", "Session expired or revoked")
        return pair[0], pair[1]
