-- =====================================================================
-- PolyQuest — Tabelas no Supabase
-- Execute este SQL no SQL Editor do seu projeto Supabase
-- =====================================================================

-- Tabela de licenças
CREATE TABLE IF NOT EXISTS licenses (
    id          BIGSERIAL PRIMARY KEY,
    key         TEXT UNIQUE NOT NULL,
    email       TEXT NOT NULL,
    hwid        TEXT,                       -- hardware ID da máquina ativada (NULL = não ativada)
    max_devices INTEGER DEFAULT 1,
    activated_at TIMESTAMPTZ,
    created_at  TIMESTAMPTZ DEFAULT NOW()
);

-- Índice para busca rápida por chave
CREATE INDEX IF NOT EXISTS idx_licenses_key ON licenses(key);

-- Tabela de atualizações
CREATE TABLE IF NOT EXISTS app_updates (
    id          BIGSERIAL PRIMARY KEY,
    version     TEXT NOT NULL,              -- ex: "1.3.0"
    message_pt  TEXT DEFAULT '',
    message_en  TEXT DEFAULT '',
    message_es  TEXT DEFAULT '',
    url         TEXT DEFAULT '',            -- link para download
    created_at  TIMESTAMPTZ DEFAULT NOW()
);

-- Tabela de cupons de desconto (influenciadores)
CREATE TABLE IF NOT EXISTS coupons (
    id              BIGSERIAL PRIMARY KEY,
    code            TEXT UNIQUE NOT NULL,          -- ex: "GAMER10", "NAKA20"
    discount_type   TEXT NOT NULL DEFAULT 'percent', -- 'percent' ou 'fixed'
    discount_value  NUMERIC(10,2) NOT NULL,        -- 10 = 10% ou R$10.00
    max_uses        INTEGER DEFAULT NULL,          -- NULL = ilimitado
    current_uses    INTEGER DEFAULT 0,
    influencer      TEXT DEFAULT '',               -- nome do influenciador
    active          BOOLEAN DEFAULT TRUE,
    expires_at      TIMESTAMPTZ DEFAULT NULL,      -- NULL = sem expiração
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_coupons_code ON coupons(code);

-- Colunas para rastrear cupom e faturamento
ALTER TABLE licenses ADD COLUMN IF NOT EXISTS coupon_code TEXT DEFAULT NULL;
ALTER TABLE licenses ADD COLUMN IF NOT EXISTS amount_paid NUMERIC(10,2) DEFAULT NULL;
ALTER TABLE licenses ADD COLUMN IF NOT EXISTS payment_id TEXT DEFAULT NULL;
CREATE UNIQUE INDEX IF NOT EXISTS idx_licenses_payment_id ON licenses(payment_id) WHERE payment_id IS NOT NULL;

-- Função para incrementar uso de cupom atomicamente
CREATE OR REPLACE FUNCTION increment_coupon_usage(coupon_code TEXT)
RETURNS VOID AS $$
BEGIN
  UPDATE coupons
  SET current_uses = current_uses + 1
  WHERE code = coupon_code;
END;
$$ LANGUAGE plpgsql;

-- =====================================================================
-- Para inserir uma licença manualmente:
-- INSERT INTO licenses (key, email) VALUES ('PQ-ABCD-1234-EFGH', 'email@comprador.com');
--
-- Para publicar uma atualização:
-- INSERT INTO app_updates (version, message_pt, message_en, message_es, url)
-- VALUES ('1.3.0', 'Novidades da v1.3...', 'v1.3 news...', 'Novedades v1.3...', 'https://...');
--
-- Para criar um cupom de desconto:
-- INSERT INTO coupons (code, discount_type, discount_value, max_uses, influencer)
-- VALUES ('GAMER10', 'percent', 10, 100, 'GamerXYZ');
-- =====================================================================
