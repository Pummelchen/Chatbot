from __future__ import annotations

from contextlib import contextmanager
from typing import Iterator

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

