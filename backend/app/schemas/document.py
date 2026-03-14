from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class ProductType(str, Enum):
    chemical = "chemical"
    engineering = "engineering"


class DocumentType(str, Enum):
    quotation = "quotation"
    coa = "coa"  # Certificate of Analysis
    coc = "coc"  # Certificate of Conformance
    tds = "tds"  # Technical Data Sheet
    msds = "msds"  # Material Safety Data Sheet
    combined = "combined"  # Legacy: no longer generated; kept for existing DB docs


class RowInput(BaseModel):
    buyer_name: str = Field(..., alias="Buyer Name")
    product_name: str = Field(..., alias="Product Name")
    quantity: Optional[str] = Field(None, alias="Quantity")
    unit: Optional[str] = Field(None, alias="Unit")
    country: Optional[str] = Field(None, alias="Country")
    port: Optional[str] = Field(None, alias="Port")
    incoterm: Optional[str] = Field(None, alias="Incoterm")
    payment_terms: Optional[str] = Field(None, alias="Payment Terms")
    remarks: Optional[str] = Field(None, alias="Remarks")

    class Config:
        populate_by_name = True


class RowPreview(BaseModel):
    """Preview row from enquiry Excel. Use Excel value when available; empty or 'from ai' → AI generates."""

    id: int
    buyer_name: str
    product_name: str
    # Enquiry columns (optional)
    date: Optional[str] = None
    employee_name: Optional[str] = None
    company_name: Optional[str] = None
    department: Optional[str] = None
    quotation_no: Optional[str] = None  # auto-generate if empty
    buyer_enquir_ref_no: Optional[str] = None
    address: Optional[str] = None
    letterhead: Optional[str] = None  # "dubai" | "india" for chemical header address
    local_export: Optional[str] = None
    transportation: Optional[str] = None
    type_of_packing: Optional[str] = None
    country: Optional[str] = None
    email_id: Optional[str] = None
    contact_no: Optional[str] = None
    manufacturer_name: Optional[str] = None
    product_description: Optional[str] = None
    hsn_code: Optional[str] = None  # use if present; else "from ai" or empty → AI
    cas_no: Optional[str] = None
    quantity: Optional[str] = None
    unit: Optional[str] = None
    packing: Optional[str] = None
    price: Optional[str] = None  # AI generates if empty
    price_fob_cif: Optional[str] = None
    port_of_loading: Optional[str] = None
    port_of_unloading: Optional[str] = None
    unloading_country: Optional[str] = None
    # Legacy / aliases
    port: Optional[str] = None
    incoterm: Optional[str] = None
    payment_terms: Optional[str] = None
    remarks: Optional[str] = None

    class Config:
        populate_by_name = True


class UploadPreviewResponse(BaseModel):
    rows: list[RowPreview]


class DocumentBase(BaseModel):
    buyer_name: str
    product_name: str
    product_type: ProductType
    doc_type: DocumentType
    html_content: str
    # Optional: from Excel / generation context
    employee_name: Optional[str] = None  # person who entered the row
    letterhead: Optional[str] = None  # "dubai" | "india" for chemical address/phone
    batch_id: Optional[str] = None  # groups quotation, tds, coa, msds from same generation
    quotation_no: Optional[str] = None
    company_name: Optional[str] = None
    local_export: Optional[str] = None  # "local" | "export" for currency (Rs vs $)
    # Row fields used for "View details" (from enquiry row at generation time)
    quantity: Optional[str] = None
    unit: Optional[str] = None
    country: Optional[str] = None
    port: Optional[str] = None
    incoterm: Optional[str] = None
    payment_terms: Optional[str] = None
    remarks: Optional[str] = None


class DocumentCreate(DocumentBase):
    pass


class CreateManualDocumentRequest(BaseModel):
    """Request body for creating a document manually (no AI generation)."""
    buyer_name: str
    product_name: str
    doc_type: DocumentType = DocumentType.quotation
    product_type: ProductType = ProductType.chemical
    letterhead: Optional[str] = None   # "india" | "dubai"
    local_export: Optional[str] = None  # "local" | "export"
    html_content: str = ""


class DocumentInDB(DocumentBase):
    id: str
    created_at: datetime
    updated_at: datetime


class DocumentSummary(BaseModel):
    id: str
    buyer_name: str
    product_name: str
    product_type: ProductType
    doc_type: DocumentType
    created_at: datetime
    updated_at: datetime
    employee_name: Optional[str] = None
    batch_id: Optional[str] = None


class ListDocumentsResponse(BaseModel):
    documents: list[DocumentSummary]
    total: int
    warning: Optional[str] = None  # Set when DB is unavailable but we return empty list


class BatchSummary(BaseModel):
    """One row per batch for dashboard; includes fields used for generation (View details)."""
    batch_id: str
    buyer_name: str
    product_name: str
    product_type: str  # "chemical" | "engineering"
    employee_name: Optional[str] = None
    created_at: datetime
    letterhead: Optional[str] = None
    local_export: Optional[str] = None
    company_name: Optional[str] = None
    quantity: Optional[str] = None
    unit: Optional[str] = None
    country: Optional[str] = None
    port: Optional[str] = None
    incoterm: Optional[str] = None
    payment_terms: Optional[str] = None
    remarks: Optional[str] = None


class ListBatchesResponse(BaseModel):
    batches: list[BatchSummary]
    total: int
    warning: Optional[str] = None


class TermsResponse(BaseModel):
    chemical: str = ""
    engineering: str = ""


class TermsUpdateRequest(BaseModel):
    chemical: str | None = None
    engineering: str | None = None


class BulkDeleteRequest(BaseModel):
    ids: list[str]


class UpdateDocumentRequest(BaseModel):
    html_content: str
    product_name: Optional[str] = None   # overwrite document title (manual docs)
    employee_name: Optional[str] = None  # set creator name (manual docs)


class GenerateRowRequest(BaseModel):
    row: RowPreview


class GenerateRowResponse(BaseModel):
    documents: list[DocumentInDB]


class GenerateBatchRequest(BaseModel):
    rows: list[RowPreview]


class GenerateBatchResponse(BaseModel):
    job_id: str

