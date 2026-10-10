import { useRef, useState, type DragEvent } from "react";
import { Download, FileText, Search, UploadCloud, X } from "lucide-react";
import clsx from "clsx";
import { Alert, Button, Card, Field, SelectField } from "@/components/ui";
import { api, ApiError } from "@/lib/api";
import type { SourceKind, Workspace } from "@/lib/types";
import { useWorkspaceMutation } from "@/lib/workspace";

const TABS: { key: SourceKind; label: string; hint: string }[] = [
  { key: "pdf", label: "Bloomberg PDF", hint: "Income statement + balance sheet" },
  { key: "ticker", label: "Listed ticker", hint: "Fetched via Yahoo Finance" },
  { key: "csv", label: "Private company CSV", hint: "CSV or Excel upload" },
];

const MAX_PDFS = 4;
const MAX_PDF_MB = 20;
const CURRENCIES = ["INR", "USD", "EUR", "GBP", "JPY", "SGD", "AED"];
const errMsg = (e: unknown) => (e instanceof ApiError ? e.message : "Something went wrong.");

export function SourcePicker({ active }: { active: SourceKind | null }) {
  const [tab, setTab] = useState<SourceKind>(active ?? "pdf");
  return (
    <Card className="p-5 sm:p-6">
      <div role="tablist" aria-label="Data source" className="flex flex-wrap gap-2">
        {TABS.map((t) => (
          <button
            key={t.key} role="tab" aria-selected={tab === t.key} onClick={() => setTab(t.key)}
            className={clsx("rounded-full px-4 py-2 text-sm font-medium transition",
              tab === t.key ? "accent-gradient text-white shadow-[0_8px_24px_-10px_#3b82f6]" : "border border-line-strong text-ink-2 hover:bg-white/[0.06] hover:text-ink")}
          >
            {t.label}
          </button>
        ))}
      </div>
      <p className="mt-3 text-xs text-ink-3">{TABS.find((t) => t.key === tab)!.hint}</p>
      <div className="mt-5" role="tabpanel">
        {tab === "pdf" && <PdfPanel />}
        {tab === "ticker" && <TickerPanel />}
        {tab === "csv" && <CsvPanel />}
      </div>
    </Card>
  );
}

/* ── PDF ────────────────────────────────────────────────────────────────── */

function PdfPanel() {
  const [files, setFiles] = useState<File[]>([]);
  const [problem, setProblem] = useState("");
  const [drag, setDrag] = useState(false);
  const input = useRef<HTMLInputElement>(null);
  const load = useWorkspaceMutation((fd: FormData) => api<Workspace>("/ingest/pdf", { form: fd }));

  const add = (incoming: FileList | File[]) => {
    const next = [...files];
    const issues: string[] = [];
    for (const f of Array.from(incoming)) {
      if (!f.name.toLowerCase().endsWith(".pdf")) issues.push(`${f.name} isn't a PDF.`);
      else if (f.size > MAX_PDF_MB * 1024 * 1024) issues.push(`${f.name} is larger than ${MAX_PDF_MB} MB.`);
      else if (next.length >= MAX_PDFS) issues.push(`Only ${MAX_PDFS} PDFs at a time.`);
      else if (!next.some((n) => n.name === f.name && n.size === f.size)) next.push(f);
    }
    setFiles(next);
    setProblem(issues.join(" "));
    load.reset();
  };
  const onDrop = (e: DragEvent) => { e.preventDefault(); setDrag(false); add(e.dataTransfer.files); };

  const submit = () => {
    const fd = new FormData();
    files.forEach((f) => fd.append("files", f));
    load.mutate(fd, { onSuccess: () => setFiles([]) });
  };

  return (
    <div className="space-y-4">
      <p className="text-sm text-ink-2">
        Upload <b className="text-ink">both</b> the Income Statement and the Balance Sheet PDF together to enable every agent.
        A single income statement enables the Revenue agent only.
      </p>
      <div
        onDragOver={(e) => { e.preventDefault(); setDrag(true); }} onDragLeave={() => setDrag(false)} onDrop={onDrop}
        className={clsx("rounded-2xl border border-dashed p-8 text-center transition", drag ? "border-brand-600 bg-brand-50" : "border-line-strong bg-black/20")}
      >
        <UploadCloud className="mx-auto size-8 text-brand-700" aria-hidden />
        <p className="mt-3 text-sm text-ink-2">Drag PDFs here, or</p>
        <Button type="button" variant="secondary" className="mt-3" onClick={() => input.current?.click()}>Choose files</Button>
        <input ref={input} type="file" accept=".pdf,application/pdf" multiple hidden
          onChange={(e) => { if (e.target.files) add(e.target.files); e.target.value = ""; }} aria-label="Choose PDF files" />
        <p className="mt-3 text-xs text-ink-3">Up to {MAX_PDFS} files · {MAX_PDF_MB} MB each</p>
      </div>

      {files.length > 0 && (
        <ul className="flex flex-wrap gap-2" aria-label="Selected files">
          {files.map((f) => (
            <li key={f.name + f.size} className="glass flex items-center gap-2 rounded-full py-1.5 pl-3 pr-1.5 text-sm">
              <FileText className="size-4 text-brand-700" aria-hidden />
              <span className="max-w-[14rem] truncate">{f.name}</span>
              <span className="num text-xs text-ink-3">{(f.size / 1024).toFixed(1)} KB</span>
              <button onClick={() => setFiles(files.filter((x) => x !== f))} aria-label={`Remove ${f.name}`}
                className="rounded-full p-1 text-ink-3 hover:bg-white/10 hover:text-ink"><X className="size-3.5" /></button>
            </li>
          ))}
        </ul>
      )}
      {problem && <Alert tone="watch">{problem}</Alert>}
      {load.isError && <Alert tone="risk">{errMsg(load.error)}</Alert>}
      <Button onClick={submit} disabled={files.length === 0} loading={load.isPending}>
        {load.isPending ? "Extracting data…" : `Extract data${files.length ? ` from ${files.length} PDF${files.length > 1 ? "s" : ""}` : ""}`}
      </Button>
    </div>
  );
}

/* ── Ticker ─────────────────────────────────────────────────────────────── */

const EXAMPLES = [["INFY.NS", "Infosys"], ["TCS.NS", "TCS"], ["AAPL", "Apple"]];
const TICKER_RE = /^\^?[A-Z0-9][A-Z0-9.\-=]{0,14}$/;

function TickerPanel() {
  const [ticker, setTicker] = useState("");
  const [local, setLocal] = useState("");
  const load = useWorkspaceMutation((t: string) => api<Workspace>("/ingest/ticker", { json: { ticker: t } }));

  const go = (e?: React.FormEvent) => {
    e?.preventDefault();
    const t = ticker.trim().toUpperCase();
    if (!t) return setLocal("Enter a ticker symbol first.");
    if (!TICKER_RE.test(t)) return setLocal("Use letters, digits, '.', '-' (e.g. INFY.NS, BRK-B).");
    setLocal("");
    load.mutate(t);
  };

  return (
    <form onSubmit={go} className="space-y-4" noValidate>
      <p className="text-sm text-ink-2">Enter a Yahoo Finance ticker to fetch the annual financial statements automatically.</p>
      <div className="flex flex-col gap-3 sm:flex-row sm:items-end">
        <div className="flex-1">
          <Field label="Ticker symbol" value={ticker} onChange={(e) => setTicker(e.target.value)} placeholder="e.g. INFY.NS, TCS.NS, AAPL"
            autoCapitalize="characters" spellCheck={false} error={local} />
        </div>
        <Button type="submit" loading={load.isPending} className="sm:mb-px"><Search className="size-4" aria-hidden /> Fetch data</Button>
      </div>
      <div className="flex flex-wrap items-center gap-2 text-xs text-ink-3">
        Try:
        {EXAMPLES.map(([sym, name]) => (
          <button key={sym} type="button" onClick={() => setTicker(sym)}
            className="rounded-full border border-line-strong px-3 py-1 text-ink-2 hover:bg-white/[0.06] hover:text-ink">{sym} <span className="text-ink-3">· {name}</span></button>
        ))}
      </div>
      {load.isError && <Alert tone="risk">{errMsg(load.error)}</Alert>}
      {load.isPending && <p className="text-sm text-ink-3" role="status">Fetching statements — this can take up to a minute…</p>}
    </form>
  );
}

/* ── CSV / Excel ────────────────────────────────────────────────────────── */

function CsvPanel() {
  const [file, setFile] = useState<File | null>(null);
  const [company, setCompany] = useState("");
  const [currency, setCurrency] = useState("INR");
  const [local, setLocal] = useState("");
  const input = useRef<HTMLInputElement>(null);
  const load = useWorkspaceMutation((fd: FormData) => api<Workspace>("/ingest/csv", { form: fd }));

  const submit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!company.trim()) return setLocal("Enter the company name.");
    if (!file) return setLocal("Choose a CSV or Excel file.");
    setLocal("");
    const fd = new FormData();
    fd.append("file", file);
    fd.append("company_name", company.trim());
    fd.append("currency", currency);
    load.mutate(fd);
  };

  return (
    <form onSubmit={submit} className="space-y-4" noValidate>
      <p className="text-sm text-ink-2">
        For private or unlisted companies. Needs a <code className="num rounded bg-white/10 px-1.5 py-0.5 text-xs">period</code> column
        (e.g. 2023-FY) plus any of revenue, total_assets, total_liabilities, current_assets, current_liabilities, equity…
        Keep all figures in one unit.
      </p>
      <a href="/api/ingest/csv-template" download
        className="inline-flex items-center gap-2 text-sm font-medium text-brand-700 hover:underline"><Download className="size-4" aria-hidden /> Download CSV template</a>
      <div className="grid gap-4 sm:grid-cols-[1fr_9rem]">
        <Field label="Company name" required value={company} onChange={(e) => setCompany(e.target.value)} placeholder="e.g. Acme Pvt. Ltd." maxLength={100} />
        <SelectField label="Currency" value={currency} onChange={(e) => setCurrency(e.target.value)}>
          {CURRENCIES.map((c) => <option key={c}>{c}</option>)}
        </SelectField>
      </div>
      <div className="flex flex-wrap items-center gap-3">
        <Button type="button" variant="secondary" onClick={() => input.current?.click()}><UploadCloud className="size-4" aria-hidden /> Choose file</Button>
        <input ref={input} type="file" accept=".csv,.xlsx,.xls" hidden aria-label="Choose CSV or Excel file"
          onChange={(e) => { setFile(e.target.files?.[0] ?? null); load.reset(); }} />
        <span className="text-sm text-ink-2">{file ? file.name : "No file chosen · .csv, .xlsx or .xls, up to 5 MB"}</span>
      </div>
      {local && <Alert tone="watch">{local}</Alert>}
      {load.isError && <Alert tone="risk">{errMsg(load.error)}</Alert>}
      <Button type="submit" loading={load.isPending}>Load company data</Button>
    </form>
  );
}
