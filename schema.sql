-- DoughAI Phase 2 schema. Run once in the Supabase SQL editor (or `psql
-- "$DATABASE_URL" -f schema.sql`) against the project used for DATABASE_URL.

create table if not exists recommendations (
    id bigserial primary key,
    ticker text not null,
    verdict text not null,
    confidence double precision,
    time_horizon text,
    reasoning text,
    generated_at timestamptz not null,
    raw jsonb not null
);

create index if not exists idx_recommendations_ticker_generated_at
    on recommendations (ticker, generated_at desc);
