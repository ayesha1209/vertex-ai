import { useCallback, useEffect, useState } from "react";
import { DashboardLayout } from "../components/layout/DashboardLayout";
import { getTerms, updateTerms } from "../lib/api";

export function TermsPage() {
  const [chemical, setChemical] = useState("");
  const [engineering, setEngineering] = useState("");
  const [editingChemical, setEditingChemical] = useState(false);
  const [editingEngineering, setEditingEngineering] = useState(false);
  const [savingChemical, setSavingChemical] = useState(false);
  const [savingEngineering, setSavingEngineering] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);

  const fetchTerms = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await getTerms();
      setChemical(res.chemical || "");
      setEngineering(res.engineering || "");
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Failed to load terms");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchTerms();
  }, [fetchTerms]);

  const handleSaveChemical = async () => {
    setSavingChemical(true);
    setError(null);
    setSuccess(null);
    try {
      await updateTerms({ chemical });
      setSuccess("Chemical terms saved. They will apply to all new Chemical documents.");
      setEditingChemical(false);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Failed to save Chemical terms");
    } finally {
      setSavingChemical(false);
    }
  };

  const handleSaveEngineering = async () => {
    setSavingEngineering(true);
    setError(null);
    setSuccess(null);
    try {
      await updateTerms({ engineering });
      setSuccess("Engineering terms saved. They will apply to all new Engineering documents.");
      setEditingEngineering(false);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Failed to save Engineering terms");
    } finally {
      setSavingEngineering(false);
    }
  };

  return (
    <DashboardLayout
      title="Terms and Conditions"
      subtitle="View or edit terms for Chemical and Engineering. Click Edit to change; Save applies to that section only. Changes apply to all new documents you generate."
    >
      <div className="space-y-6">
        <div className="rounded-lg border border-slate-200 bg-slate-50 px-4 py-3 text-sm text-slate-700">
          <p className="font-medium">View first, then Edit</p>
          <p className="mt-1 text-slate-600">Terms are shown in view mode. Click <strong>Edit</strong> on a section to change it, then <strong>Save</strong> that section. Each section (Chemical, Engineering) has its own Save button.</p>
        </div>
        {error && (
          <div className="alert-error" role="alert">
            {error}
          </div>
        )}
        {success && (
          <div className="rounded-lg border border-emerald-200 bg-emerald-50 px-4 py-3 text-sm text-emerald-800" role="status">
            {success}
          </div>
        )}

        {loading ? (
          <div className="flex min-h-[200px] items-center justify-center">
            <div className="h-8 w-8 animate-spin rounded-full border-2 border-teal-500 border-t-transparent" aria-hidden />
          </div>
        ) : (
          <>
            {/* Chemical */}
            <div className="card p-4 sm:p-6">
              <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
                <h2 className="text-sm font-semibold uppercase tracking-wide text-slate-600">Chemical</h2>
                {!editingChemical ? (
                  <button type="button" onClick={() => setEditingChemical(true)} className="btn-outline btn-sm">
                    Edit
                  </button>
                ) : (
                  <div className="flex gap-2">
                    <button type="button" onClick={() => setEditingChemical(false)} className="btn-ghost btn-sm">
                      Cancel
                    </button>
                    <button type="button" onClick={handleSaveChemical} disabled={savingChemical} className="btn-primary btn-sm">
                      {savingChemical ? "Saving…" : "Save"}
                    </button>
                  </div>
                )}
              </div>
              {editingChemical ? (
                <textarea
                  value={chemical}
                  onChange={(e) => setChemical(e.target.value)}
                  className="input min-h-[200px] w-full font-mono text-sm"
                  placeholder="Enter HTML or plain text terms for Chemical documents…"
                  rows={12}
                />
              ) : (
                <div className="min-h-[120px] rounded-lg border border-slate-200 bg-white px-3 py-3 text-sm text-slate-700 whitespace-pre-wrap">
                  {chemical ? chemical : <span className="text-slate-400">No terms set. Click Edit to add.</span>}
                </div>
              )}
            </div>

            {/* Engineering */}
            <div className="card p-4 sm:p-6">
              <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
                <h2 className="text-sm font-semibold uppercase tracking-wide text-slate-600">Engineering</h2>
                {!editingEngineering ? (
                  <button type="button" onClick={() => setEditingEngineering(true)} className="btn-outline btn-sm">
                    Edit
                  </button>
                ) : (
                  <div className="flex gap-2">
                    <button type="button" onClick={() => setEditingEngineering(false)} className="btn-ghost btn-sm">
                      Cancel
                    </button>
                    <button type="button" onClick={handleSaveEngineering} disabled={savingEngineering} className="btn-primary btn-sm">
                      {savingEngineering ? "Saving…" : "Save"}
                    </button>
                  </div>
                )}
              </div>
              {editingEngineering ? (
                <textarea
                  value={engineering}
                  onChange={(e) => setEngineering(e.target.value)}
                  className="input min-h-[200px] w-full font-mono text-sm"
                  placeholder="Enter HTML or plain text terms for Engineering documents…"
                  rows={12}
                />
              ) : (
                <div className="min-h-[120px] rounded-lg border border-slate-200 bg-white px-3 py-3 text-sm text-slate-700 whitespace-pre-wrap">
                  {engineering ? engineering : <span className="text-slate-400">No terms set. Click Edit to add.</span>}
                </div>
              )}
            </div>
          </>
        )}
      </div>
    </DashboardLayout>
  );
}
