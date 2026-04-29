"""Historical similarity lookup using Qdrant and sentence-transformers."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import numpy as np
import yaml
from qdrant_client import QdrantClient
from sentence_transformers import SentenceTransformer


logger = logging.getLogger(__name__)


class HistoricalLookup:
    """Find similar past incidents in Qdrant."""

    def __init__(self) -> None:
        config_path = Path(__file__).resolve().parents[2] / "config" / "settings.yaml"
        with config_path.open("r", encoding="utf-8") as handle:
            config = yaml.safe_load(handle)
        self.model = SentenceTransformer("all-MiniLM-L6-v2")
        self.client = QdrantClient(host=config["qdrant"]["host"], port=config["qdrant"]["port"])

    def find_similar(self, log_text: str, top_k: int = 3) -> list[dict[str, Any]]:
        try:
            vector = self.model.encode(log_text, normalize_embeddings=True)
            results = self.client.search(
                collection_name="triage_reports",
                query_vector=vector.tolist() if isinstance(vector, np.ndarray) else list(vector),
                limit=top_k,
                with_payload=True,
            )
        except Exception as exc:
            logger.warning("Historical lookup failed: %s", exc)
            return []

        similar: list[dict[str, Any]] = []
        for point in results:
            payload = point.payload or {}
            similar.append(
                {
                    "incident_id": str(payload.get("incident_id", "")),
                    "severity": str(payload.get("severity", "")),
                    "title": str(payload.get("title", "")),
                }
            )
        return similar
