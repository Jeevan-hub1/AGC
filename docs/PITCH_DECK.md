# 🔥 PROJECT PHOENIX — Pitch Deck

**ET AI Hackathon 2026 · Problem #2 — AI-Driven Energy Supply Chain Resilience**

> 14 slides · ~6-minute pitch + live demo. Speaker notes under each slide.
> Judging weights: Innovation 25 · Business Impact 25 · Technical Excellence 20 · Scalability 15 · UX 15.

---

## Slide 1 — Title

**PROJECT PHOENIX**
*National Energy Resilience Operating System (GEOS)*
An AI-native autonomous decision platform for India's energy supply chain.

> 🎤 "India imports 88% of its crude. 42% of it crosses one strait. Today, if that strait closes, the response is manual phone calls. We built the intelligence layer that makes it autonomous."

---

## Slide 2 — The Problem (Business Impact)

- India imports **~88%** of crude; **40–45%** transits the **Strait of Hormuz**.
- Strategic Petroleum Reserve = **~9.5 days** of cover.
- 2025 US–Iran standoff: **Brent +8% in one session**; refiners forced onto spot at steep premiums.
- McKinsey: economies *without* integrated response intelligence took **47 days longer** to stabilise.

> 🎤 "The data exists — prices, vessels, sanctions. What's missing is an intelligence layer that fuses it and *acts* before a crisis becomes a national emergency. That's the gap."

---

## Slide 3 — The Insight

Traditional tools are **dashboards** — they show you the problem.
PHOENIX is an **operating system** — it predicts, simulates, decides, and acts.

> 🎤 "No single sensor flags a compound crisis. Our agents, reasoning together, do."

---

## Slide 4 — What PHOENIX Is

A **digital brain** that, on any geopolitical shock:
1. **Predicts** disruption probability + lead time (trained foundation model)
2. **Simulates** thousands of futures (Monte Carlo war-gaming)
3. **Decides** the optimal procurement + reserve response (game theory + DP)
4. **Scores** national resilience live (NERI 0–100)
5. **Acts** — generates an executable, explainable national response

> 🎤 "Nine specialised AI agents, one coordinated national response — in under 100 milliseconds."

---

## Slide 5 — Architecture

*(insert `docs/architecture.svg`)*

Command Center → API → **9-agent supervisor swarm** → Core Engines (Knowledge Graph · Causal SCM · Monte Carlo · NERI) + Advanced ML (Foundation Model · GNN · Nash · DP) → Data Layer (live feed + supply model).

> 🎤 "A blackboard multi-agent pattern — agents enrich shared state in dependency order. No loops, fully auditable, maps straight onto LangGraph for production."

---

## Slide 6 — ⚡ LIVE DEMO (the centrepiece)

**Click ▶ RUN DEMO.** Narrate as it auto-plays:
1. Baseline — NERI ~64, live Brent ticker
2. Inject **Hormuz closure** → Foundation Model: 97% disruption, 2-day lead
3. 9 agents respond live → NERI drops to WATCH
4. GNN systemic-risk map → Nash procurement plan → DP reserve schedule
5. Economic transmission → **Benchmark** → Black Swan finale

> 🎤 "Watch the whole national response assemble itself in real time. This isn't a mockup — every number is computed live."

---

## Slide 7 — Innovation 1: Predictive Foundation Model + GNN

- Trained gradient-boosted model → **P(corridor disruption) + lead time** (AUC ≈ 0.74).
- 3-layer **attention GNN** propagates systemic risk across the supply graph.

> 🎤 "We don't wait for the price to move. We read the precursors — tension, naval build-up, incidents — days earlier."

---

## Slide 8 — Innovation 2: Autonomous Decision Engines

- **Cournot–Nash equilibrium** → spot price is *endogenous* to scarcity, not a fixed table.
- **Dynamic-programming MDP** → provably optimal SPR drawdown schedule.
- **Causal SCM with do-calculus** → explainable "what-ifs", not black-box correlations.

> 🎤 "Procurement and reserves aren't heuristics here — they're game theory and optimal control."

---

## Slide 9 — The Metric That Matters (Technical Excellence)

**Detection benchmark — PHOENIX vs single-sensor baseline:**

| | False-Negative Rate | Recall | Lead Time |
|---|---|---|---|
| Single-sensor baseline | ~40% | 0.59 | 1.2 days |
| **PHOENIX** | **~2%** | **0.98** | **4.7 days** |

→ **~95% FNR reduction · +3.5 days of warning.**

> 🎤 "The brief asks for false-negative-rate reduction — 'the metric that actually saves lives'. We measured it: 95% fewer missed disruptions, three and a half extra days to act."

---

## Slide 10 — Live Data, Honest Provenance

- Real **Brent / WTI / NatGas / USD-INR** ingested live; scenarios project from **today's price**.
- Disk-cache + graceful fallback → every value tagged **LIVE / CACHE / FALLBACK**.

> 🎤 "It ingests live market signals — and it never lies about where a number came from. The demo can't break on a flaky network."

---

## Slide 11 — National Energy Resilience Index (NERI)

A single **0–100** early-warning score from 8 weighted sub-indicators
(import dependency, route vulnerability, reserves, supplier diversity, price, tension, logistics, demand).
Bands: **CRITICAL · WATCH · STABLE · RESILIENT**.

> 🎤 "One number a policymaker can act on. Calm at 64, collapses to 30 under a multi-theatre war."

---

## Slide 12 — Scalability & Roadmap

- **Today:** self-contained, boots in seconds, 52 passing tests.
- **Production:** Neo4j + PyTorch-Geometric GNN, live AIS/GDELT/EIA feeds, LLM-backed Copilot & Policy agents (interfaces already in place), Kafka streaming, multi-commodity (LNG, coal).

> 🎤 "Every engine has a clean interface to its production-grade backend. The architecture doesn't change — only the scale."

---

## Slide 13 — Why We Win

- **Innovation:** foundation model + GNN + game theory + optimal control in one system.
- **Business Impact:** directly addresses a structural national-security vulnerability.
- **Technical Excellence:** real algorithms, measured 95% FNR reduction, 52 tests.
- **UX:** mission-control command center, one-click demo.
- **Scalability:** explicit production roadmap.

> 🎤 "We took the problem statement's exact evaluation metrics and built to them."

---

## Slide 14 — Close

**PROJECT PHOENIX** — *from a nation that reacts to disruptions to one that anticipates, adapts, and self-heals.*

Repo: `github.com/Jeevan-hub1/AGC` · Working prototype · Architecture · Demo

> 🎤 "Data present, but unacted upon — that's what killed response times. PHOENIX is the layer that finally acts. Thank you."

---

### 📋 Deliverables checklist
- [x] Working prototype (run `uvicorn geos.api.server:app`)
- [x] Architecture diagram (`docs/architecture.svg`)
- [x] Presentation deck (this outline → slides)
- [ ] Demo video (record the ▶ RUN DEMO walkthrough, ~90s)

### 🎬 Demo video shot list (90s)
1. 0–10s: Title + live ticker + baseline NERI
2. 10–35s: Inject Hormuz → agent feed lights up → NERI drops
3. 35–55s: Procurement plan (Nash price) + DP reserve schedule
4. 55–75s: Benchmark page — 95% FNR reduction, lead-time bars
5. 75–90s: Black Swan finale → NERI CRITICAL → close on tagline
