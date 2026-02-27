"""Interaction ORM model — audit trail of every chat turn."""

from sqlalchemy import (
    Column, Integer, Text, Boolean, String,
    JSON, TIMESTAMP, ForeignKey, func,
)
from sqlalchemy.orm import relationship

from app.database import Base


class Interaction(Base):
    """
    Records every chat turn; includes allergy audit fields so it is
    possible to audit what warnings were shown for any past response.
    """

    __tablename__ = "interactions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    uid = Column(
        String(36),
        ForeignKey("users.uid", ondelete="CASCADE"),
        nullable=False,
    )

    user_query = Column(Text, nullable=False)
    agent_response = Column(JSON, nullable=False, default=dict)

    ui_type = Column(Text, nullable=True)
    restaurant_ids = Column(JSON, nullable=True)

    # Allergy audit trail
    allergy_warnings_shown = Column(Boolean, nullable=False, server_default="0")
    allergens_flagged = Column(JSON, nullable=False, default=list)

    prompt_tokens = Column(Integer, nullable=True)
    completion_tokens = Column(Integer, nullable=True)

    created_at = Column(
        TIMESTAMP(timezone=True), nullable=False, server_default=func.now()
    )

    # Relationships
    user = relationship("User", back_populates="interactions")
