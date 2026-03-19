// Utility: get query parameter
function qs(k) {
  return new URL(location.href).searchParams.get(k);
}

// Verify Stripe payment status securely
async function verify(session_id) {
  try {
    const r = await fetch(`/verify-payment?session_id=${encodeURIComponent(session_id)}`);
    const data = await r.json();
    return !!data.paid;
  } catch (err) {
    console.error("Verification failed:", err);
    return false;
  }
}

// Fade helper
function fadeIn(el) {
  el.style.opacity = 0;
  el.style.display = "block";
  let last = +new Date();
  const tick = function() {
    el.style.opacity = +el.style.opacity + (new Date() - last) / 400;
    last = +new Date();
    if (+el.style.opacity < 1) requestAnimationFrame(tick);
  };
  tick();
}

// Main async logic
(async function init() {
  const gate = document.getElementById("gate");
  const reportDiv = document.getElementById("report");

  const session_id = qs("session_id");
  const code = qs("code") || "Medium-Medium-Medium-Medium-Medium";
  const sub = qs("sub"); // optional subtype
  const freeCode = qs("free"); // for one-time free access

  // Check referral (for subtype-based navigation)
  const fromSubtype = document.referrer.includes("/subtype");

  let verified = false;

  // 1️⃣ Check if user came from Stripe checkout
  if (session_id) {
    verified = await verify(session_id);
  }

  // 2️⃣ If not Stripe, try validating free access code (via backend)
  if (!verified && freeCode) {
    try {
      const resp = await fetch("/verify-free-code", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ code: freeCode })
      });
      const data = await resp.json();
      verified = !!data.valid;
    } catch (e) {
      console.error("Free code verification failed:", e);
    }
  }

  // 3️⃣ If still unverified and not from subtype quiz, block access
  if (!verified && !fromSubtype) {
    gate.innerHTML = `
      <p>❌ Access denied — payment not verified.</p>
      <p><a href="/">Return to test</a></p>
    `;
    return;
  }

  // 4️⃣ Load report securely
  try {
    const response = await fetch(`/api/render-report?code=${encodeURIComponent(code)}${sub ? `&sub=${encodeURIComponent(sub)}` : ""}`);
    const html = await response.text();

    gate.classList.add("hidden");
    reportDiv.classList.remove("hidden");
    fadeIn(reportDiv);
    reportDiv.innerHTML = html;

    console.log("[Morrowland] Report loaded successfully");
  } catch (e) {
    gate.innerHTML = `<p>⚠️ Error loading report. Please try again later.</p>`;
    console.error("Report load failed:", e);
  }
})();