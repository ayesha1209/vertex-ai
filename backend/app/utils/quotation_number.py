"""Quotation number: VERT/[SEQUENCE]/[YEAR] e.g. VERT/001/2026."""

import logging
from datetime import datetime, timezone
from typing import Optional

from pymongo import ReturnDocument
from pymongo.errors import DuplicateKeyError

from app.db.mongo import db, documents_collection

logger = logging.getLogger(__name__)

_counters_collection = db["counters"]
_COUNTER_ID = "quotation_number"


def _seed_counter_value() -> int:
    """One-time seed: highest sequence number already issued in existing documents, so the
    persisted counter picks up after real historical quotations instead of colliding with
    them the first time this runs against data older than this counter."""
    try:
        pipeline = [
            {"$match": {"quotation_no": {"$regex": r"^VERT/\d+/\d+$"}}},
            {"$project": {"seq_str": {"$arrayElemAt": [{"$split": ["$quotation_no", "/"]}, 1]}}},
            {"$project": {"seq_num": {"$toInt": "$seq_str"}}},
            {"$group": {"_id": None, "max_seq": {"$max": "$seq_num"}}},
        ]
        result = list(documents_collection.aggregate(pipeline))
        return result[0]["max_seq"] if result else 0
    except Exception:
        logger.exception("Failed to seed quotation-number counter from existing documents")
        return 0


def generate_quotation_no(company_name: Optional[str] = None) -> str:
    """Generate the next quotation number: VERT/SEQ/YEAR.

    Backed by a MongoDB atomic counter rather than an in-memory variable — an in-memory
    counter resets to 0 on every Render restart/redeploy (or diverges across multiple
    instances), risking the same quotation number being issued twice to different buyers.
    """
    counter = _counters_collection.find_one_and_update(
        {"_id": _COUNTER_ID},
        {"$inc": {"seq": 1}},
        return_document=ReturnDocument.AFTER,
    )
    if counter is None:
        # First-ever call: seed from existing data, then insert atomically so a concurrent
        # first call can't both seed and collide.
        seed = _seed_counter_value() + 1
        try:
            _counters_collection.insert_one({"_id": _COUNTER_ID, "seq": seed})
            seq = seed
        except DuplicateKeyError:
            # Lost the race to another concurrent first call — increment normally instead.
            counter = _counters_collection.find_one_and_update(
                {"_id": _COUNTER_ID}, {"$inc": {"seq": 1}}, return_document=ReturnDocument.AFTER
            )
            seq = counter["seq"]
    else:
        seq = counter["seq"]
    year = datetime.now(timezone.utc).year
    return f"VERT/{seq:03d}/{year}"


def build_quotation_no(seq: int) -> str:
    """Build a quotation number from a user-supplied sequence integer."""
    year = datetime.now(timezone.utc).year
    return f"VERT/{seq:03d}/{year}"
