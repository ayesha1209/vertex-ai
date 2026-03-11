"""Terms and Conditions: editable content for Chemical and Engineering, stored in MongoDB."""

from app.db.mongo import TERMS_DOC_ID, terms_collection
from app.prompts.vertex_prompts import DEFAULT_TERMS
from app.schemas.document import ProductType


def get_terms(product_type: ProductType) -> str:
    """Return terms for the given product type. Uses DEFAULT_TERMS from prompt when DB has none."""
    try:
        doc = terms_collection.find_one({"_id": TERMS_DOC_ID})
        if not doc:
            return DEFAULT_TERMS
        key = "chemical" if product_type == ProductType.chemical else "engineering"
        value = (doc.get(key) or "").strip()
        return value if value else DEFAULT_TERMS
    except Exception:
        return DEFAULT_TERMS
