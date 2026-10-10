import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import clsx from "clsx";
import { Alert, Card, Spinner } from "@/components/ui";
import { api, ApiError } from "@/lib/api";
import { EventsTable, type AuditEvent } from "./SecurityPage";

interface Dashboard {
  counts: { login_success: number; login_failure: number; lockouts: number; otp_failures: number; prompt_injection: number };
  active_sessions: number;
  top_accounts: { email: string; failures: number; distinct_ips: number }[];
  top_ips: { ip: string; events: number; accounts: number }[];
  events: AuditEvent[];
}

export default function AdminSecurityPage() {
  const [failuresOnly, setFailuresOnly] = useState(true);
  const q = useQuery({
    queryKey: ["admin-security", failuresOnly],
    queryFn: () => api<Dashboard>(`/admin/security?failures_only=${failuresOnly}`),
    refetchInterval: 30_000,
  });
  if (q.isPending) return <Spinner label="Loading dashboard" />;
  if (q.isError) return <Alert tone="risk">{q.error instanceof ApiError ? q.error.message : "Couldn't load the dashboard."}</Alert>;
  const d = q.data;
  const tiles = [
    ["Successful logins", d.counts.login_success, "text-good"], ["Failed logins", d.counts.login_failure, "text-risk"],
    ["Lockouts", d.counts.lockouts, "text-watch"], ["OTP failures", d.counts.otp_failures, "text-watch"],
    ["Prompt-injection hits", d.counts.prompt_injection, "text-risk"], ["Active sessions", d.active_sessions, "text-info"],
  ] as const;

  return (
    <div className="space-y-6 pb-10">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">Security dashboard</h1>
        <p className="text-sm text-ink-3">Authentication and abuse signals across all users in the last 24 hours. Refreshes every 30 seconds.</p>
      </div>
      <div className="grid grid-cols-2 gap-4 md:grid-cols-3 xl:grid-cols-6">
        {tiles.map(([label, value, cls]) => (
          <Card key={label} className="p-5"><div className="text-xs text-ink-3">{label}</div><div className={clsx("num mt-1 text-3xl font-semibold", value === 0 ? "text-ink" : cls)}>{value}</div></Card>
        ))}
      </div>
      <div className="grid gap-4 xl:grid-cols-2">
        <SmallTable title="Most-targeted accounts (failed logins)" empty="No failed logins in the last 24 hours."
          head={["Email", "Failures", "Distinct IPs"]} rows={d.top_accounts.map((t) => [t.email, t.failures, t.distinct_ips])}
          hint="Many IPs against one account suggests a distributed brute-force attempt." />
        <SmallTable title="Top source IPs (failures)" empty="No failures with a known IP."
          head={["IP", "Failure events", "Accounts targeted"]} rows={d.top_ips.map((t) => [t.ip, t.events, t.accounts])}
          hint="Many accounts from one IP suggests credential stuffing." />
      </div>
      <Card className="overflow-hidden">
        <div className="flex flex-wrap items-center justify-between gap-3 p-5 sm:p-6">
          <h2 className="font-semibold">Recent security events</h2>
          <label className="flex items-center gap-2 text-sm text-ink-2">
            <input type="checkbox" checked={failuresOnly} onChange={(e) => setFailuresOnly(e.target.checked)} className="size-4 accent-[#3b82f6]" />
            Failures only
          </label>
        </div>
        <EventsTable events={d.events} empty="No events recorded." />
      </Card>
    </div>
  );
}

function SmallTable({ title, head, rows, empty, hint }: { title: string; head: string[]; rows: (string | number)[][]; empty: string; hint: string }) {
  return (
    <Card className="overflow-hidden">
      <h2 className="px-5 pt-5 font-semibold sm:px-6">{title}</h2>
      {rows.length === 0 ? <p className="px-6 py-5 text-sm text-ink-3">{empty}</p> : (
        <table className="mt-3 w-full text-sm">
          <thead className="text-left text-xs text-ink-3"><tr className="border-b border-line">{head.map((h, i) => <th key={h} className={clsx("px-5 py-2.5 font-medium", i > 0 && "text-right")}>{h}</th>)}</tr></thead>
          <tbody>{rows.map((r, i) => <tr key={i} className="border-b border-line/60 last:border-0">{r.map((c, j) => <td key={j} className={clsx("px-5 py-2.5", j > 0 && "num text-right")}>{c}</td>)}</tr>)}</tbody>
        </table>
      )}
      <p className="px-5 pb-5 pt-3 text-xs text-ink-3 sm:px-6">{hint}</p>
    </Card>
  );
}
