-- =====================================================================
-- PolyQuest — Rate limiting do painel admin
-- Rode no SQL Editor do Supabase (ou via `supabase db query`).
-- =====================================================================
--
-- Registra APENAS tentativas de senha INCORRETA, por IP. A função
-- admin-panel conta as falhas recentes e bloqueia o IP após o limite.
-- Logins corretos não geram linha (e limpam as falhas do IP).

CREATE TABLE IF NOT EXISTS admin_login_attempts (
    id          BIGSERIAL PRIMARY KEY,
    ip          TEXT NOT NULL,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_admin_attempts_ip_time
    ON admin_login_attempts(ip, created_at DESC);

-- RLS ligado, sem policy → só o service_role (Edge Function) acessa.
ALTER TABLE admin_login_attempts ENABLE ROW LEVEL SECURITY;
