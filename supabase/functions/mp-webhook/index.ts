// Supabase Edge Function: mp-webhook
// Recebe notificação do Mercado Pago quando pagamento é aprovado.
// Gera chave de licença e salva no banco.
// Também serve como página de sucesso (redirect após pagamento).

import { serve } from "https://deno.land/std@0.168.0/http/server.ts";
import { createClient } from "https://esm.sh/@supabase/supabase-js@2";

const corsHeaders = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Headers": "authorization, x-client-info, apikey, content-type",
};

function generateKey(): string {
  const chars = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789";
  const segment = () => {
    let s = "";
    for (let i = 0; i < 4; i++) {
      s += chars[Math.floor(Math.random() * chars.length)];
    }
    return s;
  };
  return `PQ-${segment()}-${segment()}-${segment()}`;
}

async function hmacSha256Hex(secret: string, message: string): Promise<string> {
  const enc = new TextEncoder();
  const keyData = await crypto.subtle.importKey(
    "raw", enc.encode(secret), { name: "HMAC", hash: "SHA-256" }, false, ["sign"],
  );
  const sig = await crypto.subtle.sign("HMAC", keyData, enc.encode(message));
  return Array.from(new Uint8Array(sig)).map((b) => b.toString(16).padStart(2, "0")).join("");
}

// Valida a assinatura HMAC enviada pelo Mercado Pago no header x-signature.
// Manifesto: id:<data.id>;request-id:<x-request-id>;ts:<ts>;
async function verifyMpSignature(req: Request, url: URL, dataId: string, secret: string): Promise<boolean> {
  const xSignature = req.headers.get("x-signature") ?? "";
  const xRequestId = req.headers.get("x-request-id") ?? "";
  if (!xSignature) return false;

  const parts: Record<string, string> = {};
  for (const p of xSignature.split(",")) {
    const idx = p.indexOf("=");
    if (idx > 0) parts[p.slice(0, idx).trim()] = p.slice(idx + 1).trim();
  }
  const ts = parts["ts"] ?? "";
  const v1 = parts["v1"] ?? "";
  if (!ts || !v1) return false;

  // data.id vem da query string quando presente; senão, do corpo (paymentId já extraído)
  const idFromQuery = url.searchParams.get("data.id") ?? url.searchParams.get("id");
  const id = (idFromQuery ?? dataId ?? "").toLowerCase();
  const manifest = `id:${id};request-id:${xRequestId};ts:${ts};`;
  const expected = await hmacSha256Hex(secret, manifest);

  // comparação em tempo constante
  if (expected.length !== v1.length) return false;
  let diff = 0;
  for (let i = 0; i < expected.length; i++) diff |= expected.charCodeAt(i) ^ v1.charCodeAt(i);
  return diff === 0;
}

async function getPaymentInfo(paymentId: string, token: string) {
  const res = await fetch(`https://api.mercadopago.com/v1/payments/${paymentId}`, {
    headers: { "Authorization": `Bearer ${token}` },
  });
  if (!res.ok) return null;
  return await res.json();
}

async function getPreferenceMetadata(preferenceId: string, token: string): Promise<Record<string, unknown> | null> {
  if (!preferenceId) return null;
  try {
    const res = await fetch(`https://api.mercadopago.com/checkout/preferences/${preferenceId}`, {
      headers: { "Authorization": `Bearer ${token}` },
    });
    if (!res.ok) return null;
    const pref = await res.json();
    return pref.metadata ?? null;
  } catch {
    return null;
  }
}

async function sendLicenseEmail(to: string, key: string) {
  const RESEND_API_KEY = Deno.env.get("RESEND_API_KEY") ?? "";
  if (!RESEND_API_KEY || to === "desconhecido@email.com") return;

  const html = `
<!DOCTYPE html>
<html>
<head><meta charset="UTF-8"></head>
<body style="margin:0;padding:0;background:#0a0e18;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;">
  <div style="max-width:520px;margin:40px auto;background:#0d1422;border:1px solid #1e2d48;border-radius:20px;padding:48px 40px;text-align:center;">
    <h1 style="font-size:28px;font-weight:900;color:#9b30ff;margin:0 0 8px;">PolyQuest Premium</h1>
    <p style="color:#34d399;font-size:16px;font-weight:700;margin:0 0 24px;">Compra conclu\u00edda com sucesso!</p>
    <div style="background:#111c30;border:2px solid #00e5ff;border-radius:12px;padding:24px;margin:0 0 24px;">
      <p style="color:#5a7a9a;font-size:14px;margin:0 0 8px;">Sua chave de licen\u00e7a:</p>
      <p style="font-size:28px;font-weight:900;color:#00e5ff;letter-spacing:3px;margin:0;font-family:monospace;">${key}</p>
    </div>
    <div style="text-align:left;background:#0a0e18;border:1px solid #1e2d48;border-radius:12px;padding:20px 24px;margin:0 0 24px;">
      <p style="color:#5a7a9a;font-size:14px;margin:0 0 8px;"><strong style="color:#d8f0ff;">1.</strong> Copie a chave acima</p>
      <p style="color:#5a7a9a;font-size:14px;margin:0 0 8px;"><strong style="color:#d8f0ff;">2.</strong> Abra o PolyQuest \u2192 Configura\u00e7\u00f5es</p>
      <p style="color:#5a7a9a;font-size:14px;margin:0;"><strong style="color:#d8f0ff;">3.</strong> Cole a chave e clique <strong style="color:#d8f0ff;">Ativar</strong></p>
    </div>
    <p style="color:#5a7a9a;font-size:12px;margin:0;">Guarde esta chave! Ela \u00e9 vinculada \u00e0 sua m\u00e1quina.<br>D\u00favidas? <a href="mailto:contato.naka@hotmail.com" style="color:#00e5ff;">contato.naka@hotmail.com</a> | <a href="https://discord.gg/b45u2gN7Zx" style="color:#7289da;">Discord</a></p>
  </div>
</body>
</html>`;

  await fetch("https://api.resend.com/emails", {
    method: "POST",
    headers: {
      "Authorization": `Bearer ${RESEND_API_KEY}`,
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      from: "PolyQuest <noreply@polyquest.store>",
      to: [to],
      subject: "Sua chave PolyQuest Premium",
      html,
    }),
  });
}

async function processPayment(paymentId: string, token: string, supabase: any): Promise<{ key: string; email: string; pending?: boolean } | null> {
  const payment = await getPaymentInfo(paymentId, token);
  if (!payment) return null;

  // Se pagamento ainda não aprovado, retorna status pendente
  if (payment.status !== "approved") {
    return { key: "", email: "", pending: true };
  }

  const email = payment.payer?.email ?? payment.additional_info?.payer?.email ?? "desconhecido@email.com";

  // Verifica se já existe licença para este payment_id (evita duplicata)
  const { data: existing } = await supabase
    .from("licenses")
    .select("key, email")
    .eq("payment_id", paymentId)
    .limit(1)
    .single();

  if (existing) {
    return { key: existing.key, email: existing.email };
  }

  // Cupom: tenta do metadata do payment, senão busca da preferência original
  let couponCode: string | null = payment.metadata?.coupon_code ?? null;
  if (!couponCode) {
    const prefMetadata = await getPreferenceMetadata(payment.order?.id ?? payment.preference_id ?? "", token);
    couponCode = (prefMetadata?.coupon_code as string) ?? null;
  }

  // Valor efetivamente pago
  const amountPaid: number | null = payment.transaction_amount ?? null;

  // Gera chave única
  let key = generateKey();
  let attempts = 0;
  while (attempts < 10) {
    const { data: dup } = await supabase
      .from("licenses")
      .select("id")
      .eq("key", key)
      .single();
    if (!dup) break;
    key = generateKey();
    attempts++;
  }

  // Salva no banco com cupom, valor pago e payment_id
  const { error } = await supabase.from("licenses").insert({
    key,
    email,
    max_devices: 1,
    coupon_code: couponCode,
    amount_paid: amountPaid,
    payment_id: paymentId,
  });

  if (error) {
    console.error("DB insert error:", error);
    // Race condition: outro request já inseriu esta licença — busca a existente
    const { data: raceExisting } = await supabase
      .from("licenses")
      .select("key, email")
      .eq("payment_id", paymentId)
      .limit(1)
      .single();
    if (raceExisting) {
      return { key: raceExisting.key, email: raceExisting.email };
    }
    return null;
  }

  // Incrementa uso do cupom (atomicamente via RPC para evitar race condition)
  if (couponCode) {
    await supabase.rpc("increment_coupon_usage", { coupon_code: couponCode });
  }

  console.log(`Licença criada: ${key} para ${email} (payment: ${paymentId}, cupom: ${couponCode ?? "nenhum"})`);

  // Envia e-mail com a chave para o comprador
  await sendLicenseEmail(email, key).catch((err) =>
    console.error("Erro ao enviar e-mail:", err)
  );

  return { key, email };
}

// Página HTML de sucesso mostrada ao comprador
function successPage(key: string | null, email: string, pending = false, paymentId: string | null = null): string {
  let keyDisplay: string;

  if (key) {
    keyDisplay = `<div style="background:#111c30;border:2px solid #00e5ff;border-radius:12px;padding:24px;margin:24px 0;text-align:center;">
         <p style="color:#5a7a9a;font-size:14px;margin:0 0 8px;">Sua chave de licença:</p>
         <p style="font-size:28px;font-weight:900;color:#00e5ff;letter-spacing:3px;margin:0;font-family:monospace;" id="key">${key}</p>
         <button onclick="navigator.clipboard.writeText('${key}');this.textContent='Copiado!'" style="margin-top:16px;background:#9b30ff;color:#fff;border:none;border-radius:8px;padding:10px 24px;font-size:14px;font-weight:700;cursor:pointer;">Copiar chave</button>
       </div>`;
  } else if (pending) {
    keyDisplay = `<div style="background:#111c30;border:2px solid #f9e2af;border-radius:12px;padding:24px;margin:24px 0;text-align:center;">
         <p style="color:#f9e2af;font-size:16px;margin:0;">Aguardando confirmação do pagamento...</p>
         <p style="color:#5a7a9a;font-size:14px;margin:8px 0 0;">A página vai atualizar automaticamente. Não feche esta aba.</p>
         <div style="margin-top:16px;"><div style="border:3px solid #1e2d48;border-top:3px solid #00e5ff;border-radius:50%;width:32px;height:32px;animation:spin 1s linear infinite;margin:0 auto;"></div></div>
       </div>
       <style>@keyframes spin{0%{transform:rotate(0deg)}100%{transform:rotate(360deg)}}</style>
       <script>setTimeout(()=>location.reload(),5000);</script>`;
  } else {
    keyDisplay = `<div style="background:#111c30;border:2px solid #f9e2af;border-radius:12px;padding:24px;margin:24px 0;text-align:center;">
         <p style="color:#f9e2af;font-size:16px;margin:0;">Não foi possível gerar sua chave automaticamente.</p>
         <p style="color:#5a7a9a;font-size:14px;margin:8px 0 0;">Entre em contato informando seu e-mail de compra: <strong>contato.naka@hotmail.com</strong> ou pelo <a href="https://discord.gg/b45u2gN7Zx" style="color:#7289da;">Discord</a></p>
       </div>`;
  }

  return `<!DOCTYPE html>
<html lang="pt-BR">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>PolyQuest — Compra concluída</title>
  <style>
    *{box-sizing:border-box;margin:0;padding:0}
    body{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif;background:#0a0e18;color:#d8f0ff;min-height:100vh;display:flex;align-items:center;justify-content:center;padding:24px}
    .card{background:#0d1422;border:1px solid #1e2d48;border-radius:20px;padding:48px 40px;max-width:520px;width:100%;text-align:center;box-shadow:0 0 80px rgba(155,48,255,.1)}
    h1{font-size:28px;font-weight:900;margin-bottom:8px;background:linear-gradient(135deg,#d8f0ff 20%,#9b30ff 55%,#00e5ff 100%);-webkit-background-clip:text;-webkit-text-fill-color:transparent;background-clip:text}
    .subtitle{color:#34d399;font-size:16px;font-weight:700;margin-bottom:24px}
    .steps{text-align:left;background:#0a0e18;border:1px solid #1e2d48;border-radius:12px;padding:20px 24px;margin:24px 0}
    .steps p{color:#5a7a9a;font-size:14px;margin-bottom:8px;line-height:1.6}
    .steps strong{color:#d8f0ff}
    .footer{color:#5a7a9a;font-size:12px;margin-top:24px}
    .footer a{color:#00e5ff}
  </style>
</head>
<body>
  <div class="card">
    <h1>PolyQuest Premium</h1>
    <p class="subtitle">Compra concluída com sucesso!</p>
    ${keyDisplay}
    <div class="steps">
      <p><strong>1.</strong> Copie a chave acima</p>
      <p><strong>2.</strong> Abra o PolyQuest → Configurações</p>
      <p><strong>3.</strong> Cole a chave no campo "Chave de licença" e clique <strong>Ativar</strong></p>
    </div>
    <p class="footer">Guarde esta chave! Ela é vinculada à sua máquina.<br>Dúvidas? <a href="mailto:contato.naka@hotmail.com">contato.naka@hotmail.com</a> | <a href="https://discord.gg/b45u2gN7Zx" style="color:#7289da;">Discord</a></p>
  </div>
</body>
</html>`;
}

serve(async (req) => {
  if (req.method === "OPTIONS") {
    return new Response("ok", { headers: corsHeaders });
  }

  const MP_ACCESS_TOKEN = Deno.env.get("MP_ACCESS_TOKEN") ?? "";
  const supabase = createClient(
    Deno.env.get("SUPABASE_URL") ?? "",
    Deno.env.get("SUPABASE_SERVICE_ROLE_KEY") ?? ""
  );

  const url = new URL(req.url);

  // ── Redirect de sucesso do Mercado Pago (GET) ──────────────
  if (req.method === "GET") {
    const paymentId = url.searchParams.get("payment_id") ?? url.searchParams.get("collection_id");
    const siteUrl = "https://www.polyquest.store";

    if (paymentId) {
      const result = await processPayment(paymentId, MP_ACCESS_TOKEN, supabase);
      if (result && result.pending) {
        // Pagamento pendente — redireciona com status pending e payment_id para polling
        return Response.redirect(`${siteUrl}?purchase=pending&payment_id=${paymentId}`, 302);
      } else if (result && result.key) {
        // Sucesso — redireciona com a chave
        return Response.redirect(`${siteUrl}?purchase=success&key=${encodeURIComponent(result.key)}`, 302);
      }
    }

    // Falha — redireciona sem chave
    return Response.redirect(`${siteUrl}?purchase=error`, 302);
  }

  // ── Webhook do Mercado Pago (POST) ─────────────────────────
  if (req.method === "POST") {
    try {
      const body = await req.json();

      // Mercado Pago envia { "action": "payment.created", "data": { "id": "123" } }
      // ou { "type": "payment", "data": { "id": "123" } }
      const paymentId = body?.data?.id?.toString() ?? "";

      if (!paymentId) {
        return new Response(
          JSON.stringify({ ok: true, message: "No payment ID" }),
          { headers: { ...corsHeaders, "Content-Type": "application/json" } }
        );
      }

      // Validação da assinatura do Mercado Pago (defesa em profundidade).
      // Só roda se MP_WEBHOOK_SECRET estiver configurado. Por padrão apenas
      // registra divergências; rejeita somente se MP_WEBHOOK_ENFORCE=true.
      const MP_WEBHOOK_SECRET = Deno.env.get("MP_WEBHOOK_SECRET") ?? "";
      if (MP_WEBHOOK_SECRET) {
        const validSig = await verifyMpSignature(req, url, paymentId, MP_WEBHOOK_SECRET);
        if (!validSig) {
          console.warn(`MP signature inválida (payment: ${paymentId})`);
          if (Deno.env.get("MP_WEBHOOK_ENFORCE") === "true") {
            return new Response(
              JSON.stringify({ ok: false, error: "invalid signature" }),
              { status: 401, headers: { ...corsHeaders, "Content-Type": "application/json" } }
            );
          }
        }
      }

      const result = await processPayment(paymentId, MP_ACCESS_TOKEN, supabase);

      // Se o pagamento ainda está pendente ou falhou, retorna 500 para o MP retentar
      if (!result || result.pending) {
        return new Response(
          JSON.stringify({ ok: false, message: "Payment not yet approved or processing failed" }),
          { status: 500, headers: { ...corsHeaders, "Content-Type": "application/json" } }
        );
      }

      return new Response(
        JSON.stringify({ ok: true, processed: true }),
        { headers: { ...corsHeaders, "Content-Type": "application/json" } }
      );

    } catch (err) {
      console.error("Webhook error:", err);
      return new Response(
        JSON.stringify({ ok: false }),
        { status: 500, headers: { ...corsHeaders, "Content-Type": "application/json" } }
      );
    }
  }

  return new Response("Method not allowed", { status: 405 });
});
