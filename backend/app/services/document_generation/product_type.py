"""Product type detection: chemical vs engineering."""

from app.schemas.document import ProductType, RowPreview

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
    "module", "plc", "oem", "din rail", "part number", "interface module",
    "industrial component", "scada", "hmi", "dcs", "vfd", "drive", "panel",
    "mcc", "amf", "apfc", "encoder", "servo", "thermowell",
]


def resolve_product_type(row: RowPreview) -> ProductType:
    """Excel `product_type` column overrides keyword detection when set."""
    pt = row.product_type
    if pt == "engineering":
        return ProductType.engineering
    if pt == "chemical":
        return ProductType.chemical
    return detect_product_type(row.product_name or "")


def detect_product_type(product_name: str) -> ProductType:
    name = product_name.lower()
    if any(k in name for k in ENGINEERING_KEYWORDS):
        return ProductType.engineering
    if any(k in name for k in CHEMICAL_KEYWORDS):
        return ProductType.chemical
    return ProductType.chemical
