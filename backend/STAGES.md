# SOC Triage Pipeline Stages

This file tracks stage-by-stage progress and required checkpoints.

## Stage 1: Log Ingestion + Pre-filtering
- [x] Implement synthetic log generator
- [x] Implement rule-based prefilter (keywords, privilege escalation, brute force)
- [x] Implement producer to publish to `stream:raw_logs`
- [x] Implement Redis client + consumer group setup
- [x] Verify Redis stream receives messages
- [x] Verify keyword rule fires (`keyword_match:CRITICAL`)
- [x] Verify brute-force rule fires (`brute_force:<ip>`)

## Stage 2: Preprocessing + Sequence Construction
- [x] Implement tokenizer (parsing-free)
- [x] Implement sliding window sequence builder
- [x] Route sequences to `stream:queue_a` or `stream:queue_b`
- [x] Implement HDFS loader (block ID grouping)
- [x] Implement BGL loader (chronological windows)
- [x] Add AIT loader stub (NotImplementedError)
- [x] Add dataset download script
- [x] Verify `sequence_builder` runs and routes correctly
- [x] Verify messages appear in `stream:queue_a` and `stream:queue_b`

## Stage 3: Anomaly Detection (NeuralLog + Queue Workers)
- [ ] Implement NeuralLog model
- [ ] Implement BERT embeddings with cache
- [ ] Implement training script (synthetic + HDFS + BGL)
- [ ] Implement inference wrapper
- [ ] Implement queue A worker (escalation + results stream)
- [ ] Implement queue B worker (triage trigger)
- [ ] Add DeepLog stubs
- [ ] Verify training + inference output
- [ ] Verify `stream:queue_b_escalated` receives anomalies

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
