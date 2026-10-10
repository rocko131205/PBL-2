import { forwardRef, useId, useState, type ButtonHTMLAttributes, type InputHTMLAttributes, type ReactNode, type SelectHTMLAttributes } from "react";
import { AlertCircle, CheckCircle2, Eye, EyeOff, Info, Loader2, TriangleAlert } from "lucide-react";
import clsx from "clsx";

/* ── Button (pill-shaped, as in the reference) ──────────────────────────── */

type Variant = "primary" | "secondary" | "ghost" | "danger";
interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: Variant;
  loading?: boolean;
}

const variants: Record<Variant, string> = {
  primary: "accent-gradient text-white shadow-[0_8px_24px_-8px_#3b82f6] hover:brightness-110 disabled:opacity-50 disabled:shadow-none",
  secondary: "border border-line-strong bg-white/[0.04] text-ink hover:bg-white/10 disabled:text-ink-3",
  ghost: "text-ink-2 hover:bg-white/[0.06] hover:text-ink",
  danger: "bg-risk/90 text-white hover:bg-risk disabled:opacity-50",
};

export function Button({ variant = "primary", loading, disabled, className, children, ...rest }: ButtonProps) {
  return (
    <button
      {...rest}
      disabled={disabled || loading}
      className={clsx(
        "inline-flex h-11 items-center justify-center gap-2 rounded-full px-5 text-sm font-medium transition disabled:cursor-not-allowed",
        variants[variant],
        className,
      )}
    >
      {loading && <Loader2 className="size-4 animate-spin" aria-hidden />}
      {children}
    </button>
  );
}

/* ── Field (label + input + error) ──────────────────────────────────────── */

interface FieldShellProps {
  label: string;
  error?: string;
  hint?: string;
  required?: boolean;
  id: string;
  children: ReactNode;
}

function FieldShell({ label, error, hint, required, id, children }: FieldShellProps) {
  return (
    <div className="space-y-1.5">
      <label htmlFor={id} className="block text-sm font-medium text-ink-2">
        {label}
        {required && <span className="text-risk"> *</span>}
      </label>
      {children}
      {error ? (
        <p id={`${id}-err`} role="alert" className="text-xs text-risk">{error}</p>
      ) : hint ? (
        <p className="text-xs text-ink-3">{hint}</p>
      ) : null}
    </div>
  );
}

const inputCls =
  "h-11 w-full rounded-xl border bg-black/30 px-3.5 text-sm text-ink placeholder:text-ink-3 transition " +
  "focus:border-brand-600 focus:outline-none focus:ring-2 focus:ring-brand-600/30 disabled:opacity-50";

interface FieldProps extends InputHTMLAttributes<HTMLInputElement> {
  label: string;
  error?: string;
  hint?: string;
}

export const Field = forwardRef<HTMLInputElement, FieldProps>(function Field(
  { label, error, hint, className, ...rest },
  ref,
) {
  const id = useId();
  const [shown, setShown] = useState(false);
  const isPassword = rest.type === "password";
  return (
    <FieldShell label={label} error={error} hint={hint} required={rest.required} id={id}>
      <div className="relative">
        <input
          {...rest}
          ref={ref}
          id={id}
          type={isPassword && shown ? "text" : rest.type}
          aria-invalid={!!error}
          aria-describedby={error ? `${id}-err` : undefined}
          className={clsx(inputCls, error ? "border-risk" : "border-line-strong", isPassword && "pr-11", className)}
        />
        {isPassword && (
          <button
            type="button"
            onClick={() => setShown((s) => !s)}
            aria-label={shown ? "Hide password" : "Show password"}
            className="absolute inset-y-0 right-0 grid w-11 place-items-center text-ink-3 hover:text-ink"
          >
            {shown ? <EyeOff className="size-4" /> : <Eye className="size-4" />}
          </button>
        )}
      </div>
    </FieldShell>
  );
});

interface SelectProps extends SelectHTMLAttributes<HTMLSelectElement> {
  label: string;
  error?: string;
}

export const SelectField = forwardRef<HTMLSelectElement, SelectProps>(function SelectField(
  { label, error, className, children, ...rest },
  ref,
) {
  const id = useId();
  return (
    <FieldShell label={label} error={error} required={rest.required} id={id}>
      <select
        {...rest}
        ref={ref}
        id={id}
        aria-invalid={!!error}
        className={clsx(inputCls, error ? "border-risk" : "border-line-strong", className)}
      >
        {children}
      </select>
    </FieldShell>
  );
});

/* ── Card / Alert / Spinner ─────────────────────────────────────────────── */

export function Card({ className, children }: { className?: string; children: ReactNode }) {
  return <div className={clsx("glass rounded-2xl", className)}>{children}</div>;
}

type Tone = "info" | "good" | "watch" | "risk";
const tones: Record<Tone, { cls: string; Icon: typeof Info }> = {
  info: { cls: "border-info/25 bg-info-bg text-info", Icon: Info },
  good: { cls: "border-good/25 bg-good-bg text-good", Icon: CheckCircle2 },
  watch: { cls: "border-watch/25 bg-watch-bg text-watch", Icon: TriangleAlert },
  risk: { cls: "border-risk/25 bg-risk-bg text-risk", Icon: AlertCircle },
};

export function Alert({ tone = "info", children }: { tone?: Tone; children: ReactNode }) {
  const { cls, Icon } = tones[tone];
  return (
    <div role={tone === "risk" ? "alert" : "status"} className={clsx("flex gap-2.5 rounded-xl border p-3 text-sm", cls)}>
      <Icon className="mt-0.5 size-4 shrink-0" aria-hidden />
      <div>{children}</div>
    </div>
  );
}

export function Spinner({ label = "Loading" }: { label?: string }) {
  return (
    <div role="status" className="flex items-center justify-center gap-2 p-8 text-sm text-ink-3">
      <Loader2 className="size-4 animate-spin" aria-hidden /> {label}…
    </div>
  );
}
