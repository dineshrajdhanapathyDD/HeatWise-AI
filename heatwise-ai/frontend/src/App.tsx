import { MotionConfig } from "framer-motion";
import { Link, Navigate, Route, Routes } from "react-router-dom";

import { AppShell } from "./components/AppShell";
import { HealthProvider } from "./components/HealthProvider";
import { ToastProvider } from "./components/Toast";
import { AssessForm } from "./routes/AssessForm";
import { History } from "./routes/History";
import { Impact } from "./routes/Impact";
import { JobProgress } from "./routes/JobProgress";
import { Landing } from "./routes/Landing";
import { ActivityView } from "./routes/report/ActivityView";
import { ClimateView } from "./routes/report/ClimateView";
import { PlanView } from "./routes/report/PlanView";
import { ReportLayout } from "./routes/report/ReportLayout";
import { RiskView } from "./routes/report/RiskView";

function NotFound() {
  return (
    <>
      <h1 className="text-title font-semibold">Page not found</h1>
      <p className="mt-2 text-body text-muted">
        There is nothing at this address.{" "}
        <Link to="/" className="text-ink underline">
          Go to the home screen
        </Link>
        .
      </p>
    </>
  );
}

export default function App() {
  return (
    <MotionConfig reducedMotion="user">
      <HealthProvider>
        <ToastProvider>
        <Routes>
          <Route element={<AppShell />}>
            <Route index element={<Landing />} />
            <Route path="assess" element={<AssessForm />} />
            <Route path="assessments/:jobId" element={<JobProgress />} />
            <Route path="reports/:reportId" element={<ReportLayout />}>
              <Route index element={<Navigate to="climate" replace />} />
              <Route path="climate" element={<ClimateView />} />
              <Route path="risk" element={<RiskView />} />
              <Route path="plan" element={<PlanView />} />
              <Route path="activity" element={<ActivityView />} />
            </Route>
            <Route path="history" element={<History />} />
            <Route path="impact" element={<Impact />} />
            <Route path="*" element={<NotFound />} />
          </Route>
        </Routes>
        </ToastProvider>
      </HealthProvider>
    </MotionConfig>
  );
}
