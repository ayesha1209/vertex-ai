"""Product type detection: chemical vs engineering."""

from app.schemas.document import ProductType

CHEMICAL_KEYWORDS = [
    "sulphur", "sulfur", "urea", "copper", "pac", "aluminium", "chloride",
    "fertilizer", "chemical", "powder", "granules", "crystal", "salt", "acid",
    "base", "solvent", "polymer", "flocculant", "reagent",
]

ENGINEERING_KEYWORDS = [
    "valve", "bushing", "flow meter", "meter", "transmitter", "converter",
    "spare part", "electrical", "transformer", "breaker", "switch", "relay",
    "cable", "connector", "flange", "pipe", "fitting", "pump", "motor",
    "instrument", "gauge", "sensor", "controller", "actuator", "elastimold",
    "krohne", "dbb", "api", "ansi", "ieee",
]


def detect_product_type(product_name: str) -> ProductType:
    name = product_name.lower()
    if any(k in name for k in ENGINEERING_KEYWORDS):
        return ProductType.engineering
    if any(k in name for k in CHEMICAL_KEYWORDS):
        return ProductType.chemical
    return ProductType.chemical
