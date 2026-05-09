"""Stage-4 triage agent with deterministic and Groq-ready execution paths."""

from __future__ import annotations

import json
import hashlib
import logging
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

import numpy as np
import yaml
from langchain_core.messages import HumanMessage
from qdrant_client import QdrantClient
from qdrant_client.http import models as qdrant_models
from sentence_transformers import SentenceTransformer

from queue.redis_manager import get_redis_client
from triage.prompts.triage_prompt import build_prompt
from triage.report_schema import IPReputation, MITREAttack, TriageReport
from triage.tools.cve_lookup import CVELookup
from triage.tools.historical_lookup import HistoricalLookup
from triage.tools.ip_reputation import IPReputationChecker
from triage.tools.mitre_mapper import MITREMapper


logger = logging.getLogger(__name__)


class TriageAgent:
    """Generate, store, and publish structured triage reports."""

    def __init__(self) -> None:
        config_path = Path(__file__).resolve().parents[1] / "config" / "settings.yaml"
        with config_path.open("r", encoding="utf-8") as handle:
            self.config = yaml.safe_load(handle)

        self.mitre_mapper = MITREMapper()
        self.cve_lookup = CVELookup()
        self.ip_checker = IPReputationChecker()
        self.historical_lookup = HistoricalLookup()
        try:
            self.report_embedder = SentenceTransformer(
                self.config["embedding"]["report_model"],
                local_files_only=True,
            )
        except Exception as exc:
            logger.warning("Report embedding model unavailable, using deterministic fallback: %s", exc)
            self.report_embedder = None
        self.qdrant = QdrantClient(
            host=self.config["qdrant"]["host"],
            port=self.config["qdrant"]["port"],
            check_compatibility=False,
        )
        self.qdrant_available = True
        self.redis_client = get_redis_client()
        self._ensure_collection()

        self.llm = self._build_llm()

    def _build_llm(self):
        provider = self.config["llm"]["provider"]
        try:
            if provider == "groq":
                from langchain_groq import ChatGroq

                api_key = self._env_or_config("GROQ_API_KEY")
                if api_key:
                    return ChatGroq(model=self.config["llm"]["groq_model"], api_key=api_key)
                raise RuntimeError("GROQ_API_KEY is not set")

            from langchain_ollama import ChatOllama

            return ChatOllama(model=self.config["llm"]["ollama_model"], base_url=self.config["llm"]["ollama_base_url"])
        except Exception as exc:
            logger.warning("LLM backend unavailable, using deterministic fallback: %s", exc)
            return None

    def _env_or_config(self, name: str) -> str | None:
        value = os.getenv(name, "").strip()
        return value or None

    def _ensure_collection(self) -> None:
        collection_name = self.config["qdrant"]["collection"]
        try:
            if not self.qdrant.collection_exists(collection_name):
                self.qdrant.create_collection(
                    collection_name=collection_name,
                    vectors_config=qdrant_models.VectorParams(
                        size=int(self.config["embedding"]["report_dim"]),
                        distance=qdrant_models.Distance.COSINE,
                    ),
                )
        except Exception as exc:
            self.qdrant_available = False
            logger.warning("Qdrant unavailable, triage storage will be skipped: %s", exc)

    def run(self, sequence_message: dict[str, Any]) -> TriageReport:
        raw_lines = [str(line) for line in sequence_message.get("raw_lines", [])]
        anomaly_score = float(sequence_message.get("anomaly_score", 0.0))
        detection_source = str(sequence_message.get("detection_source", "unknown"))
        log_text = " ".join(raw_lines)

        mitre_result = self.mitre_mapper.map(raw_lines)
        public_ip = self.ip_checker.extract_public_ip(raw_lines)
        ip_result = self.ip_checker.check(public_ip) if public_ip else None
        keyword = self.cve_lookup.extract_keyword(raw_lines)
        cve_results = self.cve_lookup.lookup(keyword) if keyword else []
        similar_incidents = self.historical_lookup.find_similar(log_text)

        if self.config["llm"]["provider"] == "groq":
            report = self._run_groq_react(raw_lines, anomaly_score, detection_source, mitre_result, ip_result, cve_results, similar_incidents)
        else:
            report = self._run_ollama_deterministic(raw_lines, anomaly_score, detection_source, mitre_result, ip_result, cve_results, similar_incidents)

        report.affected_host = self._extract_host(raw_lines)
        report.log_source = str(sequence_message.get("source", "synthetic"))
        report.anomaly_score = anomaly_score
        report.detection_source = detection_source
        report.evidence = raw_lines
        report.mitre_attack = mitre_result
        report.ip_reputation = ip_result if isinstance(ip_result, IPReputation) else None
        report.cve_references = [item.get("cve_id", "") for item in cve_results if item.get("cve_id")]
        report.similar_past_incidents = [item.get("incident_id", "") for item in similar_incidents if item.get("incident_id")]

        self._store_report(report)
        logger.info("Created triage report %s", report.incident_id)
        return report

    def _run_groq_react(
        self,
        raw_lines: list[str],
        anomaly_score: float,
        detection_source: str,
        mitre_result: MITREAttack | None,
        ip_result: IPReputation | None,
        cve_results: list[dict[str, Any]],
        similar_incidents: list[dict[str, Any]],
    ) -> TriageReport:
        prompt = build_prompt(raw_lines, anomaly_score, detection_source, mitre_result, ip_result, cve_results, similar_incidents)
        if self.llm is None:
            return self._fallback_report(raw_lines, anomaly_score, detection_source)
        try:
            response = self.llm.invoke([HumanMessage(content=prompt)])
            content = getattr(response, "content", "")
            if isinstance(content, str):
                report_json = self._extract_json(content)
                return self._report_from_payload(report_json, raw_lines, anomaly_score, detection_source)
            return self._fallback_report(raw_lines, anomaly_score, detection_source)
        except Exception as exc:
            logger.warning("Groq path failed, falling back: %s", exc)
            return self._fallback_report(raw_lines, anomaly_score, detection_source)

    def _run_ollama_deterministic(
        self,
        raw_lines: list[str],
        anomaly_score: float,
        detection_source: str,
        mitre_result: MITREAttack | None,
        ip_result: IPReputation | None,
        cve_results: list[dict[str, Any]],
        similar_incidents: list[dict[str, Any]],
    ) -> TriageReport:
        prompt = build_prompt(raw_lines, anomaly_score, detection_source, mitre_result, ip_result, cve_results, similar_incidents)
        if self.llm is None:
            return self._fallback_report(raw_lines, anomaly_score, detection_source)
        try:
            response = self.llm.invoke([HumanMessage(content=prompt)])
            content = getattr(response, "content", response)
            if isinstance(content, str):
                report_json = self._extract_json(content)
                return self._report_from_payload(report_json, raw_lines, anomaly_score, detection_source)
            return self._fallback_report(raw_lines, anomaly_score, detection_source)
        except Exception as exc:
            logger.warning("Ollama path failed, falling back: %s", exc)
            return self._fallback_report(raw_lines, anomaly_score, detection_source)

    def _report_from_payload(
        self,
        payload: dict[str, Any],
        raw_lines: list[str],
        anomaly_score: float,
        detection_source: str,
    ) -> TriageReport:
        base = self._fallback_report_payload(raw_lines, anomaly_score, detection_source)
        base.update({key: value for key, value in payload.items() if value is not None})
        base["log_source"] = str(base.get("log_source") or "synthetic")
        base["affected_host"] = str(base.get("affected_host") or self._extract_host(raw_lines))
        base["severity"] = self._normalize_severity(base.get("severity"))
        base["ip_reputation"] = self._normalize_optional_model(base.get("ip_reputation"), IPReputation)
        base["mitre_attack"] = self._normalize_optional_model(base.get("mitre_attack"), MITREAttack)
        base["evidence"] = [str(item) for item in base.get("evidence", raw_lines) or raw_lines]
        base["cve_references"] = [str(item) for item in base.get("cve_references", []) or []]
        base["remediation_steps"] = [str(item) for item in base.get("remediation_steps", []) or []]
        base["similar_past_incidents"] = [str(item) for item in base.get("similar_past_incidents", []) or []]
        return TriageReport.model_validate(base)

    def _extract_json(self, content: str) -> dict[str, Any]:
        text = content.strip()
        if text.startswith("```"):
            text = text.strip("`\n")
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            match = re.search(r"\{.*\}", text, re.DOTALL)
            if match:
                return json.loads(match.group(0))
            raise

    def _store_report(self, report: TriageReport) -> None:
        embedding = self._report_embedding(report)
        if self.qdrant_available:
            try:
                self.qdrant.upsert(
                    collection_name=self.config["qdrant"]["collection"],
                    points=[
                        qdrant_models.PointStruct(
                            id=report.incident_id,
                            vector=embedding,
                            payload=report.model_dump(),
                        )
                    ],
                )
            except Exception as exc:
                self.qdrant_available = False
                logger.warning("Qdrant upsert failed, disabling storage: %s", exc)
        try:
            self.redis_client.xadd("stream:triage_reports", {"report": report.model_dump_json()})
        except Exception as exc:
            logger.warning("Redis publish failed, skipping stream write: %s", exc)

    def publish_report(self, report: TriageReport) -> None:
        """Expose a simple explicit publish hook for future integration."""
        self._store_report(report)

    def _report_embedding(self, report: TriageReport) -> list[float]:
        text = f"{report.title} {report.description} {' '.join(report.remediation_steps)}"
        if self.report_embedder is None:
            seed = int(hashlib.md5(text.encode("utf-8")).hexdigest()[:8], 16)
            rng = np.random.default_rng(seed)
            return rng.normal(size=int(self.config["embedding"]["report_dim"])).astype(np.float32).tolist()
        vector = self.report_embedder.encode(text, normalize_embeddings=True)
        return vector.tolist()

    def _fallback_report(self, raw_lines: list[str], anomaly_score: float, detection_source: str) -> TriageReport:
        return TriageReport(**self._fallback_report_payload(raw_lines, anomaly_score, detection_source))

    @staticmethod
    def _normalize_severity(value: Any) -> str:
        allowed = {"Critical", "High", "Medium", "Low", "Informational"}
        if isinstance(value, str) and value in allowed:
            return value
        if isinstance(value, dict):
            candidate = value.get("rule") or value.get("severity")
            if isinstance(candidate, str) and candidate in allowed:
                return candidate
        return "Low"

    @staticmethod
    def _normalize_optional_model(value: Any, model_cls: Any) -> Any:
        if value in (None, "", "None", "null", "NULL"):
            return None
        if isinstance(value, model_cls):
            return value
        if isinstance(value, dict):
            return model_cls.model_validate(value)
        return None

    def _fallback_report_payload(self, raw_lines: list[str], anomaly_score: float, detection_source: str) -> dict[str, Any]:
        return {
            "incident_id": str(uuid4()),
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "severity": "Low",
            "title": "LLM triage failed",
            "affected_host": self._extract_host(raw_lines),
            "log_source": "unknown",
            "anomaly_score": anomaly_score,
            "description": "LLM triage failed -- manual review required",
            "evidence": raw_lines,
            "cve_references": [],
            "ip_reputation": None,
            "mitre_attack": None,
            "remediation_steps": ["Review the alert manually."],
            "similar_past_incidents": [],
            "detection_source": detection_source,
        }

    def _extract_host(self, raw_lines: list[str]) -> str:
        if not raw_lines:
            return "unknown"
        first_line = raw_lines[0]
        parts = first_line.split()
        if len(parts) >= 2:
            if re.match(r"^\d{4}-\d{2}-\d{2}$", parts[0]):
                return parts[1].rstrip(":")
            return parts[0].rstrip(":")
        return "unknown"
