# SOC Triage Pipeline Stages

This file tracks stage-by-stage progress and required checkpoints.

## Stage 1: Log Ingestion + Pre-filtering

- [X] Implement synthetic log generator
- [X] Implement rule-based prefilter (keywords, privilege escalation, brute force)
- [X] Implement producer to publish to `stream:raw_logs`
- [X] Implement Redis client + consumer group setup
- [X] Verify Redis stream receives messages
- [X] Verify keyword rule fires (`keyword_match:CRITICAL`)
- [X] Verify brute-force rule fires (`brute_force:<ip>`)

## Stage 2: Preprocessing + Sequence Construction

- [X] Implement tokenizer (parsing-free)
- [X] Implement sliding window sequence builder
- [X] Route sequences to `stream:queue_a` or `stream:queue_b`
- [X] Implement HDFS loader (block ID grouping)
- [X] Implement BGL loader (chronological windows)
- [X] Add AIT loader stub (NotImplementedError)
- [X] Add dataset download script
- [X] Verify `sequence_builder` runs and routes correctly
- [X] Verify messages appear in `stream:queue_a` and `stream:queue_b`

## Stage 3: Anomaly Detection (NeuralLog + Queue Workers)

- [X] Implement NeuralLog model
- [X] Implement BERT embeddings with cache
- [X] Implement training script (synthetic + HDFS + BGL)
- [X] Implement inference wrapper
- [X] Implement queue A worker (escalation + results stream)
- [X] Implement queue B worker (triage trigger)
- [X] Add DeepLog stubs
- [X] Verify training + inference output
- [X] Verify `stream:queue_b_escalated` receives anomalies

## Stage 4: LLM Triage + Qdrant Storage

- [ ] Implement triage report schema
- [ ] Add MITRE techniques JSON
- [ ] Implement tools: CVE, IP reputation, historical lookup, MITRE mapper
- [ ] Implement triage prompt builder
- [ ] Implement triage agent (Groq + Ollama paths)
- [ ] Store reports in Qdrant + publish to `stream:triage_reports`
- [ ] Verify Groq path
- [ ] Verify Ollama fallback path
- [ ] Verify Qdrant upserts + similarity search

## Stage 5: Dashboard (Out of Scope for This Build)

- [ ] FastAPI backend for alerts + WebSocket feed
- [ ] Next.js dashboard views
- [ ] Qdrant + Redis integration for UI

## Final Deliverables (After Stages 1-4 Confirmed)

- [ ] `scripts/setup.sh` health checks + consumer groups + Qdrant collection
- [ ] `scripts/run_pipeline.sh` orchestration
- [ ] `README.md` usage + training + pipeline verification
