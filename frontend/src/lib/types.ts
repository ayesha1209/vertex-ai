export type ProductType = "chemical" | "engineering";

export type DocumentType = "quotation" | "coa" | "coc" | "tds" | "msds" | "combined" | "proforma_invoice" | "invoice";

export interface RowPreview {
  id: number;
  buyer_name: string;
  product_name: string;
  doc_types?: string | null;
  quantity?: string | null;
  unit?: string | null;
  country?: string | null;
  port?: string | null;
  incoterm?: string | null;
  payment_terms?: string | null;
  remarks?: string | null;
  date?: string | null;
  employee_name?: string | null;
  company_name?: string | null;
  department?: string | null;
  quotation_no?: string | null;
  buyer_enquir_ref_no?: string | null;
  address?: string | null;
  letterhead?: string | null;
  local_export?: string | null;
  transportation?: string | null;
  type_of_packing?: string | null;
  email_id?: string | null;
  contact_no?: string | null;
  manufacturer_name?: string | null;
  product_description?: string | null;
  hsn_code?: string | null;
  cas_no?: string | null;
  packing?: string | null;
  price?: string | null;
  price_fob_cif?: string | null;
  port_of_loading?: string | null;
  port_of_unloading?: string | null;
  unloading_country?: string | null;
  /** From Excel "Product type" — overrides keyword detection when set */
  product_type?: "chemical" | "engineering" | null;
  attachment?: string | null;
  dimensional?: string | null;
  technical_specification?: string | null;
}

export interface UploadPreviewResponse {
  rows: RowPreview[];
}

export interface DocumentSummary {
  id: string;
  buyer_name: string;
  product_name: string;
  product_type: ProductType;
  doc_type: DocumentType;
  created_at: string;
  updated_at: string;
  employee_name?: string | null;
  batch_id?: string | null;
}

export interface TermsResponse {
  chemical: string;
  engineering: string;
}

export interface ListDocumentsResponse {
  documents: DocumentSummary[];
  total: number;
  warning?: string;
}

export interface BatchSummary {
  batch_id: string;
  buyer_name: string;
  product_name: string;
  product_type: ProductType;
  employee_name?: string | null;
  created_at: string;
  letterhead?: string | null;
  local_export?: string | null;
  company_name?: string | null;
  quantity?: string | null;
  unit?: string | null;
  country?: string | null;
  port?: string | null;
  incoterm?: string | null;
  payment_terms?: string | null;
  remarks?: string | null;
}

export interface ListBatchesResponse {
  batches: BatchSummary[];
  total: number;
  warning?: string;
}

export interface DocumentInDB {
  id: string;
  buyer_name: string;
  product_name: string;
  product_type: ProductType;
  doc_type: DocumentType;
  html_content: string;
  created_at: string;
  updated_at: string;
  employee_name?: string | null;
  batch_id?: string | null;
}

export interface GenerateRowResponse {
  documents: DocumentInDB[];
}

