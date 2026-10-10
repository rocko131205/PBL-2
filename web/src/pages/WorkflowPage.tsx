import { useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { Background, Controls, ReactFlow, MarkerType, Position, type Edge, type Node } from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import { Bot, Calculator, Lock } from "lucide-react";
import clsx from "clsx";
import { Card } from "@/components/ui";
import { useCurrentAnalysis, type Stage } from "@/lib/analysis";

type Kind = "source" | "normalize" | "deterministic" | "agent" | "output";

interface Info { title: string; kind: Kind; what: string; guardrail?: string }

/* What each node does, and the rule that keeps it honest (ported from the old guardrails panel). */
const INFO: Record<string, Info> = {
  pdf: { title: "Bloomberg PDF", kind: "source", what: "Income statement and balance sheet PDFs, parsed by the OCR extractor." },
  ticker: { title: "Listed ticker", kind: "source", what: "Annual statements fetched from Yahoo Finance, with optional FMP cross-checks." },
  csv: { title: "Private company CSV", kind: "source", what: "A CSV or Excel file supplied by the analyst." },
  normalize: { title: "Normalisation layer", kind: "normalize", what: "Maps every source into one company record with consistent fields, periods and currency.",
    guardrail: "Uploads are validated by size and real file type before any parser touches them." },
  company_intelligence: { title: "Company intelligence", kind: "agent", what: "Classifies the company: industry, country and software sub-type.",
    guardrail: "The company name is treated as untrusted data, never as instructions. It falls back to safe defaults if the model fails." },
  financial_computation: { title: "Financial computation", kind: "deterministic", what: "Computes profitability, liquidity, solvency, working capital, DSCR and the risk dashboard in pure Python.",
    guardrail: "Deterministic math lock: the LLM never sets a ratio, grade or default probability." },
  peer_analysis: { title: "Peer benchmarking", kind: "deterministic", what: "Finds comparable listed companies and fetches their actual metrics.",
    guardrail: "Only live, fetched data — no AI-estimated peer values." },
  qualitative_analysis: { title: "Qualitative analysis", kind: "agent", what: "Extracts credit-relevant points from management commentary.",
    guardrail: "Soft context only — it can't change any computed number. Prompt-injection attempts are screened out." },
  credit_assessment: { title: "Credit assessment", kind: "agent", what: "Synthesises strengths, risks and an explainable narrative from the computed facts.",
    guardrail: "Strictly prohibited from introducing new numbers or making the lending decision." },
  scorecard: { title: "Credit scorecard", kind: "output", what: "One industry-aware grade and default-probability band with a transparent factor breakdown." },
  dscr: { title: "Debt serviceability", kind: "output", what: "Year-by-year DSCR for a proposed loan, with stress tests." },
  memo: { title: "Credit memo", kind: "output", what: "A one-page, printable lender-style summary." },
};

const KIND_STYLE: Record<Kind, { border: string; label: string }> = {
  source: { border: "#ffffff29", label: "Data source" },
  normalize: { border: "#38bdf8", label: "Normalisation" },
  deterministic: { border: "#34d399", label: "Deterministic engine" },
  agent: { border: "#a78bfa", label: "AI agent (narrative only)" },
  output: { border: "#fbbf24", label: "Output" },
};

const STAGE_KEYS = ["company_intelligence", "financial_computation", "peer_analysis", "qualitative_analysis", "credit_assessment"];

function nodeStyle(kind: Kind, status?: Stage["status"], selected?: boolean) {
  const running = status === "running";
  return {
    background: "#0f141c",
    color: "#f6f3f8",
    border: `1.5px solid ${status === "done" ? "#34d399" : running ? "#60a5fa" : KIND_STYLE[kind].border}`,
    borderRadius: 14,
    padding: "12px 14px",
    fontSize: 13,
    width: 180,
    boxShadow: selected ? "0 0 0 3px #3b82f655" : running ? "0 0 24px -4px #60a5fa" : "none",
  };
}

export default function WorkflowPage() {
  const current = useCurrentAnalysis();
  const [selected, setSelected] = useState("financial_computation");
  const stages = current.data && current.data.status !== "none" ? current.data.stages : [];
  const statusOf = (k: string) => stages.find((s) => s.key === k)?.status;

  const { nodes, edges } = useMemo(() => {
    // Two-row "snake" so the graph stays readable at normal zoom:
    // row 1 runs left→right (sources → normalisation → first stages), row 2 comes back right→left to the outputs.
    const R = Position.Right, L = Position.Left, T = Position.Top, B = Position.Bottom;
    const layout: Record<string, { x: number; y: number; src: Position; tgt: Position }> = {
      pdf: { x: 0, y: -100, src: R, tgt: L }, ticker: { x: 0, y: 0, src: R, tgt: L }, csv: { x: 0, y: 100, src: R, tgt: L },
      normalize: { x: 240, y: 0, src: R, tgt: L },
      company_intelligence: { x: 460, y: 0, src: R, tgt: L },
      financial_computation: { x: 680, y: 0, src: R, tgt: L },
      peer_analysis: { x: 900, y: 0, src: B, tgt: L },
      qualitative_analysis: { x: 900, y: 240, src: L, tgt: T },
      credit_assessment: { x: 660, y: 240, src: L, tgt: R },
      scorecard: { x: 340, y: 150, src: L, tgt: R }, dscr: { x: 340, y: 240, src: L, tgt: R }, memo: { x: 340, y: 330, src: L, tgt: R },
    };
    const nodes: Node[] = Object.entries(layout).map(([id, { x, y, src, tgt }]) => {
      const info = INFO[id];
      const status = STAGE_KEYS.includes(id) ? statusOf(id) : undefined;
      return {
        id, position: { x, y }, draggable: false, connectable: false, sourcePosition: src, targetPosition: tgt,
        data: { label: <div><div style={{ fontWeight: 600, fontSize: 13 }}>{info.title}</div><div style={{ color: "#8590a0", fontSize: 11, marginTop: 2 }}>{status ? status : KIND_STYLE[info.kind].label}</div></div> },
        style: nodeStyle(info.kind, status, selected === id),
      };
    });
    const link = (s: string, t: string, color = "#ffffff40"): Edge => ({
      id: `${s}-${t}`, source: s, target: t, animated: statusOf(t) === "running",
      style: { stroke: color, strokeWidth: 1.5 }, markerEnd: { type: MarkerType.ArrowClosed, color },
    });
    const chain = ["normalize", ...STAGE_KEYS];
    const edges: Edge[] = [
      link("pdf", "normalize"), link("ticker", "normalize"), link("csv", "normalize"),
      ...chain.slice(0, -1).map((k, i) => link(k, chain[i + 1], "#60a5fa")),
      link("credit_assessment", "scorecard", "#fbbf24"), link("credit_assessment", "dscr", "#fbbf24"), link("credit_assessment", "memo", "#fbbf24"),
    ];
    return { nodes, edges };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selected, JSON.stringify(stages)]);

  const info = INFO[selected];
  const status = statusOf(selected);

  return (
    <div className="space-y-6 pb-10">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">Agent workflow</h1>
        <p className="text-sm text-ink-3">
          How a statement becomes a credit assessment. Select a step to see what it does and the guardrail that constrains it.
          {stages.length === 0 && <> <Link to="/upload" className="text-brand-700 hover:underline">Run an analysis</Link> to see live progress here.</>}
        </p>
      </div>

      <Card className="h-[30rem] overflow-hidden p-0">
        <ReactFlow
          nodes={nodes} edges={edges} fitView fitViewOptions={{ padding: 0.08 }} colorMode="dark"
          nodesDraggable={false} nodesConnectable={false} elementsSelectable minZoom={0.3} maxZoom={1.5}
          onNodeClick={(_, n) => setSelected(n.id)} proOptions={{ hideAttribution: true }}
          style={{ background: "transparent" }}
        >
          <Background color="#ffffff14" gap={22} />
          <Controls showInteractive={false} />
        </ReactFlow>
      </Card>

      <div className="flex flex-wrap gap-3 text-xs text-ink-3">
        {Object.entries(KIND_STYLE).map(([k, s]) => (
          <span key={k} className="inline-flex items-center gap-1.5"><span className="size-2.5 rounded-sm border-2" style={{ borderColor: s.border }} />{s.label}</span>
        ))}
      </div>

      <Card className="p-5 sm:p-6" aria-live="polite">
        <div className="flex flex-wrap items-center gap-3">
          {info.kind === "agent" ? <Bot className="size-5 text-violet-300" aria-hidden /> : <Calculator className="size-5 text-brand-700" aria-hidden />}
          <h2 className="font-semibold">{info.title}</h2>
          <span className="rounded-full bg-white/10 px-2.5 py-0.5 text-xs text-ink-2">{KIND_STYLE[info.kind].label}</span>
          {status && <span className={clsx("rounded-full px-2.5 py-0.5 text-xs font-medium", status === "done" ? "bg-good-bg text-good" : status === "running" ? "bg-brand-50 text-brand-700" : "bg-white/10 text-ink-3")}>{status}</span>}
        </div>
        <p className="mt-3 text-sm text-ink-2">{info.what}</p>
        {info.guardrail && (
          <div className="mt-4 flex gap-2.5 rounded-xl bg-black/25 p-4 text-sm">
            <Lock className="mt-0.5 size-4 shrink-0 text-good" aria-hidden />
            <div><div className="font-medium">Guardrail</div><div className="text-ink-2">{info.guardrail}</div></div>
          </div>
        )}
      </Card>
    </div>
  );
}
