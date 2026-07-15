import { useCallback, useEffect, useRef, useState } from "react";
import { Link, useParams, useNavigate } from "react-router-dom";
import { getShipment, uploadShipmentDoc, deleteShipment, getShipmentDocUrl, type Shipment, type ShipmentDocSlot } from "../lib/api";
import { useAuth } from "../context/AuthContext";
import { DashboardLayout } from "../components/layout/DashboardLayout";

const DOC_TYPES = ["pi", "tax_invoice", "pl", "receipt_tt_copy", "bank_receipt", "bl_copy", "custom_copy"] as const;
type DocType = typeof DOC_TYPES[number];

const DOC_TYPE_LABELS: Record<DocType, string> = {
  pi: "Proforma Invoice (PI)",
  tax_invoice: "Tax Invoice",
  pl: "P/L (Packing List)",
  receipt_tt_copy: "Receipt (TT Copy)",
  bank_receipt: "Bank Receipt",
  bl_copy: "BL Copy",
  custom_copy: "Custom Copy",
};

function DocCard({
  docType,
  slot,
  shipmentId,
  onUploaded,
}: {
  docType: DocType;
  slot: ShipmentDocSlot | undefined;
  shipmentId: string;
  onUploaded: (docType: DocType, all_uploaded: boolean) => void;
}) {
  const fileRef = useRef<HTMLInputElement>(null);
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleFileChange = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setUploading(true);
    setError(null);
    try {
      const res = await uploadShipmentDoc(shipmentId, docType, file);
      onUploaded(docType, res.all_uploaded);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Upload failed");
    } finally {
      setUploading(false);
      if (fileRef.current) fileRef.current.value = "";
    }
  };

  const uploaded = slot?.uploaded ?? false;

  return (
    <div className={`rounded-xl border p-4 ${uploaded ? "border-emerald-200 bg-emerald-50" : "border-slate-200 bg-white"}`}>
      <div className="flex items-start justify-between gap-3">
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2">
            <span className={`flex h-6 w-6 shrink-0 items-center justify-center rounded-full text-xs font-bold ${uploaded ? "bg-emerald-500 text-white" : "bg-slate-200 text-slate-400"}`}>
              {uploaded ? "✓" : ""}
            </span>
            <h3 className={`text-sm font-semibold ${uploaded ? "text-emerald-800" : "text-slate-700"}`}>
              {DOC_TYPE_LABELS[docType]}
            </h3>
          </div>
          {uploaded && slot?.filename && (
            <p className="mt-1 pl-8 text-xs text-slate-500 truncate">{slot.filename}</p>
          )}
          {uploaded && slot?.uploaded_at && (
            <p className="pl-8 text-xs text-slate-400">
              {new Date(slot.uploaded_at).toLocaleString()}
            </p>
          )}
        </div>
        <div className="flex shrink-0 flex-col items-end gap-1">
          {uploaded && (
            <div className="flex items-center gap-1">
              <a
                href={getShipmentDocUrl(shipmentId, docType)}
                target="_blank"
                rel="noopener noreferrer"
                className="rounded-md bg-emerald-100 px-2.5 py-1 text-xs font-medium text-emerald-700 hover:bg-emerald-200"
              >
                View
              </a>
              <a
                href={getShipmentDocUrl(shipmentId, docType)}
                download={slot?.filename || true}
                className="rounded-md bg-slate-100 px-2.5 py-1 text-xs font-medium text-slate-600 hover:bg-slate-200"
                title="Download"
              >
                ↓
              </a>
            </div>
          )}
          <button
            type="button"
            disabled={uploading}
            onClick={() => fileRef.current?.click()}
            className={`rounded-md px-2.5 py-1 text-xs font-medium transition-colors ${
              uploaded
                ? "bg-slate-100 text-slate-600 hover:bg-slate-200"
                : "bg-teal-600 text-white hover:bg-teal-700"
            } disabled:opacity-60`}
          >
            {uploading ? "Uploading…" : uploaded ? "Replace" : "Upload"}
          </button>
        </div>
      </div>
      {error && <p className="mt-2 text-xs text-red-600">{error}</p>}
      <input
        ref={fileRef}
        type="file"
        className="hidden"
        onChange={handleFileChange}
        accept=".pdf,.png,.jpg,.jpeg,.xlsx,.xls,.docx,.doc"
      />
    </div>
  );
}

export function ShipmentPage() {
  const { shipmentId } = useParams<{ shipmentId: string }>();
  const { logout } = useAuth();
  const navigate = useNavigate();

  const [shipment, setShipment] = useState<Shipment | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [confirmDelete, setConfirmDelete] = useState(false);
  const [deleting, setDeleting] = useState(false);

  const handleDelete = async () => {
    if (!shipmentId) return;
    setDeleting(true);
    try {
      await deleteShipment(shipmentId);
      navigate("/admin");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to delete");
      setDeleting(false);
      setConfirmDelete(false);
    }
  };

  const fetchShipment = useCallback(async () => {
    if (!shipmentId) return;
    setLoading(true);
    setError(null);
    try {
      const s = await getShipment(shipmentId);
      setShipment(s);
    } catch (err) {
      if (err instanceof Error && err.message.includes("401")) {
        logout();
        navigate("/login");
      }
      setError(err instanceof Error ? err.message : "Failed to load shipment");
    } finally {
      setLoading(false);
    }
  }, [shipmentId, logout, navigate]);

  useEffect(() => { fetchShipment(); }, [fetchShipment]);

  const handleUploaded = (docType: DocType, all_uploaded: boolean) => {
    setShipment(prev => {
      if (!prev) return prev;
      return {
        ...prev,
        all_uploaded,
        docs: {
          ...prev.docs,
          [docType]: { ...prev.docs?.[docType], uploaded: true },
        },
      };
    });
  };

  if (!shipmentId) return <div className="page-container text-sm text-slate-600">Missing shipment id.</div>;

  const uploadedCount = shipment ? DOC_TYPES.filter(dt => shipment.docs?.[dt]?.uploaded).length : 0;

  return (
    <DashboardLayout
      title={shipment ? `${shipment.buyer_name} – ${shipment.product_name}` : "Shipment"}
      subtitle={shipment?.quotation_no ? `Quotation: ${shipment.quotation_no}` : "Shipment document tracking"}
    >
      <div className="space-y-4">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <Link to="/admin" className="btn-ghost btn-sm">← Admin Dashboard</Link>
          {confirmDelete ? (
            <div className="flex items-center gap-2">
              <span className="text-xs font-medium text-red-600">Delete this entry?</span>
              <button
                type="button"
                disabled={deleting}
                onClick={handleDelete}
                className="rounded-md bg-red-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-red-700 disabled:opacity-60"
              >
                {deleting ? "Deleting…" : "Yes, delete"}
              </button>
              <button
                type="button"
                onClick={() => setConfirmDelete(false)}
                className="rounded-md bg-slate-100 px-3 py-1.5 text-xs font-medium text-slate-600 hover:bg-slate-200"
              >
                Cancel
              </button>
            </div>
          ) : (
            <button
              type="button"
              onClick={() => setConfirmDelete(true)}
              className="rounded-md px-3 py-1.5 text-xs font-medium text-red-400 hover:bg-red-50 hover:text-red-600"
            >
              Delete entry
            </button>
          )}
        </div>

        {/* Status bar */}
        {shipment && (
          <div className={`flex items-center justify-between rounded-xl border px-5 py-4 ${shipment.all_uploaded ? "border-emerald-200 bg-emerald-50" : "border-amber-200 bg-amber-50"}`}>
            <div>
              <p className={`text-sm font-semibold ${shipment.all_uploaded ? "text-emerald-800" : "text-amber-800"}`}>
                {shipment.all_uploaded ? "All documents uploaded — Complete" : `Pending — ${uploadedCount}/7 documents uploaded`}
              </p>
              <p className="text-xs text-slate-500">
                {shipment.all_uploaded ? "This shipment is fully documented." : "Upload all 7 documents to mark this shipment as complete."}
              </p>
            </div>
            <div className={`text-2xl font-bold ${shipment.all_uploaded ? "text-emerald-600" : "text-amber-600"}`}>
              {uploadedCount}/7
            </div>
          </div>
        )}

        {error && <div className="alert-error">{error}</div>}

        {loading ? (
          <div className="flex min-h-[200px] items-center justify-center">
            <div className="h-8 w-8 animate-spin rounded-full border-2 border-teal-500 border-t-transparent" />
          </div>
        ) : shipment ? (
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {DOC_TYPES.map((dt) => (
              <DocCard
                key={dt}
                docType={dt}
                slot={shipment.docs?.[dt]}
                shipmentId={shipmentId}
                onUploaded={handleUploaded}
              />
            ))}
          </div>
        ) : null}
      </div>
    </DashboardLayout>
  );
}
