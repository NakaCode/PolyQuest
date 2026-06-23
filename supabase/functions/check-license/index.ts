// Supabase Edge Function: check-license
// Deploy: supabase functions deploy check-license
//
// Recebe: { "key": "PQ-XXXX-XXXX-XXXX", "hwid": "abc123..." }
// Retorna: { "ok": true, "valid": true/false }

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

    // Entrada inválida/abusiva → trata como licença inválida (sem tocar no banco).
    if (typeof key !== "string" || key.length > 64 || (hwid != null && (typeof hwid !== "string" || hwid.length > 256))) {
      return new Response(
        JSON.stringify({ ok: true, valid: false }),
        { headers: { ...corsHeaders, "Content-Type": "application/json" } }
      );
    }

    const supabase = createClient(
      Deno.env.get("SUPABASE_URL") ?? "",
      Deno.env.get("SUPABASE_SERVICE_ROLE_KEY") ?? ""
    );

    const { data: license, error } = await supabase
      .from("licenses")
      .select("hwid")
      .eq("key", (key ?? "").trim().toUpperCase())
      .single();

    if (error || !license) {
      return new Response(
        JSON.stringify({ ok: true, valid: false }),
        { headers: { ...corsHeaders, "Content-Type": "application/json" } }
      );
    }

    const valid = license.hwid === hwid;

    return new Response(
      JSON.stringify({ ok: true, valid }),
      { headers: { ...corsHeaders, "Content-Type": "application/json" } }
    );

  } catch (err) {
    return new Response(
      JSON.stringify({ ok: false, error: "Erro interno." }),
      { status: 500, headers: { ...corsHeaders, "Content-Type": "application/json" } }
    );
  }
});
