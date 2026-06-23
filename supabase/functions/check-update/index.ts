// Supabase Edge Function: check-update
// Deploy: supabase functions deploy check-update
//
// Recebe: { "version": "1.2.0" }
// Retorna: { "has_update": true, "version": "1.3.0", "message": "...", "url": "..." }
//      ou: { "has_update": false }

import { serve } from "https://deno.land/std@0.168.0/http/server.ts";
import { createClient } from "https://esm.sh/@supabase/supabase-js@2";

const corsHeaders = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Headers": "authorization, x-client-info, apikey, content-type",
};

function parseVersion(v: string): number[] {
  return v.replace(/^v/, "").split(".").map((x) => parseInt(x, 10) || 0);
}

function isNewer(remote: string, local: string): boolean {
  const r = parseVersion(remote);
  const l = parseVersion(local);
  for (let i = 0; i < 3; i++) {
    if ((r[i] ?? 0) > (l[i] ?? 0)) return true;
    if ((r[i] ?? 0) < (l[i] ?? 0)) return false;
  }
  return false;
}

serve(async (req) => {
  if (req.method === "OPTIONS") {
    return new Response("ok", { headers: corsHeaders });
  }

  try {
    const { version } = await req.json();

    // Limita tamanho da string de versão (endpoint público).
    const safeVersion = (typeof version === "string" && version.length <= 32) ? version : "0.0.0";

    const supabase = createClient(
      Deno.env.get("SUPABASE_URL") ?? "",
      Deno.env.get("SUPABASE_SERVICE_ROLE_KEY") ?? ""
    );

    // Pega a atualização mais recente
    const { data, error } = await supabase
      .from("app_updates")
      .select("*")
      .order("created_at", { ascending: false })
      .limit(1)
      .single();

    if (error || !data) {
      return new Response(
        JSON.stringify({ has_update: false }),
        { headers: { ...corsHeaders, "Content-Type": "application/json" } }
      );
    }

    if (!isNewer(data.version, safeVersion)) {
      return new Response(
        JSON.stringify({ has_update: false }),
        { headers: { ...corsHeaders, "Content-Type": "application/json" } }
      );
    }

    // Detecta idioma pelo Accept-Language ou retorna PT por padrão
    const acceptLang = req.headers.get("accept-language") ?? "pt";
    let message = data.message_pt || data.message_en || "";
    if (acceptLang.startsWith("en")) message = data.message_en || data.message_pt || "";
    if (acceptLang.startsWith("es")) message = data.message_es || data.message_pt || "";

    return new Response(
      JSON.stringify({
        has_update: true,
        version: data.version,
        message,
        url: data.url || "",
      }),
      { headers: { ...corsHeaders, "Content-Type": "application/json" } }
    );

  } catch (err) {
    return new Response(
      JSON.stringify({ has_update: false }),
      { status: 500, headers: { ...corsHeaders, "Content-Type": "application/json" } }
    );
  }
});
