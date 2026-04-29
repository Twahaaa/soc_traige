"""NeuralLog inference wrapper."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import torch
import yaml

from detection.neurallog.embeddings import BERTEmbedder
from detection.neurallog.model import NeuralLog


class NeuralLogInference:
    """Load a trained NeuralLog checkpoint and score token sequences."""

    def __init__(self, model_path: str) -> None:
        self.model_path = Path(model_path)
        if not self.model_path.exists():
            raise FileNotFoundError(
                f"NeuralLog checkpoint not found at {self.model_path}. Run the training script first."
            )

        config_path = Path(__file__).resolve().parents[2] / "config" / "settings.yaml"
        with config_path.open("r", encoding="utf-8") as handle:
            self.config = yaml.safe_load(handle)

        self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        self.embedder = BERTEmbedder(
            model_name=self.config["neurallog"]["bert_model"],
            cache_dir=self.config["neurallog"]["embedding_cache_dir"],
        )
        self.model = NeuralLog(
            input_dim=768,
            nhead=int(self.config["neurallog"]["nhead"]),
            num_layers=int(self.config["neurallog"]["num_layers"]),
            dim_feedforward=int(self.config["neurallog"]["dim_feedforward"]),
            dropout=float(self.config["neurallog"]["dropout"]),
        ).to(self.device)
        checkpoint = torch.load(self.model_path, map_location=self.device)
        self.model.load_state_dict(checkpoint["model_state_dict"])
        self.model.eval()

    def predict(self, sequence: list[list[str]]) -> dict[str, Any]:
        """Score a tokenized sequence and return a label plus anomaly score."""
        embeddings = [self.embedder.embed(tokens) for tokens in sequence]
        padded = torch.zeros((1, len(embeddings), 768), dtype=torch.float32, device=self.device)
        for index, embedding in enumerate(embeddings):
            padded[0, index] = torch.tensor(embedding, dtype=torch.float32, device=self.device)
        padding_mask = torch.zeros((1, len(embeddings)), dtype=torch.bool, device=self.device)

        with torch.no_grad():
            logits = self.model(padded, padding_mask)
            score = torch.sigmoid(logits).item()

        threshold = float(self.config["neurallog"]["anomaly_threshold"])
        return {
            "label": "anomalous" if score >= threshold else "normal",
            "score": float(score),
        }
