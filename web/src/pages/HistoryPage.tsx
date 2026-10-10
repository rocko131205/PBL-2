import { Link } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { FileText, History } from "lucide-react";
import clsx from "clsx";
import { Alert, Card, Spinner } from "@/components/ui";
import { api, ApiError } from "@/lib/api";
import { parseUtc } from "@/lib/analysis";

interface Row {
  id: string; analysis_id: string | null; entity_name: string; source_type: string; source_label: string;
  credibility_score: number | null; fields_loaded: string[]; timestamp: string;
}

const SOURCE: Record<string, { label: string; cls: string }> = {
  pdf: { label: "PDF", cls: "bg-brand-50 text-brand-700" },
  ticker: { label: "Ticker", cls: "bg-info-bg text-info" },
  csv: { label: "CSV", cls: "bg-good-bg text-good" },
};
const scoreTone = (s: number | null) => (s == null ? "text-ink-3" : s >= 75 ? "text-good" : s >= 50 ? "text-watch" : "text-risk");

export default function HistoryPage() {
  const q = useQuery({ queryKey: ["history"], queryFn: () => api<Row[]>("/history") });

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">My file history</h1>
        <p className="text-sm text-ink-3">Every analysis you've completed, newest first.</p>
      </div>
      {q.isPending ? <Spinner label="Loading history" />
        : q.isError ? <Alert tone="risk">{q.error instanceof ApiError ? q.error.message : "Couldn't load your history."}</Alert>
          : q.data.length === 0 ? (
            <Card className="p-10 text-center">
              <History className="mx-auto size-8 text-ink-3" aria-hidden />
              <p className="mt-3 text-sm text-ink-2">No analyses yet.</p>
              <Link to="/upload" className="mt-2 inline-block text-sm font-medium text-brand-700 hover:underline">Load data and run your first analysis</Link>
            </Card>
          ) : (
            <Card className="overflow-hidden">
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead className="text-left text-xs text-ink-3">
                    <tr className="border-b border-line">
                      <th className="px-5 py-3 font-medium">Company</th>
                      <th className="px-3 py-3 font-medium">Source</th>
                      <th className="px-3 py-3 font-medium">Dataset</th>
                      <th className="px-3 py-3 text-right font-medium">Credibility</th>
                      <th className="px-5 py-3 text-right font-medium">Date</th>
                    </tr>
                  </thead>
                  <tbody>
                    {q.data.map((r) => {
                      const s = SOURCE[r.source_type] ?? { label: r.source_type, cls: "bg-white/10 text-ink-2" };
                      const when = parseUtc(r.timestamp);
                      return (
                        <tr key={r.id} className="border-b border-line/60 last:border-0 hover:bg-white/[0.03]">
                          <td className="px-5 py-3.5">
                            <div className="flex items-center gap-2.5 font-medium"><FileText className="size-4 text-ink-3" aria-hidden />{r.entity_name}</div>
                            <div className="mt-0.5 pl-6.5 text-xs text-ink-3">{r.fields_loaded.length} fields</div>
                          </td>
                          <td className="px-3 py-3.5"><span className={clsx("rounded-full px-2.5 py-0.5 text-xs font-medium", s.cls)}>{s.label}</span></td>
                          <td className="px-3 py-3.5 text-ink-2">{r.source_label}</td>
                          <td className={clsx("num px-3 py-3.5 text-right font-medium", scoreTone(r.credibility_score))}>{r.credibility_score ?? "—"}</td>
                          <td className="px-5 py-3.5 text-right text-ink-3">{when ? when.toLocaleString() : "—"}</td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            </Card>
          )}
    </div>
  );
}
