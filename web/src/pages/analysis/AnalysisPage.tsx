import { Link } from "react-router-dom";
import { Play, RotateCw, Upload } from "lucide-react";
import { Alert, Button, Card, Spinner } from "@/components/ui";
import { ApiError } from "@/lib/api";
import { useAnalysis, useCurrentAnalysis, useStartAnalysis } from "@/lib/analysis";
import { RunProgress } from "./RunProgress";
import { ReportView } from "./ReportView";

export default function AnalysisPage() {
  const current = useCurrentAnalysis();
  const id = current.data && current.data.status !== "none" ? current.data.id : undefined;
  const done = current.data?.status === "done";
  const full = useAnalysis(done ? id : undefined);

  if (current.isPending) return <Spinner label="Loading analysis" />;
  if (current.isError) return <Alert tone="risk">{current.error instanceof ApiError ? current.error.message : "Couldn't load the analysis."}</Alert>;
  const c = current.data!;

  if (c.status === "none") return <Empty hasData={c.has_data} />;
  if (c.status === "queued" || c.status === "running") return <RunProgress stages={c.stages} entity={c.entity} />;
  if (c.status === "failed") return <Failed message={c.error ?? "The analysis failed."} />;

  if (full.isPending) return <Spinner label="Loading the report" />;
  if (full.isError || !full.data?.report) return <Alert tone="risk">Couldn't load the report. Try refreshing the page.</Alert>;
  return <ReportView analysis={full.data} report={full.data.report} />;
}

function RunButton({ label = "Run full analysis" }: { label?: string }) {
  const start = useStartAnalysis();
  return (
    <div className="space-y-3">
      <Button onClick={() => start.mutate()} loading={start.isPending}><Play className="size-4" aria-hidden /> {label}</Button>
      {start.isError && <Alert tone="risk">{start.error instanceof ApiError ? start.error.message : "Couldn't start the analysis."}</Alert>}
    </div>
  );
}

function Empty({ hasData }: { hasData: boolean }) {
  return (
    <Card className="mx-auto max-w-2xl p-8 text-center sm:p-10">
      <h1 className="text-xl font-semibold">{hasData ? "Ready to analyse" : "No data loaded yet"}</h1>
      <p className="mx-auto mt-2 max-w-md text-sm text-ink-2">
        {hasData
          ? "Your data is loaded. Run the analysis to get the credit grade, trends, debt-service coverage, peer benchmarks and a credit memo."
          : "Load a Bloomberg PDF, a listed ticker or a private-company CSV first."}
      </p>
      <div className="mt-6 flex justify-center">
        {hasData ? <RunButton /> : (
          <Link to="/upload" className="accent-gradient inline-flex h-11 items-center gap-2 rounded-full px-5 text-sm font-medium text-white">
            <Upload className="size-4" aria-hidden /> Go to Upload
          </Link>
        )}
      </div>
    </Card>
  );
}

function Failed({ message }: { message: string }) {
  return (
    <Card className="mx-auto max-w-2xl space-y-4 p-8">
      <h1 className="text-xl font-semibold">The analysis didn't finish</h1>
      <Alert tone="risk">{message}</Alert>
      <div className="flex flex-wrap gap-3">
        <RunButton label="Run again" />
        <Link to="/upload" className="inline-flex h-11 items-center gap-2 rounded-full border border-line-strong px-5 text-sm font-medium text-ink-2 hover:bg-white/10">
          <RotateCw className="size-4" aria-hidden /> Review the data
        </Link>
      </div>
    </Card>
  );
}
