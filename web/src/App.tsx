import { lazy, Suspense, useEffect } from "react";
import { BrowserRouter, Navigate, Route, Routes, useLocation } from "react-router-dom";
import { QueryClient, QueryClientProvider, useQueryClient } from "@tanstack/react-query";
import { AuthProvider, useAuth } from "@/lib/auth";
import { AppLayout } from "@/layouts/AppLayout";
import { Spinner } from "@/components/ui";
import LoginPage from "@/pages/LoginPage";
import RegisterPage from "@/pages/RegisterPage";
import ForgotPasswordPage from "@/pages/ForgotPasswordPage";
import BaselPage from "@/pages/BaselPage";
import HistoryPage from "@/pages/HistoryPage";
import SecurityPage from "@/pages/SecurityPage";
import AdminSecurityPage from "@/pages/AdminSecurityPage";

// Charts and the flow graph are heavy; load them only when the page is opened.
const UploadPage = lazy(() => import("@/pages/upload/UploadPage"));
const AnalysisPage = lazy(() => import("@/pages/analysis/AnalysisPage"));
const WorkflowPage = lazy(() => import("@/pages/WorkflowPage"));

const queryClient = new QueryClient({
  defaultOptions: { queries: { retry: false, refetchOnWindowFocus: false } },
});

/** Drop every cached API response whenever the session ends, so the next person on this browser never sees the previous user's data. */
function ClearCacheOnSignOut() {
  const { user } = useAuth();
  const qc = useQueryClient();
  useEffect(() => { if (!user) qc.clear(); }, [user, qc]);
  return null;
}

function RequireAuth({ admin = false }: { admin?: boolean }) {
  const { user, loading } = useAuth();
  const location = useLocation();
  if (loading) return <Spinner label="Loading your workspace" />;
  if (!user) return <Navigate to="/login" replace state={{ from: location.pathname }} />;
  if (admin && !user.is_admin) return <Navigate to="/upload" replace />;
  return <AppLayout />;
}

export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <AuthProvider>
        <ClearCacheOnSignOut />
        <BrowserRouter>
          <Suspense fallback={<Spinner />}>
            <Routes>
              <Route path="/login" element={<LoginPage />} />
              <Route path="/register" element={<RegisterPage />} />
              <Route path="/forgot" element={<ForgotPasswordPage />} />

              <Route element={<RequireAuth />}>
                <Route path="/upload" element={<UploadPage />} />
                <Route path="/analysis" element={<AnalysisPage />} />
                <Route path="/workflow" element={<WorkflowPage />} />
                <Route path="/basel" element={<BaselPage />} />
                <Route path="/history" element={<HistoryPage />} />
                <Route path="/security" element={<SecurityPage />} />
              </Route>
              <Route element={<RequireAuth admin />}>
                <Route path="/admin/security" element={<AdminSecurityPage />} />
              </Route>

              <Route path="*" element={<Navigate to="/upload" replace />} />
            </Routes>
          </Suspense>
        </BrowserRouter>
      </AuthProvider>
    </QueryClientProvider>
  );
}
