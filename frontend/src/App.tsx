import { Navigate, Route, Routes } from "react-router-dom";
import { ActiveJobProvider } from "./context/ActiveJobContext";
import { AuthProvider, useAuth } from "./context/AuthContext";
import { Header } from "./components/layout/Header";
import { ErrorBoundary } from "./components/ui/ErrorBoundary";
import { UploadPage } from "./routes/UploadPage";
import { PreviewPage } from "./routes/PreviewPage";
import { GeneratePage } from "./routes/GeneratePage";
import { DocumentsListPage } from "./routes/DocumentsListPage";
import { EditorPage } from "./routes/EditorPage";
import { BatchDetailPage } from "./routes/BatchDetailPage";
import { InvoicesPage } from "./routes/InvoicesPage";
import { EditRowPage } from "./routes/EditRowPage";
import { TermsPage } from "./routes/TermsPage";
import { ManualDocPage } from "./routes/ManualDocPage";
import { LoginPage } from "./routes/LoginPage";
import { AdminDashboard } from "./routes/AdminDashboard";
import { ShipmentPage } from "./routes/ShipmentPage";
import { EmailSendPage } from "./routes/EmailSendPage";

function RequireAuth({ children }: { children: React.ReactNode }) {
  const { isAuthenticated, checking } = useAuth();
  // While the /api/auth/check request is in flight, show nothing to avoid a flash redirect
  if (checking) return null;
  return isAuthenticated ? <>{children}</> : <Navigate to="/login" replace />;
}

function AppRoutes() {
  return (
    <div className="min-h-screen bg-slate-50 text-slate-800">
      <Header />
      <main id="main-content" className="min-h-[60vh]">
        <ErrorBoundary>
          <Routes>
            <Route path="/" element={<UploadPage />} />
            <Route path="/preview" element={<PreviewPage />} />
            <Route path="/generate" element={<GeneratePage />} />
            <Route path="/documents" element={<DocumentsListPage />} />
            <Route path="/documents/engineering" element={<DocumentsListPage />} />
            <Route path="/documents/chemical" element={<DocumentsListPage />} />
            <Route path="/documents/batch/:batchId" element={<BatchDetailPage />} />
            <Route path="/documents/batch/:batchId/invoices" element={<InvoicesPage />} />
            <Route path="/documents/batch/:batchId/edit-row" element={<EditRowPage />} />
            <Route path="/documents/:id" element={<EditorPage />} />
            <Route path="/terms" element={<TermsPage />} />
            <Route path="/manual" element={<ManualDocPage />} />
            <Route path="/send-emails" element={<EmailSendPage />} />
            <Route path="/login" element={<LoginPage />} />
            <Route path="/admin" element={<RequireAuth><AdminDashboard /></RequireAuth>} />
            <Route path="/admin/shipment/:shipmentId" element={<RequireAuth><ShipmentPage /></RequireAuth>} />
          </Routes>
        </ErrorBoundary>
      </main>
    </div>
  );
}

function App() {
  return (
    <AuthProvider>
      <ActiveJobProvider>
        <AppRoutes />
      </ActiveJobProvider>
    </AuthProvider>
  );
}

export default App;

