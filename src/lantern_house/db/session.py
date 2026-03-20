# Lantern House core instruction: stay fail-safe, never leak debug or
# error text into the live chat, log recovered failures to
# logs/error.txt with context, and preserve hot-patch compatibility
# for uninterrupted long-running operation.
from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import Engine, create_engine, text
from sqlalchemy.orm import Session, sessionmaker

from lantern_house.config import DatabaseConfig


def create_engine_from_config(config: DatabaseConfig) -> Engine:
    return create_engine(
        config.url,
        echo=config.echo,
        pool_pre_ping=True,
        future=True,
    )


class SessionFactory:
    def __init__(self, engine: Engine) -> None:
        self._session_maker = sessionmaker(bind=engine, expire_on_commit=False, future=True)

    @contextmanager
    def session_scope(self) -> Iterator[Session]:
        session = self._session_maker()
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def ping(self) -> None:
        with self.session_scope() as session:
            session.execute(text("SELECT 1"))
