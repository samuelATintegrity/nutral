// Vercel serverless function — receives contact form submissions
// and forwards them via Resend to the site owner.
//
// Required env var on Vercel: RESEND_API_KEY
// Optional: CONTACT_TO (override destination), CONTACT_FROM (override sender)

const DEFAULT_TO = "samuelthompson21@yahoo.com";
const DEFAULT_FROM = "Nūtral Contact <briefs@nutral.news>";

function escapeHtml(s) {
  return String(s)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

export default async function handler(req, res) {
  if (req.method !== "POST") {
    res.setHeader("Allow", "POST");
    return res.status(405).json({ error: "Method not allowed" });
  }

  const apiKey = process.env.RESEND_API_KEY;
  if (!apiKey) {
    return res.status(500).json({ error: "Server not configured (missing RESEND_API_KEY)." });
  }

  let body = req.body;
  if (typeof body === "string") {
    try { body = JSON.parse(body); } catch { body = {}; }
  }
  body = body || {};

  const name = String(body.name || "").trim();
  const email = String(body.email || "").trim();
  const message = String(body.message || "").trim();
  const company = String(body.company || "").trim(); // honeypot

  // Honeypot: silently succeed so bots don't learn anything.
  if (company) {
    return res.status(200).json({ ok: true });
  }

  if (!name || name.length > 120) {
    return res.status(400).json({ error: "Invalid name." });
  }
  if (!email || email.length > 200 || !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) {
    return res.status(400).json({ error: "Invalid email address." });
  }
  if (!message || message.length > 5000) {
    return res.status(400).json({ error: "Message is required (max 5000 chars)." });
  }

  const to = process.env.CONTACT_TO || DEFAULT_TO;
  const from = process.env.CONTACT_FROM || DEFAULT_FROM;

  const subject = `[Nūtral contact] ${name}`;
  const text =
    `New message from the Nūtral contact form\n` +
    `--------------------------------------------\n` +
    `Name:    ${name}\n` +
    `Email:   ${email}\n\n` +
    `${message}\n`;

  const html =
    `<div style="font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;line-height:1.5;color:#1a1a1a;">` +
    `<p style="color:#5c5a55;margin:0 0 12px;">New message from the Nūtral contact form.</p>` +
    `<p style="margin:0 0 6px;"><strong>Name:</strong> ${escapeHtml(name)}</p>` +
    `<p style="margin:0 0 18px;"><strong>Email:</strong> <a href="mailto:${escapeHtml(email)}">${escapeHtml(email)}</a></p>` +
    `<div style="white-space:pre-wrap;padding:16px;background:#fcfaf3;border:1px solid #d9d3c4;border-radius:8px;">${escapeHtml(message)}</div>` +
    `</div>`;

  try {
    const resendRes = await fetch("https://api.resend.com/emails", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${apiKey}`,
      },
      body: JSON.stringify({
        from,
        to: [to],
        reply_to: email,
        subject,
        text,
        html,
      }),
    });

    if (!resendRes.ok) {
      const detail = await resendRes.text().catch(() => "");
      console.error("Resend error", resendRes.status, detail);
      return res.status(502).json({ error: "Could not send message right now. Please try again later." });
    }

    return res.status(200).json({ ok: true });
  } catch (err) {
    console.error("Contact handler error", err);
    return res.status(500).json({ error: "Unexpected error. Please try again." });
  }
}
