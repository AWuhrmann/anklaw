from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Optional
import uuid


class CardStatus(str, Enum):
    PENDING = "pending"
    IMPORTED = "imported"
    FAILED = "failed"


class CardType(str, Enum):
    BASIC = "Basic"
    CLOZE = "Cloze"


@dataclass
class Card:
    front: str
    back: str
    deck_name: str
    tags: list = field(default_factory=list)
    card_type: CardType = CardType.BASIC
    id: Optional[int] = None
    batch_id: Optional[str] = None
    status: CardStatus = CardStatus.PENDING
    created_at: Optional[datetime] = None
    imported_at: Optional[datetime] = None


@dataclass
class Batch:
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    topic_snapshot: str = ""
    cards_requested: int = 0
    cards_generated: int = 0
    llm_model: str = ""
    status: str = "completed"
