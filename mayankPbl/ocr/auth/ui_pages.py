"""Auth UI pages for FinVeritas — Login, Register, Forgot Password, File History."""
from __future__ import annotations

import re
import streamlit as st
import streamlit.components.v1 as components
from datetime import datetime

from auth.auth_controller import (
    login_user, register_user, send_otp, verify_otp,
    reset_password, decode_token,
)
from auth.indian_states import ALL_STATES, get_cities
from auth.db import get_file_history
from bson import ObjectId


# ── Country codes with flag emojis ────────────────────────────────────────────
COUNTRY_CODES = [
    "🇮🇳 +91",   # India — first by default
    "🇺🇸 +1",
    "🇬🇧 +44",
    "🇦🇺 +61",
    "🇨🇦 +1",
    "🇦🇪 +971",
    "🇸🇬 +65",
    "🇩🇪 +49",
    "🇫🇷 +33",
    "🇯🇵 +81",
    "🇨🇳 +86",
    "🇧🇷 +55",
    "🇿🇦 +27",
    "🇳🇿 +64",
    "🇳🇱 +31",
    "🇮🇹 +39",
    "🇪🇸 +34",
    "🇰🇷 +82",
    "🇲🇾 +60",
    "🇵🇭 +63",
    "🇵🇰 +92",
    "🇧🇩 +880",
    "🇳🇬 +234",
    "🇰🇪 +254",
    "🇲🇽 +52",
]


# ── Registration validation helper ────────────────────────────────────────────
def _validate_registration(
    full_name: str,
    email: str,
    phone_digits: str,
    state: str,
    city: str,
    cities: list,
    password: str,
    confirm: str,
) -> dict[str, str]:
    """Return a dictionary of human-readable error strings (empty = all valid)."""
    errors: dict[str, str] = {}

    # ── Full Name ──────────────────────────────────────────────────────────────
    name = full_name.strip()
    if not name:
        errors["name"] = "Full name is required."
    elif len(name) < 2:
        errors["name"] = "Full name must be at least 2 characters."
    elif not re.match(r"^[A-Za-z\s\.\-']+$", name):
        errors["name"] = "Full name may only contain letters, spaces, hyphens, or apostrophes — no numbers or symbols."

    # ── Email ──────────────────────────────────────────────────────────────────
    em = email.strip()
    if not em:
        errors["email"] = "Email address is required."
    elif not re.match(r"^[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}$", em):
        errors["email"] = "Please enter a valid email address (e.g. you@example.com)."

    # ── Phone ──────────────────────────────────────────────────────────────────
    digits = re.sub(r"\D", "", phone_digits)
    if not digits:
        errors["phone"] = "Phone number is required."
    elif len(digits) != 10:
        errors["phone"] = "Phone number must be exactly 10 digits."

    # ── State / City ───────────────────────────────────────────────────────────
    if state == "\u2014 Select \u2014" or state == "— Select —":
        errors["state"] = "Please select your state."
    elif not cities or city in ("\u2014 Select \u2014", "— Select —", "\u2014 Select state first \u2014", "— Select state first —"):
        errors["city"] = "Please select your city."

    # ── Password ───────────────────────────────────────────────────────────────
    if not password:
        errors["password"] = "Password is required."
    else:
        pw_issues: list[str] = []
        if len(password) < 8:
            pw_issues.append("at least 8 characters")
        if not re.search(r"[A-Z]", password):
            pw_issues.append("one uppercase letter (A-Z)")
        if not re.search(r"[a-z]", password):
            pw_issues.append("one lowercase letter (a-z)")
        if not re.search(r"\d", password):
            pw_issues.append("one number (0-9)")
        if not re.search(r"[@$!%*?&#^()_+\-=]", password):
            pw_issues.append("one special character (@, $, !, #, etc.)")
        if pw_issues:
            errors["password"] = "Password must include: " + " · ".join(pw_issues) + "."

    # ── Confirm ────────────────────────────────────────────────────────────────
    if password and confirm and password != confirm:
        errors["confirm"] = "Passwords do not match."

    return errors


# ── Right-panel animated logo — rendered via components.html (bypasses markdown parser) ──

_RIGHT_PANEL_HTML = """<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<style>
  * { margin: 0; padding: 0; box-sizing: border-box; }
  body {
    background: #0A0B0E;
    display: flex;
    align-items: center;
    justify-content: center;
    min-height: 100vh;
    font-family: 'Courier New', Courier, monospace;
    overflow: hidden;
  }

  /* Animated grid background */
  .grid {
    position: fixed;
    inset: 0;
    background-image:
      linear-gradient(rgba(212,150,58,0.05) 1px, transparent 1px),
      linear-gradient(90deg, rgba(212,150,58,0.05) 1px, transparent 1px);
    background-size: 44px 44px;
    animation: gridMove 18s linear infinite;
  }
  @keyframes gridMove {
    from { transform: translateY(0); }
    to   { transform: translateY(44px); }
  }

  /* Ambient glow circles */
  .glow1 {
    position: fixed;
    width: 300px; height: 300px;
    border-radius: 50%;
    background: radial-gradient(circle, rgba(212,150,58,0.12) 0%, transparent 70%);
    top: 10%; left: 20%;
    animation: pulse1 6s ease-in-out infinite;
  }
  .glow2 {
    position: fixed;
    width: 200px; height: 200px;
    border-radius: 50%;
    background: radial-gradient(circle, rgba(46,155,184,0.08) 0%, transparent 70%);
    bottom: 15%; right: 15%;
    animation: pulse2 8s ease-in-out infinite;
  }
  @keyframes pulse1 {
    0%,100% { transform: scale(1); opacity: 0.6; }
    50%     { transform: scale(1.15); opacity: 1; }
  }
  @keyframes pulse2 {
    0%,100% { transform: scale(1); opacity: 0.4; }
    50%     { transform: scale(1.2); opacity: 0.8; }
  }

  /* Center content */
  .center {
    position: relative;
    z-index: 10;
    display: flex;
    flex-direction: column;
    align-items: center;
    text-align: center;
    padding: 40px;
  }

  /* Hexagon logo mark */
  .hex-ring {
    width: 120px; height: 120px;
    position: relative;
    margin-bottom: 32px;
    animation: spinGlow 8s linear infinite;
  }
  @keyframes spinGlow {
    0%   { filter: drop-shadow(0 0 8px rgba(212,150,58,0.4)); }
    50%  { filter: drop-shadow(0 0 20px rgba(212,150,58,0.8)); }
    100% { filter: drop-shadow(0 0 8px rgba(212,150,58,0.4)); }
  }
  .hex-ring svg { width: 100%; height: 100%; }

  /* Main brand name */
  .brand {
    font-size: 52px;
    font-weight: 900;
    letter-spacing: 0.08em;
    background: linear-gradient(135deg, #D4963A 0%, #F0C060 40%, #D4963A 70%, #A06820 100%);
    background-size: 200% auto;
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    background-clip: text;
    animation: shimmer 4s linear infinite;
    margin-bottom: 8px;
  }
  @keyframes shimmer {
    from { background-position: 0% center; }
    to   { background-position: 200% center; }
  }

  .brand-sub {
    font-size: 10px;
    color: #3A3A52;
    letter-spacing: 0.26em;
    text-transform: uppercase;
    margin-bottom: 48px;
  }

  /* Feature pills */
  .pills {
    display: flex;
    flex-direction: column;
    gap: 10px;
    width: 100%;
    max-width: 320px;
  }
  .pill {
    display: flex;
    align-items: center;
    gap: 14px;
    padding: 12px 16px;
    border: 1px solid rgba(212,150,58,0.15);
    border-radius: 4px;
    background: rgba(212,150,58,0.03);
    opacity: 0;
    transform: translateX(20px);
    animation: slideIn 0.6s ease forwards;
  }
  .pill:nth-child(1) { animation-delay: 0.2s; }
  .pill:nth-child(2) { animation-delay: 0.5s; }
  .pill:nth-child(3) { animation-delay: 0.8s; }
  .pill:nth-child(4) { animation-delay: 1.1s; }
  .pill:nth-child(5) { animation-delay: 1.4s; }
  @keyframes slideIn {
    to { opacity: 1; transform: translateX(0); }
  }
  .pill-icon { font-size: 16px; min-width: 24px; }
  .pill-text {
    font-size: 11px;
    color: #7A7A96;
    letter-spacing: 0.06em;
    text-align: left;
    line-height: 1.5;
  }
  .pill-text strong {
    color: #D4963A;
    display: block;
    font-size: 12px;
    letter-spacing: 0.08em;
    margin-bottom: 1px;
  }

  /* Animated border line at bottom */
  .bottom-line {
    position: fixed;
    bottom: 0; left: 0;
    height: 2px;
    width: 100%;
    background: linear-gradient(90deg, transparent, #D4963A, transparent);
    animation: scanLine 3s ease-in-out infinite;
  }
  @keyframes scanLine {
    0%,100% { opacity: 0.3; }
    50%     { opacity: 1; }
  }
</style>
</head>
<body>
  <div class="grid"></div>
  <div class="glow1"></div>
  <div class="glow2"></div>

  <div class="center">
    <!-- Hexagon SVG logo mark -->
    <div class="hex-ring">
      <svg viewBox="0 0 100 100" fill="none" xmlns="http://www.w3.org/2000/svg">
        <polygon
          points="50,5 93,27.5 93,72.5 50,95 7,72.5 7,27.5"
          stroke="#D4963A" stroke-width="2" fill="rgba(212,150,58,0.06)"
        />
        <polygon
          points="50,18 82,35.5 82,64.5 50,82 18,64.5 18,35.5"
          stroke="rgba(212,150,58,0.3)" stroke-width="1" fill="none"
        />
        <text x="50" y="57" text-anchor="middle"
          fill="#D4963A" font-size="22" font-weight="900"
          font-family="Courier New, monospace" letter-spacing="1">FV</text>
      </svg>
    </div>

    <div class="brand">FinVeritas</div>
    <div class="brand-sub">Explainable Financial Analysis Platform</div>

    <div class="pills">
      <div class="pill">
        <span class="pill-icon">⬡</span>
        <div class="pill-text">
          <strong>Multi-Source Ingestion</strong>
          Bloomberg PDFs · yFinance Tickers · Private CSV
        </div>
      </div>
      <div class="pill">
        <span class="pill-icon">🔍</span>
        <div class="pill-text">
          <strong>9-Point Credibility Scoring</strong>
          Accounting identity · YoY plausibility · Dual-source check
        </div>
      </div>
      <div class="pill">
        <span class="pill-icon">🤖</span>
        <div class="pill-text">
          <strong>5 Explainable AI Agents</strong>
          Revenue · Liquidity · Balance Sheet · Sentiment · Cross-Ref
        </div>
      </div>
      <div class="pill">
        <span class="pill-icon">📊</span>
        <div class="pill-text">
          <strong>Basel III Aligned Outputs</strong>
          Pillar 2 & Pillar 3 ready · Fully auditable metrics
        </div>
      </div>
      <div class="pill">
        <span class="pill-icon">🔒</span>
        <div class="pill-text">
          <strong>Strict User Isolation</strong>
          JWT secured · Your data stays private · Always
        </div>
      </div>
    </div>
  </div>

  <div class="bottom-line"></div>
</body>
</html>"""


def _right_panel() -> None:
    """Render the animated right panel via components.html (never parsed as Markdown)."""
    components.html(_RIGHT_PANEL_HTML, height=820, scrolling=False)


# ── Left-side shared header ───────────────────────────────────────────────────

def _left_header(page_label: str, page_sub: str = "") -> None:
    st.markdown(
        f"""<div style="margin-bottom:28px;">
  <div style="font-size:22px;font-weight:800;color:#F0C060;letter-spacing:0.12em;
    font-family:'Courier New',monospace;margin-bottom:4px;">FinVeritas</div>
  <div style="font-size:11px;font-weight:600;color:#C0C0D0;letter-spacing:0.22em;
    text-transform:uppercase;font-family:monospace;margin-bottom:28px;">
    Explainable Financial Analysis Platform</div>
  <div style="font-size:14px;font-weight:700;color:#FFFFFF;letter-spacing:0.1em;
    text-transform:uppercase;font-family:monospace;
    border-left:3px solid #F0C060;padding-left:10px;margin-bottom:4px;">
    {page_label}</div>
  <div style="font-size:12px;color:#A0A0B0;font-family:monospace;
    padding-left:13px;">{page_sub}</div>
</div>""",
        unsafe_allow_html=True,
    )


# ── Login Page ────────────────────────────────────────────────────────────────

def page_login() -> None:
    left_col, right_col = st.columns([1, 1], gap="small")

    with right_col:
        _right_panel()

    with left_col:
        _left_header("Sign In", "Welcome back")

        with st.form("login_form", clear_on_submit=False):
            email    = st.text_input("Email", placeholder="you@example.com", key="login_email")
            password = st.text_input("Password", type="password",
                                      placeholder="••••••••", key="login_pw")
            submitted = st.form_submit_button("Login  →", use_container_width=True)

        if submitted:
            if not email.strip() or not password:
                st.error("Please enter both email and password.")
            else:
                ok, result = login_user(email.strip(), password)
                if ok:
                    st.session_state["auth_token"] = result
                    st.session_state["auth_user"]  = decode_token(result)
                    st.query_params["token"] = result
                    st.rerun()
                else:
                    st.error(result)

        st.markdown("<br>", unsafe_allow_html=True)
        col_reg, col_forgot = st.columns(2)
        if col_reg.button("Create Account", use_container_width=True, key="goto_register"):
            st.session_state["auth_page"] = "register"
            st.rerun()
        if col_forgot.button("Forgot Password", use_container_width=True, key="goto_forgot"):
            st.session_state["auth_page"] = "forgot"
            st.rerun()

        st.markdown(
            '<p style="font-size:10px;color:#8A8A96;text-align:center;margin-top:32px;'
            'font-family:monospace;letter-spacing:0.14em;">'
            'FINVERITAS · SECURE · EXPLAINABLE · AUDITABLE</p>',
            unsafe_allow_html=True,
        )


# ── Registration Page ─────────────────────────────────────────────────────────

def page_register() -> None:
    left_col, right_col = st.columns([1, 1], gap="small")

    with right_col:
        _right_panel()

    with left_col:
        _left_header("Create Account", "Join FinVeritas — it's free")

        # Initialize errors from submit attempts
        errors = st.session_state.get("reg_submit_errors", {}).copy()

        # Inline error macro helper
        def _err(field: str):
            if field in errors:
                st.markdown(f'<p style="color:#FF6B6B;font-size:12px;margin-top:-12px;margin-bottom:12px;">{errors[field]}</p>', unsafe_allow_html=True)
        
        def _err_col(col, field: str):
            if field in errors:
                col.markdown(f'<p style="color:#FF6B6B;font-size:12px;margin-top:-12px;margin-bottom:12px;">{errors[field]}</p>', unsafe_allow_html=True)

        with st.container(border=True):
            full_name = st.text_input("Full Name *", placeholder="Rahul Sharma", key="reg_name")
            if full_name and "name" not in errors:
                # Dynamic validation when not empty
                if len(full_name.strip()) < 2:
                    errors["name"] = "Full name must be at least 2 characters."
                elif not re.match(r"^[A-Za-z\s\.\-']+$", full_name.strip()):
                    errors["name"] = "Full name may only contain letters, spaces... no numbers/symbols."
            _err("name")

            email = st.text_input("Email *", placeholder="you@example.com", key="reg_email")
            if email and "email" not in errors:
                if not re.match(r"^[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}$", email.strip()):
                    errors["email"] = "Please enter a valid email address (e.g. you@example.com)."
            _err("email")

            col_cc, col_ph = st.columns([1, 3])
            country_code = col_cc.selectbox("Code *", COUNTRY_CODES, index=0, key="reg_cc")
            phone_raw    = col_ph.text_input("Phone *", placeholder="9876543210", key="reg_phone")
            
            if phone_raw and "phone" not in errors:
                digits = re.sub(r"\D", "", phone_raw)
                if len(digits) != 10:
                    errors["phone"] = "Phone number must be exactly 10 digits."
            if "phone" in errors:
                st.markdown(f'<p style="color:#FF6B6B;font-size:12px;margin-top:-12px;margin-bottom:12px;">{errors["phone"]}</p>', unsafe_allow_html=True)

            # State & City inside the same bordered box, dynamically reacting
            col_s, col_c = st.columns(2)
            state  = col_s.selectbox("State *", ["— Select —"] + ALL_STATES, key="reg_state")
            _err_col(col_s, "state")
            
            cities = get_cities(state) if state != "— Select —" else []
            city   = col_c.selectbox("City *", ["— Select —"] + cities if cities else ["— Select state first —"], key="reg_city")
            _err_col(col_c, "city")

            col_p1, col_p2 = st.columns(2)
            password = col_p1.text_input("Password *", type="password", placeholder="Min 8 chars", key="reg_pw", help="Must include uppercase, lowercase, number & special character")
            if password and "password" not in errors:
                pw_issues: list[str] = []
                if len(password) < 8: pw_issues.append("at least 8 chars")
                if not re.search(r"[A-Z]", password): pw_issues.append("uppercase")
                if not re.search(r"[a-z]", password): pw_issues.append("lowercase")
                if not re.search(r"\d", password): pw_issues.append("number")
                if not re.search(r"[@$!%*?&#^()_+\-=]", password): pw_issues.append("special char")
                if pw_issues:
                    errors["password"] = "Password needs: " + ", ".join(pw_issues)
            _err_col(col_p1, "password")
            
            confirm = col_p2.text_input("Confirm Password *", type="password", placeholder="Repeat", key="reg_confirm")
            if confirm and password and password != confirm and "confirm" not in errors:
                errors["confirm"] = "Passwords do not match."
            _err_col(col_p2, "confirm")

            st.write("") # slight spacer inside form box
            submitted = st.button("Create Account  →", use_container_width=True)

        if submitted:
            cc_num     = country_code.split()[-1]
            phone_full = f"{cc_num}{phone_raw.strip()}"

            chk_errors = _validate_registration(
                full_name=full_name, email=email,
                phone_digits=phone_raw,
                state=state, city=city, cities=cities,
                password=password, confirm=confirm,
            )
            
            if chk_errors:
                st.session_state["reg_submit_errors"] = chk_errors
                st.rerun()  # Rerun to display errors inline
            else:
                st.session_state.pop("reg_submit_errors", None)
                ok, msg = register_user(
                    full_name=full_name.strip(), email=email.strip(),
                    phone=phone_full, state=state, city=city, password=password,
                )
                if ok:
                    st.success("✅ Account created! Redirecting to login…")
                    st.session_state["auth_page"] = "login"
                    st.rerun()
                else:
                    st.error(msg)

        st.markdown("<br>", unsafe_allow_html=True)
        if st.button("← Back to Login", key="reg_back", use_container_width=True):
            st.session_state["auth_page"] = "login"
            st.rerun()



# ── Forgot Password ───────────────────────────────────────────────────────────

def page_forgot_password() -> None:
    step = st.session_state.get("otp_step", 1)

    left_col, right_col = st.columns([1, 1], gap="small")

    with right_col:
        _right_panel()

    with left_col:
        step_info = {
            1: ("Reset Password", "Step 1 of 3 — Enter your registered email"),
            2: ("Reset Password", "Step 2 of 3 — Enter the OTP sent to your inbox"),
            3: ("Reset Password", "Step 3 of 3 — Choose your new password"),
        }
        title, sub = step_info.get(step, ("Reset Password", ""))
        _left_header(title, sub)

        # Progress bar
        pct = {1: 33, 2: 66, 3: 100}.get(step, 33)
        st.markdown(
            f'<div style="background:#1A1A28;height:3px;border-radius:2px;margin-bottom:24px;">'
            f'<div style="background:linear-gradient(90deg,#D4963A,#F0C060);height:3px;'
            f'border-radius:2px;width:{pct}%;"></div></div>',
            unsafe_allow_html=True,
        )

        if step == 1:
            with st.form("otp_email_form"):
                email     = st.text_input("Registered Email", placeholder="you@example.com")
                submitted = st.form_submit_button("Send OTP  →", use_container_width=True)
            if submitted:
                if not email.strip():
                    st.error("Please enter your email.")
                else:
                    with st.spinner("Sending OTP via Gmail…"):
                        ok, msg = send_otp(email.strip(), st.session_state)
                    if ok:
                        st.success("📧 OTP sent — check your inbox (valid 2 minutes).")
                        st.session_state["otp_step"] = 2
                        st.rerun()
                    else:
                        st.error(msg)

        elif step == 2:
            sent_to = st.session_state.get("otp_data", {}).get("email", "your email")
            st.markdown(
                f'<p style="font-size:10px;color:#D4963A;font-family:monospace;margin-bottom:8px;">'
                f'OTP sent to: {sent_to}</p>',
                unsafe_allow_html=True,
            )
            with st.form("otp_verify_form"):
                otp_input = st.text_input("6-Digit OTP", placeholder="123456", max_chars=6)
                submitted  = st.form_submit_button("Verify OTP  →", use_container_width=True)
            if submitted:
                ok, msg = verify_otp(otp_input.strip(), st.session_state)
                if ok:
                    st.success("✅ OTP verified.")
                    st.session_state["otp_step"] = 3
                    st.rerun()
                else:
                    st.error(msg)
            if st.button("Resend OTP", key="resend_otp"):
                st.session_state["otp_step"] = 1
                st.rerun()

        elif step == 3:
            with st.form("reset_pw_form"):
                new_pw  = st.text_input("New Password", type="password",
                                         placeholder="Min 8 characters",
                                         help="Must include uppercase, lowercase, number & special character")
                conf_pw = st.text_input("Confirm Password", type="password",
                                         placeholder="Repeat password")
                submitted = st.form_submit_button("Reset Password  →", use_container_width=True)
            if submitted:
                pw_issues: list[str] = []
                if len(new_pw) < 8: pw_issues.append("at least 8 chars")
                if not re.search(r"[A-Z]", new_pw): pw_issues.append("uppercase")
                if not re.search(r"[a-z]", new_pw): pw_issues.append("lowercase")
                if not re.search(r"\d", new_pw): pw_issues.append("number")
                if not re.search(r"[@$!%*?&#^()_+\-=]", new_pw): pw_issues.append("special char")

                if pw_issues:
                    st.error("Password needs: " + ", ".join(pw_issues))
                elif new_pw != conf_pw:
                    st.error("Passwords do not match.")
                else:
                    ok, msg = reset_password(
                        st.session_state.get("otp_verified_email", ""), new_pw
                    )
                    if ok:
                        st.success("✅ Password reset! Redirecting to login…")
                        for k in ["otp_step", "otp_data", "otp_verified_email"]:
                            st.session_state.pop(k, None)
                        st.session_state["auth_page"] = "login"
                        st.rerun()
                    else:
                        st.error(msg)

        st.markdown("<br>", unsafe_allow_html=True)
        if st.button("← Back to Login", key="forgot_back", use_container_width=True):
            for k in ["otp_step", "otp_data", "otp_verified_email"]:
                st.session_state.pop(k, None)
            st.session_state["auth_page"] = "login"
            st.rerun()


# ── File History Page ─────────────────────────────────────────────────────────

def page_history(user_id: str) -> None:
    st.markdown(
        '<div class="bb-section"><div class="bb-section-title">MY FILE HISTORY</div>'
        '<div class="bb-section-sub">All analyses you have run — linked to your account</div>'
        "</div>",
        unsafe_allow_html=True,
    )

    try:
        records = list(
            get_file_history()
            .find({"user_id": ObjectId(user_id)})
            .sort("timestamp", -1)
            .limit(100)
        )
    except Exception as exc:
        st.error(f"Could not load history: {exc}")
        return

    if not records:
        st.markdown(
            '<div style="color:var(--c-text3,#5A5A72);font-size:12px;margin-top:24px;">'
            "▸ No analyses recorded yet. Run a full analysis on the Upload page to start tracking."
            "</div>",
            unsafe_allow_html=True,
        )
        return

    src_colour = {"pdf": "#D4963A", "ticker": "#2E9BB8", "csv": "#3AB87A"}
    rows_html = ""
    for r in records:
        src     = r.get("source_type", "—")
        col     = src_colour.get(src, "#9A9AB0")
        ts      = r.get("timestamp")
        ts_str  = ts.strftime("%Y-%m-%d %H:%M") if isinstance(ts, datetime) else "—"
        score   = r.get("credibility_score", "—")
        sc_col  = (
            "#3AB87A" if isinstance(score, int) and score >= 75 else
            "#D4963A" if isinstance(score, int) and score >= 50 else "#C94A3A"
        )
        rows_html += (
            f'<tr style="border-bottom:1px solid #12131E;">'
            f'<td style="padding:10px 12px;color:#D8D8E0;">{r.get("entity_name","—")}</td>'
            f'<td style="padding:10px 12px;">'
            f'<span style="color:{col};font-size:9px;font-weight:700;'
            f'background:{col}18;padding:2px 8px;border-radius:2px;">{src.upper()}</span></td>'
            f'<td style="padding:10px 12px;color:#5A5A72;font-family:monospace;">'
            f'{r.get("source_label","—")}</td>'
            f'<td style="padding:10px 12px;color:{sc_col};font-weight:700;'
            f'font-family:monospace;">{score}</td>'
            f'<td style="padding:10px 12px;color:#3A3A52;font-family:monospace;">{ts_str}</td>'
            f'</tr>'
        )

    st.markdown(
        f'<div style="background:#0A0B0E;border:1px solid #1E2030;border-radius:4px;'
        f'overflow:hidden;margin-top:16px;">'
        f'<table style="width:100%;border-collapse:collapse;font-size:11px;">'
        f'<thead><tr style="background:#10121A;">'
        f'<th style="text-align:left;padding:10px 12px;color:#D4963A;font-size:9px;'
        f'letter-spacing:0.16em;border-bottom:1px solid #1E2030;">ENTITY</th>'
        f'<th style="text-align:left;padding:10px 12px;color:#D4963A;font-size:9px;'
        f'letter-spacing:0.16em;border-bottom:1px solid #1E2030;">SOURCE</th>'
        f'<th style="text-align:left;padding:10px 12px;color:#D4963A;font-size:9px;'
        f'letter-spacing:0.16em;border-bottom:1px solid #1E2030;">LABEL</th>'
        f'<th style="text-align:left;padding:10px 12px;color:#D4963A;font-size:9px;'
        f'letter-spacing:0.16em;border-bottom:1px solid #1E2030;">CRED SCORE</th>'
        f'<th style="text-align:left;padding:10px 12px;color:#D4963A;font-size:9px;'
        f'letter-spacing:0.16em;border-bottom:1px solid #1E2030;">DATE</th>'
        f'</tr></thead><tbody>{rows_html}</tbody></table></div>',
        unsafe_allow_html=True,
    )
