import { passwordIsValid, passwordRules, passwordStrength } from "./password";

describe("password policy (matches the server)", () => {
  it("accepts a strong password", () => expect(passwordIsValid("Str0ng!Passw0rd")).toBe(true));
  it.each(["Sh0rt!A","alllowercase1!", "ALLUPPERCASE1!", "NoNumbers!!", "NoSpecial123", "Password@123"])(
    "rejects %s", (pw) => expect(passwordIsValid(pw)).toBe(false),
  );
  it("rejects passwords over 72 bytes (bcrypt truncates silently)", () =>
    expect(passwordIsValid("Aa1!" + "x".repeat(70))).toBe(false));
  it("reports which rules are unmet", () =>
    expect(passwordRules("abc").filter((r) => !r.ok).map((r) => r.id)).toEqual(["len", "upper", "num", "special"]));
  it("strength meter spans 0-4", () => {
    expect(passwordStrength("")).toBe(0);
    expect(passwordStrength("Str0ng!Passw0rd")).toBe(4);
  });
});
