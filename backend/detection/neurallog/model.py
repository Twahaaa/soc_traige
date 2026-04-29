"""NeuralLog model for parsing-free log anomaly detection."""

from __future__ import annotations

import torch
from torch import nn


class NeuralLog(nn.Module):
    """NeuralLog: BERT embeddings followed by a Transformer encoder."""

    def __init__(
        self,
        input_dim: int = 768,
        nhead: int = 2,
        num_layers: int = 2,
        dim_feedforward: int = 512,
        dropout: float = 0.1,
    ) -> None:
        super().__init__()
        encoder_layer = nn.TransformerEncoderLayer(
            d_model=input_dim,
            nhead=nhead,
            dim_feedforward=dim_feedforward,
            dropout=dropout,
            batch_first=True,
            activation="gelu",
        )
        self.encoder = nn.TransformerEncoder(encoder_layer, num_layers=num_layers)
        self.classifier = nn.Linear(input_dim, 1)

    def forward(
        self,
        inputs: torch.Tensor,
        padding_mask: torch.Tensor | None = None,
    ) -> torch.Tensor:
        """Return logits for a batch of log sequences."""
        encoded = self.encoder(inputs, src_key_padding_mask=padding_mask)
        if padding_mask is None:
            pooled = encoded.mean(dim=1)
        else:
            valid_mask = (~padding_mask).unsqueeze(-1).type_as(encoded)
            pooled = (encoded * valid_mask).sum(dim=1) / valid_mask.sum(dim=1).clamp_min(1.0)
        return self.classifier(pooled)
