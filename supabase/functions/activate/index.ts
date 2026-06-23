// Supabase Edge Function: activate
// Deploy: supabase functions deploy activate
//
// Recebe: { "key": "PQ-XXXX-XXXX-XXXX", "hwid": "abc123..." }
// Retorna: { "ok": true, "activated_at": "..." } ou { "ok": false, "error": "..." }

import { serve } from "https://deno.land/std@0.168.0/http/server.ts";
import { createClient } from "https://esm.sh/@supabase/supabase-js@2";

const corsHeaders = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Headers": "authorization, x-client-info, apikey, content-type",
};

serve(async (req) => {
  if (req.method === "OPTIONS") {
    return new Response("ok", { headers: corsHeaders });
  }

  try {
    const { key, hwid } = await req.json();

    if (!key || !hwid || typeof key !== "string" || typeof hwid !== "string") {
      return new Response(
        JSON.stringify({ ok: false, error: "Chave e hardware ID são obrigatórios." }),
        { status: 400, headers: { ...corsHeaders, "Content-Type": "application/json" } }
      );
    }

    // Limites de tamanho e formato — endpoint público, reduz abuso/armazenamento.
    const normalizedKey = key.trim().toUpperCase();
    if (!/^PQ-[A-Z0-9]{4}-[A-Z0-9]{4}-[A-Z0-9]{4}$/.test(normalizedKey) || hwid.length > 256) {
      return new Response(
        JSON.stringify({ ok: false, error: "Chave de licença não encontrada." }),
        { status: 404, headers: { ...corsHeaders, "Content-Type": "application/json" } }
      );
    }

    const supabase = createClient(
      Deno.env.get("SUPABASE_URL") ?? "",
      Deno.env.get("SUPABASE_SERVICE_ROLE_KEY") ?? ""
    );

    // Busca a licença
    const { data: license, error } = await supabase
      .from("licenses")
      .select("*")
      .eq("key", normalizedKey)
      .single();

    if (error || !license) {
      return new Response(
        JSON.stringify({ ok: false, error: "Chave de licença não encontrada." }),
        { status: 404, headers: { ...corsHeaders, "Content-Type": "application/json" } }
      );
    }

    // Já ativada neste hardware
    if (license.hwid === hwid) {
      return new Response(
        JSON.stringify({ ok: true, activated_at: license.activated_at }),
        { headers: { ...corsHeaders, "Content-Type": "application/json" } }
      );
    }

    // Já ativada em outro hardware
    if (license.hwid && license.hwid !== hwid) {
      return new Response(
        JSON.stringify({ ok: false, error: "Esta chave já está ativada em outra máquina." }),
        { status: 403, headers: { ...corsHeaders, "Content-Type": "application/json" } }
      );
    }

    // Ativa: vincula ao hardware
    const now = new Date().toISOString();
    const { error: updateError } = await supabase
      .from("licenses")
      .update({ hwid, activated_at: now })
      .eq("id", license.id);

    if (updateError) {
      return new Response(
        JSON.stringify({ ok: false, error: "Erro ao ativar. Tente novamente." }),
        { status: 500, headers: { ...corsHeaders, "Content-Type": "application/json" } }
      );
    }

    return new Response(
      JSON.stringify({ ok: true, activated_at: now }),
      { headers: { ...corsHeaders, "Content-Type": "application/json" } }
    );

  } catch (err) {
    return new Response(
      JSON.stringify({ ok: false, error: "Erro interno." }),
      { status: 500, headers: { ...corsHeaders, "Content-Type": "application/json" } }
    );
  }
});
