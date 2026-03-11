import { Route, Routes } from "react-router-dom";
import { ActiveJobProvider } from "./context/ActiveJobContext";
import { Header } from "./components/layout/Header";
import { ErrorBoundary } from "./components/ui/ErrorBoundary";
import { UploadPage } from "./routes/UploadPage";
import { PreviewPage } from "./routes/PreviewPage";
import { GeneratePage } from "./routes/GeneratePage";
import { DocumentsListPage } from "./routes/DocumentsListPage";
import { EditorPage } from "./routes/EditorPage";
import { BatchDetailPage } from "./routes/BatchDetailPage";
import { TermsPage } from "./routes/TermsPage";

function App() {
  return (
    <ActiveJobProvider>
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
              <Route path="/documents/:id" element={<EditorPage />} />
              <Route path="/terms" element={<TermsPage />} />
            </Routes>
          </ErrorBoundary>
        </main>
      </div>
    </ActiveJobProvider>
  );
}

export default App;

