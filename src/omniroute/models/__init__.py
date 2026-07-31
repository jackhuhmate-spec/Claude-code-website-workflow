"""
Omniroute ORM models.

SQLAlchemy is OPTIONAL. When unavailable, models are placeholders.
Install with: pip install sqlalchemy
"""

from omniroute.models.base import Base, TimestampMixin, DictMixin, _SA_AVAILABLE, require_sa

__all__ = [
    "Base",
    "TimestampMixin",
    "DictMixin",
    "_SA_AVAILABLE",
    "require_sa",
]

Lead: type
Customer: type
Subscription: type
Conversation: type
Message: type
Project: type
Deployment: type
Website: type

# Define Direction constants even without SQLAlchemy
class Direction:
    OUTBOUND = "outbound"
    INBOUND = "inbound"

__all__.extend(["Direction"])

if _SA_AVAILABLE:
    from omniroute.models.lead import Lead
    from omniroute.models.customer import Customer, Subscription
    from omniroute.models.conversation import Conversation, Message
    from omniroute.models.project import Project, Deployment, Website

    __all__.extend([
        "Lead", "Customer", "Subscription",
        "Conversation", "Message",
        "Project", "Deployment", "Website",
    ])
else:
    # Placeholder classes for when SQLAlchemy is not available
    Lead = object
    Customer = object
    Subscription = object
    Conversation = object
    Message = object
    Project = object
    Deployment = object
    Website = object
