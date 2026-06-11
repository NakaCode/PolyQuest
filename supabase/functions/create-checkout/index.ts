// Supabase Edge Function: create-checkout
// Cria uma preferência de pagamento no Mercado Pago e retorna a URL do checkout.
//
// POST { "email": "comprador@email.com", "coupon": "GAMER10" }
// Retorna: { "url": "...", "original_price": 9.99, "final_price": 8.99, "discount": 1.00, "coupon_applied": "GAMER10" }

import { serve } from "https://deno.land/std@0.168.0/http/server.ts";
import { createClient } from "https://esm.sh/@supabase/supabase-js@2";

const ALLOWED_ORIGINS = [
  "https://polyquest.store",
  "https://www.polyquest.store",
];

function corsFor(req: Request): Record<string, string> {
  const origin = req.headers.get("Origin") ?? "";
  const allow = ALLOWED_ORIGINS.includes(origin) ? origin : ALLOWED_ORIGINS[0];
  return {
    "Access-Control-Allow-Origin": allow,
    "Access-Control-Allow-Headers": "authorization, x-client-info, apikey, content-type",
    "Vary": "Origin",
  };
}

const BASE_PRICE = 9.99;

serve(async (req) => {
  const corsHeaders = corsFor(req);
  if (req.method === "OPTIONS") {
    return new Response("ok", { headers: corsHeaders });
  }

  try {
    const MP_ACCESS_TOKEN = Deno.env.get("MP_ACCESS_TOKEN") ?? "";
    const SUPABASE_URL = Deno.env.get("SUPABASE_URL") ?? "";

    const supabase = createClient(
      SUPABASE_URL,
      Deno.env.get("SUPABASE_SERVICE_ROLE_KEY") ?? ""
    );

    let email = "";
    let couponCode = "";
    try {
      const body = await req.json();
      email = body?.email ?? "";
      couponCode = (body?.coupon ?? "").trim().toUpperCase();
    } catch {
      // body vazio é ok
    }

    // ── Validar cupom ────────────────────────────────────────
    let finalPrice = BASE_PRICE;
    let discount = 0;
    let couponApplied = "";

    if (couponCode) {
      const { data: coupon } = await supabase
        .from("coupons")
        .select("*")
        .eq("code", couponCode)
        .eq("active", true)
        .single();

      if (!coupon) {
        return new Response(
          JSON.stringify({ ok: false, error: "Cupom inválido ou expirado." }),
          { status: 400, headers: { ...corsHeaders, "Content-Type": "application/json" } }
        );
      }

      // Verificar expiração
      if (coupon.expires_at && new Date(coupon.expires_at) < new Date()) {
        return new Response(
          JSON.stringify({ ok: false, error: "Este cupom expirou." }),
          { status: 400, headers: { ...corsHeaders, "Content-Type": "application/json" } }
        );
      }

      // Verificar limite de usos
      if (coupon.max_uses !== null && coupon.current_uses >= coupon.max_uses) {
        return new Response(
          JSON.stringify({ ok: false, error: "Este cupom atingiu o limite de usos." }),
          { status: 400, headers: { ...corsHeaders, "Content-Type": "application/json" } }
        );
      }

      // Calcular desconto
      if (coupon.discount_type === "percent") {
        discount = Math.round(BASE_PRICE * (coupon.discount_value / 100) * 100) / 100;
      } else {
        discount = Number(coupon.discount_value);
      }

      finalPrice = Math.max(Math.round((BASE_PRICE - discount) * 100) / 100, 0.01);
      couponApplied = coupon.code;
    }

    // URL de retorno após pagamento
    const successUrl = `${SUPABASE_URL}/functions/v1/mp-webhook?action=success`;

    const preference: Record<string, unknown> = {
      items: [
        {
          title: "PolyQuest Premium",
          description: couponApplied
            ? `Licença vitalícia — cupom ${couponApplied} aplicado (${discount > 0 ? `-R$${discount.toFixed(2)}` : ""})`
            : "Licença vitalícia — perfis, glossário, tema custom e todas as atualizações futuras.",
          quantity: 1,
          currency_id: "BRL",
          unit_price: finalPrice,
        },
      ],
      back_urls: {
        success: successUrl,
        failure: successUrl,
        pending: successUrl,
      },
      auto_return: "approved",
      notification_url: `${SUPABASE_URL}/functions/v1/mp-webhook`,
      statement_descriptor: "POLYQUEST",
      expires: false,
      metadata: {
        coupon_code: couponApplied || null,
        original_price: BASE_PRICE,
        final_price: finalPrice,
      },
    };

    // Se tiver email, preenche o payer
    if (email) {
      preference.payer = { email };
    }

    const mpResponse = await fetch("https://api.mercadopago.com/checkout/preferences", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "Authorization": `Bearer ${MP_ACCESS_TOKEN}`,
      },
      body: JSON.stringify(preference),
    });

    const mpData = await mpResponse.json();

    if (!mpResponse.ok) {
      console.error("MP error:", mpData);
      return new Response(
        JSON.stringify({ ok: false, error: "Erro ao criar checkout." }),
        { status: 500, headers: { ...corsHeaders, "Content-Type": "application/json" } }
      );
    }

    return new Response(
      JSON.stringify({
        ok: true,
        url: mpData.init_point,
        sandbox_url: mpData.sandbox_init_point,
        original_price: BASE_PRICE,
        final_price: finalPrice,
        discount,
        coupon_applied: couponApplied || null,
      }),
      { headers: { ...corsHeaders, "Content-Type": "application/json" } }
    );

  } catch (err) {
    console.error("Error:", err);
    return new Response(
      JSON.stringify({ ok: false, error: "Erro interno." }),
      { status: 500, headers: { ...corsHeaders, "Content-Type": "application/json" } }
    );
  }
});
