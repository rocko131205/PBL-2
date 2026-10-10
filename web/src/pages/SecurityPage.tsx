import { useState, type FormEvent } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { KeyRound, LogOut, ShieldCheck, ShieldOff } from "lucide-react";
import { Alert, Button, Card, Field, Spinner } from "@/components/ui";
import { api, ApiError } from "@/lib/api";
import { parseUtc } from "@/lib/analysis";

export interface AuditEvent { timestamp: string; event: string; outcome: string; email: string; ip: string; detail: string }
interface Overview { mfa_enabled: boolean; active_sessions: number; activity: AuditEvent[] }

const msg = (e: unknown) => (e instanceof ApiError ? e.message : "Something went wrong.");

export default function SecurityPage() {
  const q = useQuery({ queryKey: ["security"], queryFn: () => api<Overview>("/security") });
  if (q.isPending) return <Spinner label="Loading security settings" />;
  if (q.isError) return <Alert tone="risk">{msg(q.error)}</Alert>;
  const d = q.data;
  return (
    <div className="space-y-6 pb-10">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">Security settings</h1>
        <p className="text-sm text-ink-3">Two-factor authentication, sessions and recent account activity.</p>
      </div>
      <Mfa enabled={d.mfa_enabled} />
      <Sessions count={d.active_sessions} />
      <Card className="overflow-hidden">
        <div className="p-5 sm:p-6">
          <h2 className="font-semibold">Recent account activity</h2>
          <p className="text-sm text-ink-3">Review this for sign-ins you don't recognise.</p>
        </div>
        <EventsTable events={d.activity} empty="No activity recorded yet." />
      </Card>
    </div>
  );
}

function Mfa({ enabled }: { enabled: boolean }) {
  const qc = useQueryClient();
  const [setup, setSetup] = useState<{ secret: string; qr_png: string; enrol_token: string } | null>(null);
  const [code, setCode] = useState("");
  const [busy, setBusy] = useState(false);
  const [note, setNote] = useState<{ tone: "good" | "risk"; text: string } | null>(null);

  const call = async (fn: () => Promise<unknown>, success?: string) => {
    setBusy(true); setNote(null);
    try {
      await fn();
      if (success) setNote({ tone: "good", text: success });
      qc.invalidateQueries({ queryKey: ["security"] });
    } catch (e) { setNote({ tone: "risk", text: msg(e) }); } finally { setBusy(false); }
  };

  const confirm = (e: FormEvent) => {
    e.preventDefault();
    call(async () => {
      await api("/security/mfa/confirm", { json: { enrol_token: setup!.enrol_token, code } });
      setSetup(null); setCode("");
    }, "Two-factor authentication is now enabled.");
  };
  const disable = (e: FormEvent) => {
    e.preventDefault();
    call(async () => { await api("/security/mfa/disable", { json: { code } }); setCode(""); }, "Two-factor authentication has been disabled.");
  };

  return (
    <Card className="p-5 sm:p-6">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div className="flex gap-3">
          {enabled ? <ShieldCheck className="size-6 text-good" aria-hidden /> : <ShieldOff className="size-6 text-watch" aria-hidden />}
          <div>
            <h2 className="font-semibold">Two-factor authentication</h2>
            <p className="text-sm text-ink-3">Protects your account even if your password leaks. Works with Google Authenticator, Microsoft Authenticator, Authy or 1Password.</p>
          </div>
        </div>
        <span className={enabled ? "rounded-full bg-good-bg px-3 py-1 text-xs font-semibold text-good" : "rounded-full bg-watch-bg px-3 py-1 text-xs font-semibold text-watch"}>
          {enabled ? "Enabled" : "Not enabled"}
        </span>
      </div>

      <div className="mt-5 space-y-4">
        {note && <Alert tone={note.tone}>{note.text}</Alert>}
        {enabled ? (
          <form onSubmit={disable} className="flex max-w-md flex-col gap-3 sm:flex-row sm:items-end">
            <div className="flex-1"><Field label="Current code to disable" inputMode="numeric" maxLength={6} autoComplete="one-time-code" value={code} onChange={(e) => setCode(e.target.value)} /></div>
            <Button type="submit" variant="danger" loading={busy} disabled={code.length < 6}>Disable</Button>
          </form>
        ) : setup ? (
          <div className="grid gap-6 md:grid-cols-[auto_1fr]">
            <img src={`data:image/png;base64,${setup.qr_png}`} alt="QR code to scan with your authenticator app" className="size-48 rounded-2xl bg-white p-2" />
            <div className="space-y-4">
              <div>
                <div className="text-sm text-ink-2">Can't scan? Enter this key manually:</div>
                <code className="num mt-1 block break-all rounded-xl bg-black/40 px-3 py-2 text-sm">{setup.secret}</code>
              </div>
              <form onSubmit={confirm} className="flex max-w-md flex-col gap-3 sm:flex-row sm:items-end">
                <div className="flex-1"><Field label="6-digit code from the app" inputMode="numeric" maxLength={6} autoComplete="one-time-code" value={code} onChange={(e) => setCode(e.target.value)} autoFocus /></div>
                <Button type="submit" loading={busy} disabled={code.length < 6}>Verify & enable</Button>
              </form>
              <Button variant="ghost" onClick={() => { setSetup(null); setCode(""); setNote(null); }}>Cancel setup</Button>
            </div>
          </div>
        ) : (
          <Button loading={busy} onClick={() => call(async () => setSetup(await api("/security/mfa/begin", { method: "POST" })))}>
            <KeyRound className="size-4" aria-hidden /> Set up two-factor authentication
          </Button>
        )}
      </div>
    </Card>
  );
}

function Sessions({ count }: { count: number }) {
  const qc = useQueryClient();
  const [busy, setBusy] = useState(false);
  const [note, setNote] = useState<{ tone: "good" | "risk"; text: string } | null>(null);
  const revoke = async () => {
    setBusy(true); setNote(null);
    try {
      const r = await api<{ revoked: number }>("/security/sessions/revoke-others", { method: "POST" });
      setNote({ tone: "good", text: `Signed out ${r.revoked} other session${r.revoked === 1 ? "" : "s"}.` });
      qc.invalidateQueries({ queryKey: ["security"] });
    } catch (e) { setNote({ tone: "risk", text: msg(e) }); } finally { setBusy(false); }
  };
  return (
    <Card className="p-5 sm:p-6">
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <h2 className="font-semibold">Sessions</h2>
          <p className="text-sm text-ink-3">Sessions expire after 8 hours, or after 15 minutes of inactivity.</p>
          <p className="mt-2 text-sm">Active sessions: <b className="num">{count}</b></p>
        </div>
        <Button variant="secondary" loading={busy} disabled={count <= 1} onClick={revoke}><LogOut className="size-4" aria-hidden /> Sign out all other sessions</Button>
      </div>
      {note && <div className="mt-4"><Alert tone={note.tone}>{note.text}</Alert></div>}
    </Card>
  );
}

export function EventsTable({ events, empty }: { events: AuditEvent[]; empty: string }) {
  if (events.length === 0) return <p className="px-6 pb-6 text-sm text-ink-3">{empty}</p>;
  return (
    <div className="max-h-[32rem] overflow-auto border-t border-line">
      <table className="w-full text-sm">
        <thead className="sticky top-0 bg-surface-solid text-left text-xs text-ink-3">
          <tr><th className="px-5 py-2.5 font-medium">Time</th><th className="px-3 py-2.5 font-medium">Event</th><th className="px-3 py-2.5 font-medium">Outcome</th><th className="px-3 py-2.5 font-medium">Email</th><th className="px-3 py-2.5 font-medium">IP</th><th className="px-5 py-2.5 font-medium">Detail</th></tr>
        </thead>
        <tbody>
          {events.map((e, i) => (
            <tr key={i} className="border-t border-line/60">
              <td className="num whitespace-nowrap px-5 py-2 text-xs text-ink-3">{parseUtc(e.timestamp)?.toLocaleString() ?? "—"}</td>
              <td className="px-3 py-2">{e.event.replace(/_/g, " ")}</td>
              <td className="px-3 py-2"><span className={e.outcome === "failure" ? "text-risk" : "text-good"}>{e.outcome}</span></td>
              <td className="px-3 py-2 text-ink-2">{e.email || "—"}</td>
              <td className="num px-3 py-2 text-xs text-ink-3">{e.ip || "—"}</td>
              <td className="num px-5 py-2 text-xs text-ink-3">{e.detail || "—"}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
