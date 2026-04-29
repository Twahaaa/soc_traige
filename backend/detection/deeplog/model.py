"""DeepLog baseline stub kept for future benchmarking."""

from __future__ import annotations

from torch import nn


class DeepLog(nn.Module):
    """DeepLog baseline placeholder.

    DeepLog treats log messages as event keys and predicts the next key.
    """

    def __init__(self, *args, **kwargs) -> None:
        super().__init__()

    def forward(self, *args, **kwargs):
        raise NotImplementedError(
            "DeepLog baseline not implemented. See Du et al. 2017 CCS. Implement after NeuralLog is working."
        )
