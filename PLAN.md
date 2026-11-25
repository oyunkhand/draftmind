# DraftMind AI — Build Plan

Cloud9 x JetBrains "Sky's The Limit" Hackathon — Category 2 (LoL Macro Scouting & Draft Management)

## Architecture decisions
- **Backend**: Python FastAPI + stdlib `sqlite3` (no ORM, zero native deps). Code kept Python 3.9+ compatible.
- **Frontend**: React 18 + TypeScript + Vite + Tailwind v4, react-router.
- **Data**: `DataAdapter` interface → `SampleAdapter` (seeded synthetic dataset in `/data/seed`) and
  `GridAdapter` (GRID Central Data + Series State GraphQL, enabled by `GRID_API_KEY`). Adapters feed a
  normalized SQLite store; all analytics read from SQLite, so the engine is source-agnostic.
- **Champion metadata**: snapshot of Riot Data Dragon (`/data/champions.json`) + hand-curated pro role map;
  icons served from the Data Dragon CDN with initials fallback.
- **Explanations**: templated from score factors; optional LLM rewrite (Anthropic or OpenAI key) on demand.

## Milestones
1. **Data model + seed data** — champion snapshot, seed generator (8 teams, ~100 games, full 20-action
   drafts, fearless Bo3 series, objectives, gold@15), SQLite schema + loader, adapter interface.
2. **Scoring engine + tests** — draft-order/fearless state machine, stats aggregation, opponent
   prediction (softmax), our recommendation (weighted factors), coach-feedback factor, explanations.
   pytest suite.
3. **API** — teams, matches, scouting (+ Markdown export), series, draft sessions, actions, decisions,
   predictions/recommendations, weights settings, LLM explain.
4. **Draft Board UI** — full pro draft order, champion grid w/ search + role filter, prediction panel,
   recommendation panel (Accept / Modify / Reject, "Why?"), fearless toggle, game number, weights panel.
5. **Scouting Report UI** — champion-pool heatmap, pick/ban tables, first-pick priorities, side stats,
   early-game tendencies; PDF (print layout) + Markdown export. Dashboard + Series History.
6. **Polish + delivery** — README (Mermaid diagram, methodology, JetBrains section, screenshots),
   Docker compose, deploy docs (Vercel/Netlify + Render/Fly), LICENSE, .env.example.

Each milestone: run tests + app, fix errors before moving on.

## Status (2026-11-24)
- [x] M1 data model + seed (148 games, 8 teams, 56 fearless Bo3 series)
- [x] M2 scoring engine + 30 tests; opponent model backtested (picks top-5 52% vs 32% baseline) and calibrated
- [x] M3 API (FastAPI, Swagger at /docs)
- [x] M4 Draft Board · M5 Scouting / Dashboard / Series History / AI Model
- [x] M6 README, Docker (verified `docker compose up`), deploy configs, LICENSE
- [ ] Team: fill in "How JetBrains tools were used" in README; record the 3-minute demo
