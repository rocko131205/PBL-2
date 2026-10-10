import { Check, Circle } from "lucide-react";
import clsx from "clsx";
import { passwordRules, passwordStrength } from "@/lib/password";

const LEVELS = ["Too weak", "Weak", "Fair", "Good", "Strong"];
const COLORS = ["bg-line-strong", "bg-risk", "bg-watch", "bg-sky-600", "bg-good"];

export function PasswordChecklist({ value }: { value: string }) {
  if (!value) return null;
  const strength = passwordStrength(value);
  return (
    <div className="space-y-2 rounded-xl bg-black/25 p-3" aria-live="polite">
      <div className="flex items-center gap-2">
        <div className="flex flex-1 gap-1" aria-hidden>
          {[1, 2, 3, 4].map((i) => (
            <div key={i} className={clsx("h-1.5 flex-1 rounded-full", i <= strength ? COLORS[strength] : "bg-line")} />
          ))}
        </div>
        <span className="w-16 text-right text-xs font-medium text-ink-2">{LEVELS[strength]}</span>
      </div>
      <ul className="grid grid-cols-1 gap-x-4 gap-y-1 sm:grid-cols-2">
        {passwordRules(value).map((r) => (
          <li key={r.id} className={clsx("flex items-center gap-1.5 text-xs", r.ok ? "text-good" : "text-ink-3")}>
            {r.ok ? <Check className="size-3.5" aria-hidden /> : <Circle className="size-3.5" aria-hidden />}
            {r.label}
          </li>
        ))}
      </ul>
    </div>
  );
}
