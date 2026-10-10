import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useForm, useWatch } from "react-hook-form";
import { z } from "zod";
import { zodResolver } from "@hookform/resolvers/zod";
import clsx from "clsx";
import { AuthLayout } from "@/layouts/AuthLayout";
import { Alert, Button, Field } from "@/components/ui";
import { PasswordChecklist } from "@/components/PasswordChecklist";
import { api, ApiError } from "@/lib/api";
import { passwordIsValid } from "@/lib/password";

const STEPS = ["Email", "Code", "New password"];
const msg = (e: unknown) => (e instanceof ApiError ? e.message : "Something went wrong.");

export default function ForgotPasswordPage() {
  const [step, setStep] = useState(0);
  const [email, setEmail] = useState("");
  const [notice, setNotice] = useState("");
  const [resetToken, setResetToken] = useState("");
  const navigate = useNavigate();

  return (
    <AuthLayout title="Reset your password" subtitle={`Step ${step + 1} of 3 — ${["enter your registered email", "enter the code we sent you", "choose a new password"][step]}`}>
      <ol className="mb-6 flex gap-2" aria-label="Progress">
        {STEPS.map((label, i) => (
          <li key={label} className="flex-1" aria-current={i === step ? "step" : undefined}>
            <div className={clsx("h-1 rounded-full", i <= step ? "bg-brand-700" : "bg-line")} />
            <span className={clsx("mt-1 block text-xs", i === step ? "font-medium text-ink" : "text-ink-3")}>{label}</span>
          </li>
        ))}
      </ol>

      {step === 0 && (
        <EmailStep onDone={(e, n) => { setEmail(e); setNotice(n); setStep(1); }} />
      )}
      {step === 1 && (
        <CodeStep
          email={email} notice={notice}
          onVerified={(t) => { setResetToken(t); setStep(2); }}
          onResend={() => setStep(0)}
        />
      )}
      {step === 2 && (
        <PasswordStep token={resetToken} onDone={() => navigate("/login", { replace: true })} onExpired={() => setStep(0)} />
      )}

      <p className="mt-6 text-center text-sm">
        <Link to="/login" className="font-medium text-brand-700 hover:underline">Back to sign in</Link>
      </p>
    </AuthLayout>
  );
}

function EmailStep({ onDone }: { onDone: (email: string, notice: string) => void }) {
  const [error, setError] = useState("");
  const { register, handleSubmit, formState: { errors, isSubmitting } } = useForm<{ email: string }>({
    resolver: zodResolver(z.object({ email: z.string().trim().min(1, "Enter your email.") })),
  });
  return (
    <form
      noValidate className="space-y-4"
      onSubmit={handleSubmit(async ({ email }) => {
        setError("");
        try {
          const r = await api<{ message: string }>("/password-reset/send-otp", { json: { email }, silent401: true });
          onDone(email, r.message);
        } catch (e) { setError(msg(e)); }
      })}
    >
      {error && <Alert tone="risk">{error}</Alert>}
      <Field label="Registered email" type="email" autoComplete="email" placeholder="you@example.com" error={errors.email?.message} {...register("email")} />
      <Button type="submit" loading={isSubmitting} className="w-full">Send code</Button>
    </form>
  );
}

function CodeStep({ email, notice, onVerified, onResend }: { email: string; notice: string; onVerified: (t: string) => void; onResend: () => void }) {
  const [error, setError] = useState("");
  const { register, handleSubmit, formState: { errors, isSubmitting } } = useForm<{ code: string }>({
    resolver: zodResolver(z.object({ code: z.string().regex(/^\d{6}$/, "Enter the 6-digit code.") })),
  });
  return (
    <form
      noValidate className="space-y-4"
      onSubmit={handleSubmit(async ({ code }) => {
        setError("");
        try {
          const r = await api<{ reset_token: string }>("/password-reset/verify-otp", { json: { email, code }, silent401: true });
          onVerified(r.reset_token);
        } catch (e) { setError(msg(e)); }
      })}
    >
      <Alert tone="info">{notice}</Alert>
      {error && <Alert tone="risk">{error}</Alert>}
      <Field label="6-digit code" inputMode="numeric" autoComplete="one-time-code" maxLength={6} placeholder="123456" autoFocus error={errors.code?.message} {...register("code")} />
      <Button type="submit" loading={isSubmitting} className="w-full">Verify code</Button>
      <Button type="button" variant="ghost" className="w-full" onClick={onResend}>Send a new code</Button>
    </form>
  );
}

function PasswordStep({ token, onDone, onExpired }: { token: string; onDone: () => void; onExpired: () => void }) {
  const [error, setError] = useState("");
  const schema = z
    .object({ password: z.string().refine(passwordIsValid, "Password doesn't meet the requirements below."), confirm: z.string() })
    .refine((v) => v.password === v.confirm, { path: ["confirm"], message: "Passwords do not match." });
  const { register, handleSubmit, control, formState: { errors, isSubmitting } } = useForm<z.infer<typeof schema>>({ resolver: zodResolver(schema) });
  const password = useWatch({ control, name: "password" }) ?? "";
  return (
    <form
      noValidate className="space-y-4"
      onSubmit={handleSubmit(async ({ password }) => {
        setError("");
        try {
          await api("/password-reset/reset", { json: { reset_token: token, new_password: password }, silent401: true });
          onDone();
        } catch (e) {
          if (e instanceof ApiError && /expired/i.test(e.message)) onExpired();
          setError(msg(e));
        }
      })}
    >
      {error && <Alert tone="risk">{error}</Alert>}
      <Field label="New password" type="password" autoComplete="new-password" placeholder="Min 8 characters" error={errors.password?.message} {...register("password")} />
      <PasswordChecklist value={password} />
      <Field label="Confirm password" type="password" autoComplete="new-password" placeholder="Repeat password" error={errors.confirm?.message} {...register("confirm")} />
      <Button type="submit" loading={isSubmitting} className="w-full">Reset password</Button>
    </form>
  );
}
