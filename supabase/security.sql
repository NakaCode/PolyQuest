-- =====================================================================
-- PolyQuest — Endurecimento de segurança (rode no SQL Editor do Supabase)
-- =====================================================================
--
-- CONTEXTO: a anon key do Supabase é pública por design (vai no index.html).
-- O que impede alguém de ler/alterar suas tabelas com essa chave NÃO é
-- esconder a chave — é o Row Level Security (RLS). Todo acesso legítimo às
-- tabelas passa pelas Edge Functions, que usam SUPABASE_SERVICE_ROLE_KEY e
-- IGNORAM o RLS. Portanto, basta ativar RLS sem criar policy para anon:
-- o padrão vira "negar tudo" para o público, e as functions continuam
-- funcionando normalmente.
--
-- Verifique antes: se o index.html ou o app fizerem QUALQUER consulta direta
-- a estas tabelas com a anon key (em vez de chamar uma Edge Function), essa
-- consulta vai parar de funcionar. Hoje todo acesso é via Edge Function, então
-- é seguro. Teste o fluxo de compra + ativação após rodar.

ALTER TABLE licenses    ENABLE ROW LEVEL SECURITY;
ALTER TABLE coupons     ENABLE ROW LEVEL SECURITY;
ALTER TABLE app_updates ENABLE ROW LEVEL SECURITY;

-- Sem nenhuma POLICY criada, anon e authenticated não conseguem
-- SELECT/INSERT/UPDATE/DELETE. O service_role (Edge Functions) ignora o RLS.

-- Para conferir o estado do RLS depois:
--   SELECT relname, relrowsecurity FROM pg_class
--   WHERE relname IN ('licenses','coupons','app_updates');
-- relrowsecurity deve ser 't' (true) para as três.


-- =====================================================================
-- OPCIONAL — Multi-device (só se você quiser vender licença p/ N máquinas)
-- =====================================================================
-- Hoje a tabela licenses tem UMA coluna hwid: uma licença = uma máquina.
-- A coluna max_devices existe mas é inócua (não há onde guardar vários HWIDs).
-- Para suportar de verdade, separe as ativações numa tabela própria:
--
-- CREATE TABLE IF NOT EXISTS activations (
--     id           BIGSERIAL PRIMARY KEY,
--     license_key  TEXT NOT NULL REFERENCES licenses(key) ON DELETE CASCADE,
--     hwid         TEXT NOT NULL,
--     activated_at TIMESTAMPTZ DEFAULT NOW(),
--     UNIQUE (license_key, hwid)
-- );
-- ALTER TABLE activations ENABLE ROW LEVEL SECURITY;
--
-- E em activate/index.ts, antes de ativar:
--   1) SELECT count(*) FROM activations WHERE license_key = key;
--   2) se já existe linha com este (key, hwid) -> ok (idempotente)
--   3) se count >= licenses.max_devices -> erro "limite de dispositivos atingido"
--   4) senão INSERT em activations
