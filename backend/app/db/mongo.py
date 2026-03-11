from datetime import datetime

from bson import ObjectId
from pymongo import MongoClient

from app.core.config import get_settings


settings = get_settings()

client = MongoClient(settings.MONGODB_URI)
db = client[settings.MONGODB_DB_NAME]
documents_collection = db["documents"]
terms_collection = db["terms_and_conditions"]
# Single document id for terms (chemical + engineering HTML)
TERMS_DOC_ID = "default"


def now_local() -> datetime:
    """Return current local time (system timezone)."""
    return datetime.now()


def to_object_id(id_str: str) -> ObjectId:
    try:
        return ObjectId(id_str)
    except Exception as exc:  # noqa: BLE001
        raise ValueError("Invalid document id") from exc

