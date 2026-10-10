/** Client-side mirror of finveritas/security/passwords.py. The server is the authority. */

export interface PasswordRule {
  id: string;
  label: string;
  ok: boolean;
}

const COMMON = new Set([
  "password", "password1", "password123", "passw0rd", "qwerty123", "12345678", "123456789",
  "iloveyou", "admin123", "welcome1", "letmein1", "password@123", "password1!", "qwerty@123",
  "admin@123", "welcome@123",
]);

export function passwordRules(pw: string): PasswordRule[] {
  return [
    { id: "len", label: "At least 8 characters", ok: pw.length >= 8 },
    { id: "upper", label: "An uppercase letter", ok: /[A-Z]/.test(pw) },
    { id: "lower", label: "A lowercase letter", ok: /[a-z]/.test(pw) },
    { id: "num", label: "A number", ok: /\d/.test(pw) },
    { id: "special", label: "A special character", ok: /[^A-Za-z0-9]/.test(pw) },
    { id: "common", label: "Not a commonly used password", ok: pw.length > 0 && !COMMON.has(pw.toLowerCase()) },
  ];
}

export const passwordIsValid = (pw: string) => new TextEncoder().encode(pw).length <= 72 && passwordRules(pw).every((r) => r.ok);

/** 0–4 for the strength meter. */
export function passwordStrength(pw: string): number {
  const met = passwordRules(pw).filter((r) => r.ok).length; // 0–6 rules
  return Math.max(0, met - 2);
}
