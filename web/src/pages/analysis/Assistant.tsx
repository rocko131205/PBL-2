import { useEffect, useRef, useState, type FormEvent } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { Send, Sparkles } from "lucide-react";
import { Alert, Button, Card } from "@/components/ui";
import { api, ApiError } from "@/lib/api";
import type { QA } from "@/lib/analysis";

const SUGGESTIONS = ["Is leverage a concern?", "What's driving the risk level?", "How strong is cash flow?"];

export function AssistantSection({ analysisId, ai }: { analysisId: string; ai: { explain: string | null; qa: QA[] } }) {
  const qc = useQueryClient();
  const [explain, setExplain] = useState(ai.explain);
  const [qa, setQa] = useState<QA[]>(ai.qa);
  const [question, setQuestion] = useState("");
  const [busy, setBusy] = useState<"explain" | "ask" | null>(null);
  const [error, setError] = useState("");
  const end = useRef<HTMLDivElement>(null);

  useEffect(() => { end.current?.scrollIntoView({ block: "nearest" }); }, [qa.length]);

  const run = async (kind: "explain" | "ask", q?: string) => {
    setError("");
    setBusy(kind);
    try {
      if (kind === "explain") {
        const r = await api<{ text: string }>(`/analysis/${analysisId}/assistant/explain`, { method: "POST" });
        setExplain(r.text);
      } else {
        const r = await api<QA>(`/analysis/${analysisId}/assistant/ask`, { json: { question: q } });
        setQa((prev) => [...prev, r]);
        setQuestion("");
      }
      qc.invalidateQueries({ queryKey: ["analysis", analysisId] });
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "The assistant is unavailable right now.");
    } finally {
      setBusy(null);
    }
  };

  const ask = (e: FormEvent) => {
    e.preventDefault();
    if (question.trim()) run("ask", question.trim());
  };

  return (
    <Card className="p-5 sm:p-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <p className="max-w-xl text-sm text-ink-2">Answers use only the computed facts on this page. The assistant can't change any number and will say so if something isn't in the data.</p>
        <Button variant="secondary" onClick={() => run("explain")} loading={busy === "explain"}><Sparkles className="size-4" aria-hidden /> {explain ? "Explain again" : "Explain in plain English"}</Button>
      </div>

      {explain && (
        <div className="mt-5 rounded-2xl border border-brand-600/30 bg-brand-50 p-4 text-sm leading-relaxed whitespace-pre-line">{explain}</div>
      )}

      {qa.length > 0 && (
        <div className="mt-5 max-h-[28rem] space-y-4 overflow-y-auto pr-1" aria-live="polite">
          {qa.map((m, i) => (
            <div key={i} className="space-y-2">
              <div className="ml-auto w-fit max-w-[85%] rounded-2xl rounded-br-md bg-brand-600/30 px-4 py-2.5 text-sm">{m.q}</div>
              <div className="w-fit max-w-[90%] whitespace-pre-line rounded-2xl rounded-bl-md bg-white/[0.06] px-4 py-2.5 text-sm leading-relaxed text-ink-2">{m.a}</div>
            </div>
          ))}
          {busy === "ask" && <div className="w-fit rounded-2xl bg-white/[0.06] px-4 py-2.5 text-sm text-ink-3">Thinking…</div>}
          <div ref={end} />
        </div>
      )}

      {error && <div className="mt-4"><Alert tone="risk">{error}</Alert></div>}

      <form onSubmit={ask} className="mt-5 flex gap-2">
        <input value={question} onChange={(e) => setQuestion(e.target.value)} maxLength={1000} aria-label="Ask about this company"
          placeholder="Ask about this company…" disabled={busy !== null}
          className="h-11 flex-1 rounded-full border border-line-strong bg-black/30 px-4 text-sm placeholder:text-ink-3 focus:border-brand-600 focus:outline-none focus:ring-2 focus:ring-brand-600/30" />
        <Button type="submit" loading={busy === "ask"} disabled={!question.trim()} aria-label="Send question"><Send className="size-4" aria-hidden /></Button>
      </form>
      {qa.length === 0 && (
        <div className="mt-3 flex flex-wrap gap-2">
          {SUGGESTIONS.map((s) => (
            <button key={s} onClick={() => run("ask", s)} disabled={busy !== null}
              className="rounded-full border border-line-strong px-3 py-1 text-xs text-ink-2 hover:bg-white/[0.06] hover:text-ink disabled:opacity-50">{s}</button>
          ))}
        </div>
      )}
      <p className="mt-3 text-xs text-ink-3">Requires the LLM endpoint configured on the server to be running.</p>
    </Card>
  );
}
