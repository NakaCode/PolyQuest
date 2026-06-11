// Supabase Edge Function: admin-panel (API JSON)
// Painel administrativo para gerenciar licenças do PolyQuest.
// Protegido por senha definida na variável de ambiente ADMIN_PASSWORD.

import { serve } from "https://deno.land/std@0.168.0/http/server.ts";
import { createClient } from "https://esm.sh/@supabase/supabase-js@2";

const corsHeaders = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Headers": "authorization, x-client-info, apikey, content-type",
};

function json(data: unknown, status = 200) {
  return new Response(JSON.stringify(data), {
    status,
    headers: { ...corsHeaders, "Content-Type": "application/json" },
  });
}

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

function getSupabase() {
  return createClient(
    Deno.env.get("SUPABASE_URL") ?? "",
    Deno.env.get("SUPABASE_SERVICE_ROLE_KEY") ?? ""
  );
}

serve(async (req) => {
  if (req.method === "OPTIONS") {
    return new Response("ok", { headers: corsHeaders });
  }

  if (req.method !== "POST") {
    return json({ error: "Use POST" }, 405);
  }

  const ADMIN_PASSWORD = Deno.env.get("ADMIN_PASSWORD") ?? "";

  try {
    const body = await req.json();
    const { action, password } = body;

    // Sem senha configurada no ambiente, o painel fica bloqueado
    // (nunca cai em um valor padrão conhecido).
    if (!ADMIN_PASSWORD || password !== ADMIN_PASSWORD) {
      return json({ ok: false, error: "Senha incorreta." }, 401);
    }

    const supabase = getSupabase();

    // ── Listar licenças ──────────────────────────────────────
    if (action === "list") {
      const { data, error } = await supabase
        .from("licenses")
        .select("*")
        .order("created_at", { ascending: false });

      if (error) return json({ ok: false, error: error.message }, 500);
      return json({ ok: true, licenses: data });
    }

    // ── Gerar chaves ─────────────────────────────────────────
    if (action === "generate") {
      const email = body.email ?? "manual@admin";
      const nota = body.nota ?? "";
      const qty = Math.min(parseInt(body.qty ?? "1") || 1, 50);
      const generated: string[] = [];

      for (let i = 0; i < qty; i++) {
        let key = generateKey();
        let attempts = 0;
        while (attempts < 10) {
          const { data: dup } = await supabase.from("licenses").select("id").eq("key", key).single();
          if (!dup) break;
          key = generateKey();
          attempts++;
        }
        const { error } = await supabase.from("licenses").insert({ key, email, nota });
        if (!error) generated.push(key);
      }

      return json({ ok: true, keys: generated });
    }

    // ── Resetar ativação ─────────────────────────────────────
    if (action === "reset") {
      const { error } = await supabase
        .from("licenses")
        .update({ hwid: null, activated_at: null })
        .eq("key", body.key ?? "");

      if (error) return json({ ok: false, error: error.message }, 500);
      return json({ ok: true });
    }

    // ── Excluir licença ──────────────────────────────────────
    if (action === "delete") {
      const { error } = await supabase
        .from("licenses")
        .delete()
        .eq("key", body.key ?? "");

      if (error) return json({ ok: false, error: error.message }, 500);
      return json({ ok: true });
    }

    // ── Listar cupons ────────────────────────────────────────
    if (action === "list-coupons") {
      const { data, error } = await supabase
        .from("coupons")
        .select("*")
        .order("created_at", { ascending: false });

      if (error) return json({ ok: false, error: error.message }, 500);

      // Buscar licenças com cupom para calcular usos e faturamento
      const { data: couponLicenses } = await supabase
        .from("licenses")
        .select("coupon_code, amount_paid")
        .not("coupon_code", "is", null);

      const revenueMap: Record<string, { uses: number; revenue: number }> = {};
      if (couponLicenses) {
        for (const lic of couponLicenses) {
          if (!revenueMap[lic.coupon_code]) {
            revenueMap[lic.coupon_code] = { uses: 0, revenue: 0 };
          }
          revenueMap[lic.coupon_code].uses += 1;
          revenueMap[lic.coupon_code].revenue += Number(lic.amount_paid) || 0;
        }
      }

      return json({ ok: true, coupons: data, revenue: revenueMap });
    }

    // ── Criar cupom ────────────────────────────────────────
    if (action === "create-coupon") {
      const code = (body.code ?? "").trim().toUpperCase();
      if (!code) return json({ ok: false, error: "Código do cupom é obrigatório." }, 400);

      const discountType = body.discount_type === "fixed" ? "fixed" : "percent";
      const discountValue = parseFloat(body.discount_value) || 0;
      if (discountValue <= 0) return json({ ok: false, error: "Valor do desconto deve ser maior que zero." }, 400);
      if (discountType === "percent" && discountValue > 100) return json({ ok: false, error: "Desconto percentual não pode exceder 100%." }, 400);

      const maxUses = body.max_uses ? parseInt(body.max_uses) : null;
      const influencer = body.influencer ?? "";
      const expiresAt = body.expires_at || null;

      const { error } = await supabase.from("coupons").insert({
        code,
        discount_type: discountType,
        discount_value: discountValue,
        max_uses: maxUses,
        influencer,
        expires_at: expiresAt,
      });

      if (error) {
        if (error.message?.includes("duplicate")) {
          return json({ ok: false, error: "Já existe um cupom com este código." }, 400);
        }
        return json({ ok: false, error: error.message }, 500);
      }

      return json({ ok: true, code });
    }

    // ── Ativar/desativar cupom ─────────────────────────────
    if (action === "toggle-coupon") {
      const code = (body.code ?? "").trim().toUpperCase();
      const active = body.active ?? false;

      const { error } = await supabase
        .from("coupons")
        .update({ active })
        .eq("code", code);

      if (error) return json({ ok: false, error: error.message }, 500);
      return json({ ok: true });
    }

    // ── Excluir cupom ──────────────────────────────────────
    if (action === "delete-coupon") {
      const code = (body.code ?? "").trim().toUpperCase();

      const { error } = await supabase
        .from("coupons")
        .delete()
        .eq("code", code);

      if (error) return json({ ok: false, error: error.message }, 500);
      return json({ ok: true });
    }

    return json({ ok: false, error: "Ação desconhecida." }, 400);

  } catch (err) {
    return json({ ok: false, error: "Erro interno." }, 500);
  }
});
