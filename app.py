from flask import Flask, render_template, request, jsonify, send_file, redirect, session, abort
import os, re, json, secrets
from docx import Document
from io import BytesIO
from dotenv import load_dotenv
import stripe

# ------------------------------------------------------------------
# 1️⃣ Config & Setup
# ------------------------------------------------------------------
load_dotenv()

app = Flask(__name__)

# Decide cookie security based on environment / DOMAIN
FLASK_ENV = os.getenv("FLASK_ENV", "development").lower()
DOMAIN = os.getenv("DOMAIN", "http://localhost:5000")

USE_SECURE_COOKIES = DOMAIN.startswith("https://") or FLASK_ENV == "production"

app.config.update(
    SESSION_COOKIE_SECURE=USE_SECURE_COOKIES,  # ✅ Secure in production / HTTPS, off on localhost
    SESSION_COOKIE_HTTPONLY=True,              # ✅ Not accessible via JavaScript
    SESSION_COOKIE_SAMESITE="Lax",             # ✅ Helps prevent CSRF
)

app.secret_key = os.getenv("FLASK_SECRET_KEY", secrets.token_hex(16))
stripe.api_key = os.getenv("STRIPE_SECRET_KEY", "")
OWNER_SECRET = os.getenv("OWNER_SECRET", "supersecureadminkey123")

print(f"[CONFIG] FLASK_ENV={FLASK_ENV}, DOMAIN={DOMAIN}, USE_SECURE_COOKIES={USE_SECURE_COOKIES}")

# ------------------------------------------------------------------
# 2️⃣ Parse morrowland 243.docx
# ------------------------------------------------------------------
def load_detailed_archetypes_docx(file_path: str):
    if not os.path.exists(file_path):
        print(f"[ERROR] File not found: {file_path}")
        return {}, {}, {}

    doc = Document(file_path)
    raw_lines = [p.text for p in doc.paragraphs]
    lines = [line.strip() for line in raw_lines]

    header_re = re.compile(
        r"(?i)openness\s*[:\-–—]?\s*(low|medium|high).*?"
        r"conscientiousness\s*[:\-–—]?\s*(low|medium|high).*?"
        r"extraversion\s*[:\-–—]?\s*(low|medium|high).*?"
        r"agreeableness\s*[:\-–—]?\s*(low|medium|high).*?"
        r"neuroticism\s*[:\-–—]?\s*(low|medium|high)"
    )
    archetype_re = re.compile(r"(?i)^archetype\s*[:\-–—]?\s*(.+?)\s*$")

    by_code, by_name, code_to_name = {}, {}, {}
    current_code, current_name, buffer = None, None, []

    def flush():
        nonlocal current_code, current_name, buffer
        if current_code and buffer:
            text = "\n".join(buffer).strip()
            by_code[current_code] = text
            if current_name:
                by_name[current_name] = text
                code_to_name[current_code] = current_name
        buffer = []

    i = 0
    while i < len(lines):
        line = lines[i]
        m_header = header_re.search(line)
        if m_header:
            flush()
            O, C, E, A, N_ = [x.capitalize() for x in m_header.groups()]
            current_code = f"{O}-{C}-{E}-{A}-{N_}"
            current_name = None

            # look ahead a couple lines for "Archetype: Name"
            for j in range(1, 4):
                if i + j >= len(lines):
                    break
                m_name = archetype_re.match(lines[i + j].strip())
                if m_name:
                    current_name = m_name.group(1).strip()
                    i += j
                    break

            if not current_name:
                current_name = f"Unknown_{i}"
        else:
            if current_code:
                buffer.append(raw_lines[i])
        i += 1

    flush()
    print(f"[✅ SUCCESS] Loaded {len(by_code)} archetypes from {os.path.basename(file_path)}")
    return by_code, by_name, code_to_name

# ------------------------------------------------------------------
# 3️⃣ Load Data
# ------------------------------------------------------------------
base_dir = os.path.dirname(os.path.abspath(__file__))
file_path = os.path.join(base_dir, "morrowland 243.docx")

DETAILED_BY_CODE, DETAILED_BY_NAME, CODE_TO_NAME = load_detailed_archetypes_docx(file_path)


def load_archetypes(base_map):
    """
    Build the archetype-name mapping.
    1. Start with names parsed from the DOCX (CODE_TO_NAME).
    2. If archetypes_full.json / archetypes.json exist, they override or add.
    """
    result = dict(base_map or {})
    for file in ["archetypes_full.json", "archetypes.json"]:
        path = os.path.join(base_dir, file)
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, dict) and data:
                    result.update(data)
                    print(f"[INFO] Loaded {len(data)} archetypes from {file}")
                    return result
    if not result:
        print("[⚠️ Using fallback minimal archetypes]")
        return {"Low-Low-Low-Low-Low": "Aquashine"}
    return result


ARCHETYPES = load_archetypes(CODE_TO_NAME)
FREE_CODES_FILE = os.path.join(base_dir, "free_codes.json")

# ------------------------------------------------------------------
# 4️⃣ Free Code System
# ------------------------------------------------------------------
def load_free_codes():
    if os.path.exists(FREE_CODES_FILE):
        try:
            with open(FREE_CODES_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except json.JSONDecodeError:
            print("[⚠️ Corrupted free_codes.json, resetting.]")
            return {}
    return {}


def save_free_codes(codes):
    with open(FREE_CODES_FILE, "w", encoding="utf-8") as f:
        json.dump(codes, f, indent=2)


def generate_free_code():
    code = secrets.token_hex(4).upper()
    codes = load_free_codes()
    codes[code] = {"used": False}
    save_free_codes(codes)
    print(f"[🎁 NEW CODE GENERATED]: {code}")
    return code


def verify_free_code(code: str):
    codes = load_free_codes()
    if code in codes and not codes[code]["used"]:
        codes[code]["used"] = True
        save_free_codes(codes)
        print(f"[✅ FREE CODE ACCEPTED]: {code}")
        return True
    print(f"[❌ INVALID/USED CODE]: {code}")
    return False

# ------------------------------------------------------------------
# 5️⃣ Socials
# ------------------------------------------------------------------
@app.context_processor
def inject_socials():
    return dict(
        tiktok_url="https://www.tiktok.com/@neptunee7777",
        instagram_url="https://www.instagram.com/kendallm16",
    )

# ------------------------------------------------------------------
# 6️⃣ Routes
# ------------------------------------------------------------------
@app.route("/")
def index():
    return render_template("index.html")


@app.route("/quiz")
def quiz():
    return render_template("quiz.html")


# 🔐 Owner-only: Generate free codes
@app.route("/generate-free-code")
def make_free_code():
    key = request.args.get("key", "")
    if key != OWNER_SECRET:
        abort(403)
    code = generate_free_code()
    return jsonify({"new_code": code})


# ✅ Verify free codes from quiz
@app.route("/verify-free-code", methods=["POST"])
def api_verify_free_code():
    data = request.get_json() or {}
    code = (data.get("code") or "").strip().upper()
    if not code:
        return jsonify({"valid": False, "error": "No code provided."}), 400

    if verify_free_code(code):
        # mark this session as paid – DO NOT overwrite latest_code here
        session["paid"] = True
        return jsonify({"valid": True})

    return jsonify({"valid": False, "error": "Invalid or already used."}), 400


# 🧠 Save quiz code to session (from frontend)
@app.route("/api/set-latest-code", methods=["POST"])
def set_latest_code():
    data = request.get_json() or {}
    code = data.get("code", "")
    if not code:
        return jsonify({"success": False, "error": "No code provided"}), 400
    session["latest_code"] = code
    print(f"[🧠 SAVED QUIZ CODE]: {code}")
    return jsonify({"success": True})


# 💳 Stripe Checkout
@app.route("/create-checkout-session")
def create_checkout_session():
    """
    We assume /api/set-latest-code has already stored the user's code.
    Do NOT overwrite latest_code here.
    """
    user_id = secrets.token_hex(6)
    checkout_token = secrets.token_urlsafe(16)

    session["user_id"] = user_id
    session["checkout_token"] = checkout_token  # secret random value for this flow

    try:
        stripe_session = stripe.checkout.Session.create(
            mode="payment",
            payment_method_types=["card"],
            line_items=[{
                "price_data": {
                    "currency": "usd",
                    "product_data": {"name": "Big 5 Detailed Archetype Report"},
                    "unit_amount": 99,
                },
                "quantity": 1
            }],
            # include both Stripe session_id and our own secret token
            success_url=f"{DOMAIN}/purchase-success?session_id={{CHECKOUT_SESSION_ID}}&token={checkout_token}",
            cancel_url=f"{DOMAIN}/",
        )

        # store Stripe's session id in our Flask session for verification
        session["checkout_session_id"] = stripe_session.id

        return redirect(stripe_session.url)
    except Exception as e:
        print("Stripe error:", e)
        return f"Stripe session creation failed: {e}", 500


@app.route("/purchase-success")
def purchase_success():
    """
    This route is called only by Stripe's redirect.
    We verify:
      1. The session_id matches the one we stored.
      2. The token matches the random one we stored.
      3. Stripe says the session is actually PAID.
    Manually typing /purchase-success will not work.
    """
    session_id = request.args.get("session_id", "")
    token = request.args.get("token", "")

    expected_id = session.get("checkout_session_id")
    expected_token = session.get("checkout_token")

    if not session_id or not token or session_id != expected_id or token != expected_token:
        print("[SECURITY] Invalid purchase-success attempt.")
        abort(403)

    # Verify with Stripe that this checkout session is paid
    try:
        stripe_session = stripe.checkout.Session.retrieve(session_id)
        if stripe_session.payment_status != "paid":
            print("[SECURITY] Stripe session not paid.")
            abort(403)
    except Exception as e:
        print("[Stripe verify error]", e)
        abort(403)

    # All good — mark user as paid and clear transient checkout data
    session["paid"] = True
    session.pop("checkout_session_id", None)
    session.pop("checkout_token", None)

    return redirect("/report")


# 🔒 Secure report route (with archetype name)
@app.route("/report")
def report():
    if not session.get("paid"):
        return redirect("/")

    code = session.get("latest_code", "Medium-Medium-Medium-Medium-Medium")
    archetype_name = ARCHETYPES.get(code, None)
    detailed_text = DETAILED_BY_CODE.get(code)

    if not detailed_text and archetype_name:
        detailed_text = DETAILED_BY_NAME.get(archetype_name)

    if not detailed_text:
        detailed_text = "Detailed report not found."

    if not archetype_name:
        archetype_name = "Unknown Archetype"

    return render_template(
        "detailed_report.html",
        archetype=archetype_name,
        traits=code,
        sections={"Detailed Report": detailed_text},
        quote="“Depth rewards patience.”",
    )


@app.route("/api/render-report")
def api_render_report():
    if not session.get("paid"):
        abort(403)

    code = session.get("latest_code", "Medium-Medium-Medium-Medium-Medium")
    archetype_name = ARCHETYPES.get(code, None)
    detailed_text = DETAILED_BY_CODE.get(code)

    if not detailed_text and archetype_name:
        detailed_text = DETAILED_BY_NAME.get(archetype_name)

    if not detailed_text:
        detailed_text = "Detailed report not found."

    if not archetype_name:
        archetype_name = "Unknown Archetype"

    return render_template(
        "detailed_report.html",
        archetype=archetype_name,
        traits=code,
        sections={"Detailed Report": detailed_text},
        quote="“Depth rewards patience.”",
    )


@app.route("/api/download-report")
def download_report():
    if not session.get("paid"):
        abort(403)

    # Prefer the code in the session, but fall back to query param if needed
    code = session.get("latest_code") or request.args.get("code", "")
    if not code:
        abort(400)

    name = ARCHETYPES.get(code, "Unknown")
    detailed_text = DETAILED_BY_CODE.get(code) or DETAILED_BY_NAME.get(name)

    doc = Document()
    doc.add_heading(name, level=1)
    doc.add_paragraph(detailed_text or "Detailed text not found.")

    output = BytesIO()
    doc.save(output)
    output.seek(0)

    return send_file(
        output,
        as_attachment=True,
        download_name=f"{name.replace(' ', '_')}_Detailed_Report.docx",
        mimetype="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    )

# ------------------------------------------------------------------
# 🏁 Run Flask
# ------------------------------------------------------------------
if __name__ == "__main__":
    # debug=True is fine for local; in production you’ll run via gunicorn/https
    app.run(debug=True)