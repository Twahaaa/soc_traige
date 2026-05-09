"""Historical similarity lookup using Qdrant and sentence-transformers."""

from __future__ import annotations

import hashlib
import logging
from pathlib import Path
from typing import Any

import numpy as np
import yaml
from qdrant_client import QdrantClient
from qdrant_client.http import models as qdrant_models
from sentence_transformers import SentenceTransformer


logger = logging.getLogger(__name__)


class HistoricalLookup:
    """Find similar past incidents in Qdrant."""

    def __init__(self) -> None:
        config_path = Path(__file__).resolve().parents[2] / "config" / "settings.yaml"
        with config_path.open("r", encoding="utf-8") as handle:
            config = yaml.safe_load(handle)
        self.dimension = 384
        self.fallback = False
        try:
            self.model = SentenceTransformer("all-MiniLM-L6-v2")
        except Exception as exc:
            logger.warning("HistoricalLookup using deterministic embeddings: %s", exc)
            self.model = None
            self.fallback = True
        self.client = QdrantClient(
            host=config["qdrant"]["host"],
            port=config["qdrant"]["port"],
            check_compatibility=False,
        )

    def _embed(self, text: str) -> list[float]:
        if self.fallback or self.model is None:
            seed = int(hashlib.md5(text.encode("utf-8")).hexdigest()[:8], 16)
            rng = np.random.default_rng(seed)
            return rng.normal(size=self.dimension).astype(np.float32).tolist()

        vector = self.model.encode(text, normalize_embeddings=True)
        return vector.tolist() if isinstance(vector, np.ndarray) else list(vector)

    def find_similar(self, log_text: str, top_k: int = 3) -> list[dict[str, Any]]:
        try:
            vector = self._embed(log_text)
            results = self.client.query_points(
                collection_name="triage_reports",
                query=vector,
                limit=top_k,
                with_payload=True,
            )
        except Exception as exc:
            logger.warning("Historical lookup failed: %s", exc)
            return []

        similar: list[dict[str, Any]] = []
        points = getattr(results, "points", None) or getattr(results, "result", None) or results
        for point in points:
            payload = getattr(point, "payload", None) or {}
            similar.append(
                {
                    "incident_id": str(payload.get("incident_id", "")),
                    "severity": str(payload.get("severity", "")),
                    "title": str(payload.get("title", "")),
                }
            )
        return similar

    def store_report(self, report: dict[str, Any], embedding: list[float]) -> None:
        """Upsert a triage report embedding and payload into Qdrant."""
        from qdrant_client.http import models as qdrant_models

        self.client.upsert(
            collection_name=self._collection_name(),
            points=[
                qdrant_models.PointStruct(
                    id=str(report["incident_id"]),
                    vector=embedding,
                    payload=report,
                )
            ],
        )

    @staticmethod
    def _collection_name() -> str:
        return "triage_reports"
