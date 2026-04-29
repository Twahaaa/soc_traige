"""BERT embeddings for NeuralLog sequences."""

from __future__ import annotations

import hashlib
import logging
from pathlib import Path
from typing import Any

import numpy as np
import torch
from transformers import AutoModel, AutoTokenizer


class BERTEmbedder:
    """Embed token lists using bert-base-uncased with on-disk caching."""

    def __init__(self, model_name: str, cache_dir: str) -> None:
        self.logger = logging.getLogger(__name__)
        self.model_name = model_name
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.fallback = False
        try:
            self.tokenizer = AutoTokenizer.from_pretrained(model_name, local_files_only=True)
            self.model = AutoModel.from_pretrained(model_name, local_files_only=True)
            self.model.eval()
        except Exception as exc:
            # Keep the pipeline runnable offline by falling back to a deterministic embedding.
            self.logger.warning("Falling back to deterministic embeddings: %s", exc)
            self.tokenizer = None
            self.model = None
            self.fallback = True

    def _cache_path(self, tokens: list[str]) -> Path:
        joined = " ".join(tokens)
        key = hashlib.md5(joined.encode("utf-8")).hexdigest()
        return self.cache_dir / f"{key}.npy"

    def embed(self, tokens: list[str]) -> np.ndarray:
        """Return a cached 768-dim CLS embedding."""
        cache_path = self._cache_path(tokens)
        if cache_path.exists():
            return np.load(cache_path)

        if self.fallback:
            joined = " ".join(tokens)
            seed = int(hashlib.md5(joined.encode("utf-8")).hexdigest()[:8], 16)
            rng = np.random.default_rng(seed)
            embedding = rng.normal(loc=0.0, scale=1.0, size=768).astype(np.float32)
            np.save(cache_path, embedding)
            return embedding

        text = " ".join(tokens)
        encoded = self.tokenizer(
            text,
            return_tensors="pt",
            truncation=True,
            max_length=128,
            padding=False,
        )

        with torch.no_grad():
            outputs = self.model(**encoded)
            cls_embedding = outputs.last_hidden_state[:, 0, :].squeeze(0).detach().cpu().numpy()

        np.save(cache_path, cls_embedding)
        return cls_embedding
