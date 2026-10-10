import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useForm, useWatch } from "react-hook-form";
import { z } from "zod";
import { zodResolver } from "@hookform/resolvers/zod";
import { useQuery } from "@tanstack/react-query";
import { AuthLayout } from "@/layouts/AuthLayout";
import { Alert, Button, Field, SelectField } from "@/components/ui";
import { PasswordChecklist } from "@/components/PasswordChecklist";
import { api, ApiError } from "@/lib/api";
import { passwordIsValid } from "@/lib/password";

const COUNTRY_CODES = [
  ["IN", "+91"], ["US", "+1"], ["GB", "+44"], ["AU", "+61"], ["CA", "+1"], ["AE", "+971"], ["SG", "+65"],
  ["DE", "+49"], ["FR", "+33"], ["JP", "+81"], ["CN", "+86"], ["BR", "+55"], ["ZA", "+27"], ["NZ", "+64"],
  ["NL", "+31"], ["IT", "+39"], ["ES", "+34"], ["KR", "+82"], ["MY", "+60"], ["PH", "+63"], ["PK", "+92"],
  ["BD", "+880"], ["NG", "+234"], ["KE", "+254"], ["MX", "+52"],
] as const;

const schema = z
  .object({
    full_name: z.string().trim().min(2, "Full name must be at least 2 characters.")
      .regex(/^[A-Za-z\s.\-']+$/, "Use letters, spaces, hyphens, dots or apostrophes only."),
    email: z.string().trim().regex(/^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$/, "Enter a valid email address."),
    country_code: z.string(),
    phone: z.string().refine((v) => v.replace(/\D/g, "").length === 10, "Phone number must be exactly 10 digits."),
    state: z.string().min(1, "Select your state."),
    city: z.string().min(1, "Select your city."),
    password: z.string().refine(passwordIsValid, "Password doesn't meet the requirements below."),
    confirm: z.string(),
  })
  .refine((v) => v.password === v.confirm, { path: ["confirm"], message: "Passwords do not match." });
type Values = z.infer<typeof schema>;

export default function RegisterPage() {
  const navigate = useNavigate();
  const [error, setError] = useState("");
  const { register, handleSubmit, control, setError: setFieldError, resetField, formState: { errors, isSubmitting } } =
    useForm<Values>({ resolver: zodResolver(schema), defaultValues: { country_code: "+91", state: "", city: "" } });

  const state = useWatch({ control, name: "state" });
  const password = useWatch({ control, name: "password" }) ?? "";
  const states = useQuery({ queryKey: ["states"], queryFn: () => api<string[]>("/geo/states"), staleTime: Infinity });
  const cities = useQuery({
    queryKey: ["cities", state],
    queryFn: () => api<string[]>(`/geo/cities?state=${encodeURIComponent(state)}`),
    enabled: !!state,
    staleTime: Infinity,
  });

  const submit = async (v: Values) => {
    setError("");
    try {
      const { confirm: _confirm, ...body } = v;
      await api("/auth/register", { json: body, silent401: true });
      navigate("/login", { replace: true, state: { registered: true } });
    } catch (e) {
      if (!(e instanceof ApiError)) return setError("Something went wrong.");
      Object.entries(e.fields).forEach(([k, msg]) => setFieldError(k as keyof Values, { message: msg }));
      setError(e.message);
    }
  };

  return (
    <AuthLayout title="Create your account" subtitle="Join FinVeritas — it's free.">
      <form onSubmit={handleSubmit(submit)} className="space-y-4" noValidate>
        {error && <Alert tone="risk">{error}</Alert>}
        <Field label="Full name" required autoComplete="name" placeholder="Rahul Sharma" error={errors.full_name?.message} {...register("full_name")} />
        <Field label="Email" required type="email" autoComplete="email" placeholder="you@example.com" error={errors.email?.message} {...register("email")} />

        <div className="grid grid-cols-[7.5rem_1fr] gap-3">
          <SelectField label="Code" required {...register("country_code")}>
            {COUNTRY_CODES.map(([iso, code], i) => <option key={i} value={code}>{iso} {code}</option>)}
          </SelectField>
          <Field label="Phone" required type="tel" inputMode="numeric" autoComplete="tel-national" placeholder="9876543210" error={errors.phone?.message} {...register("phone")} />
        </div>

        <div className="grid gap-3 sm:grid-cols-2">
          <SelectField label="State" required error={errors.state?.message}
            {...register("state", { onChange: () => resetField("city", { defaultValue: "" }) })}>
            <option value="">Select state</option>
            {states.data?.map((s) => <option key={s}>{s}</option>)}
          </SelectField>
          <SelectField label="City" required error={errors.city?.message} disabled={!state} {...register("city")}>
            <option value="">{state ? "Select city" : "Select a state first"}</option>
            {cities.data?.map((c) => <option key={c}>{c}</option>)}
          </SelectField>
        </div>

        <Field label="Password" required type="password" autoComplete="new-password" placeholder="Min 8 characters" error={errors.password?.message} {...register("password")} />
        <PasswordChecklist value={password} />
        <Field label="Confirm password" required type="password" autoComplete="new-password" placeholder="Repeat password" error={errors.confirm?.message} {...register("confirm")} />

        <Button type="submit" loading={isSubmitting} className="w-full">Create account</Button>
      </form>
      <p className="mt-6 text-center text-sm text-ink-2">
        Already registered? <Link to="/login" className="font-medium text-brand-700 hover:underline">Back to sign in</Link>
      </p>
    </AuthLayout>
  );
}
