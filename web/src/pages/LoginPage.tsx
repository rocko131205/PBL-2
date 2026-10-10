import { useState } from "react";
import { Link, Navigate, useLocation, useNavigate } from "react-router-dom";
import { useForm } from "react-hook-form";
import { z } from "zod";
import { zodResolver } from "@hookform/resolvers/zod";
import { AuthLayout } from "@/layouts/AuthLayout";
import { Alert, Button, Field } from "@/components/ui";
import { useAuth } from "@/lib/auth";
import { ApiError } from "@/lib/api";

const schema = z.object({
  email: z.string().trim().min(1, "Enter your email."),
  password: z.string().min(1, "Enter your password."),
});
type Values = z.infer<typeof schema>;

export default function LoginPage() {
  const { user, login, loginMfa, expired } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const navState = location.state as { from?: string; registered?: boolean } | null;
  const from = navState?.from ?? "/upload";
  const justRegistered = !!navState?.registered;
  const [mfaToken, setMfaToken] = useState<string | null>(null);
  const [error, setError] = useState("");

  if (user) return <Navigate to={from} replace />;

  return mfaToken ? (
    <MfaStep
      error={error}
      onCancel={() => { setMfaToken(null); setError(""); }}
      onSubmit={async (code) => {
        setError("");
        try {
          await loginMfa(mfaToken, code);
          navigate(from, { replace: true });
        } catch (e) {
          setError(e instanceof ApiError ? e.message : "Something went wrong.");
        }
      }}
    />
  ) : (
    <PasswordStep
      error={error}
      expired={expired}
      justRegistered={justRegistered}
      onSubmit={async (v) => {
        setError("");
        try {
          const res = await login(v.email, v.password);
          if ("mfaToken" in res) setMfaToken(res.mfaToken);
          else navigate(from, { replace: true });
        } catch (e) {
          setError(e instanceof ApiError ? e.message : "Something went wrong.");
        }
      }}
    />
  );
}

function PasswordStep({ onSubmit, error, expired, justRegistered }: {
  onSubmit: (v: Values) => Promise<void>; error: string; expired: boolean; justRegistered: boolean;
}) {
  const { register, handleSubmit, formState: { errors, isSubmitting } } = useForm<Values>({ resolver: zodResolver(schema) });
  return (
    <AuthLayout title="Sign in" subtitle="Welcome back to FinVeritas.">
      <form onSubmit={handleSubmit(onSubmit)} className="space-y-4" noValidate>
        {justRegistered && <Alert tone="good">Account created. Sign in to continue.</Alert>}
        {expired && <Alert tone="watch">You were signed out because your session ended. Please sign in again.</Alert>}
        {error && <Alert tone="risk">{error}</Alert>}
        <Field label="Email" type="email" autoComplete="username" placeholder="you@example.com" error={errors.email?.message} {...register("email")} />
        <Field label="Password" type="password" autoComplete="current-password" error={errors.password?.message} {...register("password")} />
        <Button type="submit" loading={isSubmitting} className="w-full">Sign in</Button>
      </form>
      <div className="mt-6 flex items-center justify-between text-sm">
        <Link to="/forgot" className="font-medium text-brand-700 hover:underline">Forgot password?</Link>
        <span className="text-ink-2">
          New here? <Link to="/register" className="font-medium text-brand-700 hover:underline">Create an account</Link>
        </span>
      </div>
    </AuthLayout>
  );
}

const mfaSchema = z.object({ code: z.string().regex(/^\d{6}$/, "Enter the 6-digit code.") });

function MfaStep({ onSubmit, onCancel, error }: { onSubmit: (code: string) => Promise<void>; onCancel: () => void; error: string }) {
  const { register, handleSubmit, formState: { errors, isSubmitting } } = useForm<{ code: string }>({ resolver: zodResolver(mfaSchema) });
  return (
    <AuthLayout title="Two-factor authentication" subtitle="Enter the 6-digit code from your authenticator app.">
      <form onSubmit={handleSubmit((v) => onSubmit(v.code))} className="space-y-4" noValidate>
        {error && <Alert tone="risk">{error}</Alert>}
        <Field label="Authentication code" inputMode="numeric" autoComplete="one-time-code" maxLength={6} placeholder="123456"
          autoFocus error={errors.code?.message} {...register("code")} />
        <Button type="submit" loading={isSubmitting} className="w-full">Verify</Button>
        <Button type="button" variant="ghost" className="w-full" onClick={onCancel}>Back</Button>
      </form>
    </AuthLayout>
  );
}
