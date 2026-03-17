"""Parse enquiry Excel: extract rows. Use Excel value when available; empty or 'from ai' → leave for AI."""

from typing import Any, List

import pandas as pd
from fastapi import HTTPException, UploadFile, status

from app.schemas.document import RowPreview


def _normalize_date(val: Any) -> str | None:
    """Convert Excel date/datetime or date string to YYYY-MM-DD for consistent filtering."""
    if val is None or (isinstance(val, float) and pd.isna(val)):
        return None
    if hasattr(val, "strftime"):
        return val.strftime("%Y-%m-%d")
    s = str(val).strip()
    if not s or s.lower() == "from ai":
        return None
    try:
        parsed = pd.to_datetime(s)
        return parsed.strftime("%Y-%m-%d")
    except Exception:
        return s


def _col(df: pd.DataFrame, *candidates: str) -> str | None:
    """Return first column name that exists (case-insensitive match)."""
    cols_lower = {c.lower(): c for c in df.columns}
    for c in candidates:
        if c.lower() in cols_lower:
            return cols_lower[c.lower()]
    return None


def _val(row: Any, col: str | None, default: str | None = None) -> str | None:
    """Get string value; if empty or 'from ai' return None so AI generates."""
    if col is None:
        return default
    try:
        v = row[col]
    except (KeyError, TypeError):
        return default
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return default
    s = str(v).strip().lower()
    if s == "" or s == "from ai":
        return None
    return str(v).strip()


# Required: at least one of these for Buyer and Product
BUYER_CANDIDATES = ["Buyer Name", "Buyer name", "buyer name"]
PRODUCT_CANDIDATES = ["Product name", "Product Name", "product name"]

# Optional enquiry columns (Excel header -> RowPreview field)
ENQUIRY_MAP = [
    # Which docs to generate: e.g. "q,tds,coa,msds" (empty → all)
    ("doc_types", ["Docs", "docs", "Doc types", "Doc Types", "Documents", "Docs to generate"]),
    ("date", ["date", "Date", "Invoice Date", "invoice date", "Order Date", "order date", "Enquiry Date", "enquiry date"]),
    ("Employee Name", ["Employee Name", "employee name"]),
    ("Company Name", ["Company Name", "company name"]),
    ("Department", ["Department", "department"]),
    ("Quotation no", ["Quotation no", "Quotation No", "quotation no"]),
    ("Buyer enquir Ref no", ["Buyer enquir Ref no", "Buyer enquir ref no"]),
    ("Address", ["Address", "address"]),
    ("Letterhead", ["Letterhead", "letterhead", "Letter head"]),
    ("Local/export", ["Local/export", "Local/Export", "local/export"]),
    ("Transportation", ["Transportation", "transportation"]),
    ("type of packingg", ["type of packingg", "type of packing", "Type of packing"]),
    ("Country name", ["Country name", "Country Name", "Country", "country"]),
    ("Email id", ["Email id", "Email Id", "email id"]),
    ("Contact no", ["Contact no", "Contact No", "contact no"]),
    ("Manufacturer name", ["Manufacturer name", "Manufacturer Name"]),
    ("Product Description", ["Product Description", "product description"]),
    ("hsn code", ["hsn code", "HSN code", "HSN Code"]),
    ("cas no", ["cas no", "CAS no", "CAS No"]),
    ("Qty", ["Qty", "Quantity", "quantity"]),
    ("Unit", ["Unit", "unit", "Unit (kg/Mt)", "Unit (kg/MT)"]),
    ("packing", ["packing", "Packing", "Packing"]),
    ("Price", ["Price", "price"]),
    ("Price FOB/CIF", ["Price FOB/CIF", "price fob/cif"]),
    ("port of loading", ["port of loading", "Port of loading", "Port"]),
    ("port of unloading", ["port of unloading", "Port of unloading"]),
    ("unloading country name", ["unloading country name", "unloading country"]),
    ("Incoterm", ["Incoterm", "incoterm"]),
    ("Payment Terms", ["Payment Terms", "payment terms"]),
    ("Remarks", ["Remarks", "remarks"]),
]


def parse_excel_to_previews(upload_file: UploadFile, max_rows: int = 500) -> List[RowPreview]:
    """Parse Excel/CSV into RowPreview list. Raises HTTPException on bad file or missing columns."""
    filename = upload_file.filename or ""
    try:
        if filename.lower().endswith(".csv"):
            df = pd.read_csv(upload_file.file, nrows=max_rows)
        else:
            df = pd.read_excel(upload_file.file)
            if len(df) > max_rows:
                df = df.iloc[:max_rows]
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Could not read file: {exc}",
        ) from exc

    buyer_col = _col(df, *BUYER_CANDIDATES)
    product_col = _col(df, *PRODUCT_CANDIDATES)
    if not buyer_col or not product_col:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Missing required columns: need 'Buyer Name' and 'Product name' (or Product Name).",
        )

    # Build optional column mapping: RowPreview field name -> actual column name
    opt_map: dict[str, str] = {}
    for field_name, candidates in ENQUIRY_MAP:
        c = _col(df, *candidates)
        if c:
            opt_map[field_name] = c

    previews: List[RowPreview] = []
    for idx, row in df.iterrows():
        buyer_name = _val(row, buyer_col) or ""
        product_name = _val(row, product_col) or ""
        if not buyer_name or not product_name:
            continue

        def get(f: str) -> str | None:
            col = opt_map.get(f)
            return _val(row, col)

        # Date: normalize to YYYY-MM-DD when possible for filtering
        date_str = _normalize_date(get("date"))

        # Map to RowPreview; use quantity from Qty or Quantity
        qty = get("Qty")
        if qty is None and "Quantity" in opt_map:
            qty = _val(row, opt_map["Quantity"])

        previews.append(
            RowPreview(
                id=int(idx),
                buyer_name=buyer_name,
                product_name=product_name,
                doc_types=get("doc_types"),
                date=date_str,
                employee_name=get("Employee Name"),
                company_name=get("Company Name"),
                department=get("Department"),
                quotation_no=get("Quotation no"),
                buyer_enquir_ref_no=get("Buyer enquir Ref no"),
                address=get("Address"),
                letterhead=get("Letterhead"),
                local_export=get("Local/export"),
                transportation=get("Transportation"),
                type_of_packing=get("type of packingg"),
                country=get("Country name"),
                email_id=get("Email id"),
                contact_no=get("Contact no"),
                manufacturer_name=get("Manufacturer name"),
                product_description=get("Product Description"),
                hsn_code=get("hsn code"),
                cas_no=get("cas no"),
                quantity=qty,
                unit=get("Unit"),
                packing=get("packing"),
                price=get("Price"),
                price_fob_cif=get("Price FOB/CIF"),
                port_of_loading=get("port of loading"),
                port_of_unloading=get("port of unloading"),
                unloading_country=get("unloading country name"),
                port=get("port of loading"),
                incoterm=get("Incoterm"),
                payment_terms=get("Payment Terms"),
                remarks=get("Remarks"),
            )
        )

    if not previews:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No valid rows found (need non-empty Buyer Name and Product name).",
        )

    if len(previews) >= max_rows:
        # Caller may want to know we truncated
        pass  # Still return previews; optional: add warning in response later
    return previews
