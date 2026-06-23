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
  // 32 símbolos → 256 % 32 === 0, logo módulo não introduz viés.
  const chars = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789";
  const bytes = new Uint8Array(12);
  crypto.getRandomValues(bytes);
  let out = "";
  for (let i = 0; i < 12; i++) {
    out += chars[bytes[i] % 32];
    if (i === 3 || i === 7) out += "-";
  }
  return `PQ-${out}`;
}

// Comparação em tempo constante — evita timing attack na senha do admin.
function safeEqual(a: string, b: string): boolean {
  const enc = new TextEncoder();
  const ab = enc.encode(a);
  const bb = enc.encode(b);
  if (ab.length !== bb.length) return false;
  let diff = 0;
  for (let i = 0; i < ab.length; i++) diff |= ab[i] ^ bb[i];
  return diff === 0;
}

function getSupabase() {
  return createClient(
    Deno.env.get("SUPABASE_URL") ?? "",
    Deno.env.get("SUPABASE_SERVICE_ROLE_KEY") ?? ""
  );
}

// IP do cliente (primeiro item do x-forwarded-for inserido pela borda).
function clientIp(req: Request): string {
  const xff = req.headers.get("x-forwarded-for") ?? "";
  return xff.split(",")[0].trim() || "unknown";
}

// Rate limiting: bloqueia o IP após MAX_FAILS senhas erradas em WINDOW_MIN min.
const MAX_FAILS = 8;
const WINDOW_MIN = 15;

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

    const supabase = getSupabase();
    const ip = clientIp(req);

    // ── Rate limiting por IP ──────────────────────────────────
    // Conta senhas erradas recentes deste IP; bloqueia se passou do limite.
    const since = new Date(Date.now() - WINDOW_MIN * 60 * 1000).toISOString();
    const { count: fails } = await supabase
      .from("admin_login_attempts")
      .select("id", { count: "exact", head: true })
      .eq("ip", ip)
      .gte("created_at", since);

    if ((fails ?? 0) >= MAX_FAILS) {
      return json({ ok: false, error: "Muitas tentativas. Tente novamente em alguns minutos." }, 429);
    }

    // ── Verificação de senha ─────────────────────────────────
    // Sem senha no ambiente, o painel fica bloqueado (nunca cai em padrão
    // conhecido). Comparação em tempo constante e limite de tamanho.
    const passOk =
      !!ADMIN_PASSWORD &&
      typeof password === "string" &&
      password.length <= 256 &&
      safeEqual(password, ADMIN_PASSWORD);

    if (!passOk) {
      // Registra a falha (alimenta o rate limiting).
      await supabase.from("admin_login_attempts").insert({ ip });
      return json({ ok: false, error: "Senha incorreta." }, 401);
    }

    // Sucesso: zera as falhas deste IP e limpa registros antigos (>1 dia).
    await supabase.from("admin_login_attempts").delete().eq("ip", ip);
    await supabase
      .from("admin_login_attempts")
      .delete()
      .lt("created_at", new Date(Date.now() - 24 * 60 * 60 * 1000).toISOString());

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
