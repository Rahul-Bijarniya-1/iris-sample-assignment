"""
News Signal Model

Structured signals extracted from one news article: which planner-relevant
themes it touches, and what entity it names, if any.

Author:
NRW BI Platform
"""

from __future__ import annotations

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    func,
)

from sqlalchemy.orm import (
    Mapped,
    mapped_column,
)

from app.database.base import Base


class NewsSignal(Base):

    __tablename__ = "news_signals"

    __table_args__ = (
        {
            "schema": "iris_core",
        },
    )

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        autoincrement=True,
    )

    article_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey(
            "iris_core.news_articles.id",
            ondelete="CASCADE",
        ),
        nullable=False,
        index=True,
    )

    expansion: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
    )

    power: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
    )

    renewable: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
    )

    retrofit: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
    )

    investment: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
    )

    capacity_mw: Mapped[float | None] = mapped_column(
        Float,
        nullable=True,
    )

    confidence: Mapped[float | None] = mapped_column(
        Float,
        nullable=True,
    )

    city: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
    )

    company: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )

    created_at: Mapped[DateTime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
