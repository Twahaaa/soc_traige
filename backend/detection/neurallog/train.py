"""Train NeuralLog on synthetic, HDFS, or BGL data."""

from __future__ import annotations

import argparse
import logging
from pathlib import Path
from typing import Any, Iterable
from datetime import datetime, timedelta

import numpy as np
import torch
import yaml
from sklearn.metrics import f1_score, precision_score, recall_score
from torch import nn
from torch.utils.data import DataLoader, TensorDataset

from detection.neurallog.embeddings import BERTEmbedder
from detection.neurallog.model import NeuralLog
from ingestion.synthetic_logs import generate_logs
from preprocessing.dataset_loaders.bgl_loader import BGLLoader
from preprocessing.dataset_loaders.hdfs_loader import HDFSLoader
from preprocessing.sequence_builder import tokenize_log_line


def _configure_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    )


def _load_config() -> dict[str, Any]:
    config_path = Path(__file__).resolve().parents[2] / "config" / "settings.yaml"
    with config_path.open("r", encoding="utf-8") as handle:
        return yaml.safe_load(handle)


def _sequences_from_synthetic(count: int, window_size: int) -> list[dict[str, Any]]:
    """Build chronological synthetic sequences without sleeping."""
    half = count // 2
    start_time = datetime(2024, 5, 15, 10, 23, 1)
    generated = list(generate_logs("normal", rate=10.0, count=half, sleep=False, start_time=start_time))
    generated.extend(
        generate_logs(
            "attack",
            rate=10.0,
            count=count - half,
            sleep=False,
            start_time=start_time + timedelta(seconds=max(half, 1) * 10),
        )
    )

    window = []
    sequences: list[dict[str, Any]] = []
    for index, entry in enumerate(generated):
        log_line = entry["log_line"]
        is_attack_mode = index >= half
        window.append(
            {
                "tokens": tokenize_log_line(log_line),
                "raw_line": log_line,
                "timestamp": f"synthetic-{index}",
                "label": 1 if is_attack_mode else 0,
            }
        )
        if len(window) > window_size:
            window.pop(0)
        if len(window) == window_size:
            label = 1 if any(item["label"] == 1 for item in window) else 0
            sequences.append(
                {
                    "sequence": [item["tokens"] for item in window],
                    "raw_lines": [item["raw_line"] for item in window],
                    "label": label,
                    "source": "synthetic",
                }
            )

    return sequences


def _sequences_from_loader(loader: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    return list(loader)


def _chronological_split(items: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Use chronological splits so future patterns do not leak into training."""
    split_index = max(1, int(len(items) * 0.8))
    return items[:split_index], items[split_index:]


def _embed_sequences(
    sequences: list[dict[str, Any]],
    embedder: BERTEmbedder,
) -> tuple[torch.Tensor, torch.Tensor, torch.Tensor]:
    embeddings = []
    masks = []
    labels = []
    max_len = max(len(item["sequence"]) for item in sequences)

    for item in sequences:
        sequence_embeddings = [embedder.embed(tokens) for tokens in item["sequence"]]
        length = len(sequence_embeddings)
        padded = np.zeros((max_len, 768), dtype=np.float32)
        padded[:length] = np.stack(sequence_embeddings)
        mask = np.ones(max_len, dtype=bool)
        mask[:length] = False
        embeddings.append(padded)
        masks.append(mask)
        labels.append(int(item.get("label", 0)))

    inputs = torch.tensor(np.stack(embeddings), dtype=torch.float32)
    padding_masks = torch.tensor(np.stack(masks), dtype=torch.bool)
    targets = torch.tensor(labels, dtype=torch.float32)
    return inputs, padding_masks, targets


def _train_epoch(model: NeuralLog, loader: DataLoader, optimizer: torch.optim.Optimizer, criterion: nn.Module) -> float:
    model.train()
    total_loss = 0.0
    for batch_inputs, batch_masks, batch_targets in loader:
        optimizer.zero_grad()
        logits = model(batch_inputs, batch_masks)
        loss = criterion(logits.squeeze(1), batch_targets)
        loss.backward()
        optimizer.step()
        total_loss += loss.item() * batch_inputs.size(0)
    return total_loss / max(1, len(loader.dataset))


def _evaluate(model: NeuralLog, loader: DataLoader) -> tuple[float, float, float]:
    model.eval()
    y_true: list[int] = []
    y_pred: list[int] = []
    with torch.no_grad():
        for batch_inputs, batch_masks, batch_targets in loader:
            logits = model(batch_inputs, batch_masks)
            probs = torch.sigmoid(logits).squeeze(1)
            y_true.extend(int(x) for x in batch_targets.tolist())
            y_pred.extend(int(x >= 0.5) for x in probs.tolist())

    if not y_true:
        return 0.0, 0.0, 0.0

    return (
        f1_score(y_true, y_pred, zero_division=0),
        precision_score(y_true, y_pred, zero_division=0),
        recall_score(y_true, y_pred, zero_division=0),
    )


def _collect_sequences(
    dataset: str,
    synthetic_count: int,
    window_size: int,
    max_lines: int | None,
) -> list[dict[str, Any]]:
    if dataset == "synthetic":
        return _sequences_from_synthetic(synthetic_count, window_size)
    if dataset == "hdfs":
        return _sequences_from_loader(HDFSLoader().load_sequences("data/raw", max_lines=max_lines))
    if dataset == "bgl":
        return _sequences_from_loader(BGLLoader().load_sequences("data/raw", max_lines=max_lines))
    raise ValueError("dataset must be synthetic, hdfs, or bgl")


def main() -> None:
    _configure_logging()
    logger = logging.getLogger("neurallog_train")

    parser = argparse.ArgumentParser(description="Train the NeuralLog anomaly detector.")
    parser.add_argument("--dataset", choices=["synthetic", "hdfs", "bgl"], default="synthetic")
    parser.add_argument("--epochs", type=int, default=10)
    parser.add_argument("--synthetic_count", type=int, default=5000)
    parser.add_argument("--output", type=str, default=None)
    parser.add_argument("--max_lines", type=int, default=None)
    args = parser.parse_args()

    config = _load_config()
    window_size = int(config["neurallog"]["window_size"])
    sequences = _collect_sequences(args.dataset, args.synthetic_count, window_size, args.max_lines)
    if not sequences:
        raise RuntimeError("No sequences available for training")

    train_sequences, test_sequences = _chronological_split(sequences)
    if not test_sequences:
        test_sequences = train_sequences[-1:]

    embedder = BERTEmbedder(
        model_name=config["neurallog"]["bert_model"],
        cache_dir=config["neurallog"]["embedding_cache_dir"],
    )

    train_inputs, train_masks, train_targets = _embed_sequences(train_sequences, embedder)
    test_inputs, test_masks, test_targets = _embed_sequences(test_sequences, embedder)

    train_dataset = TensorDataset(train_inputs, train_masks, train_targets)
    test_dataset = TensorDataset(test_inputs, test_masks, test_targets)
    train_loader = DataLoader(train_dataset, batch_size=8, shuffle=True)
    test_loader = DataLoader(test_dataset, batch_size=8)

    positives = train_targets.sum().item()
    negatives = max(1.0, len(train_targets) - positives)
    pos_weight = torch.tensor([negatives / max(1.0, positives)], dtype=torch.float32)

    model = NeuralLog(
        input_dim=768,
        nhead=int(config["neurallog"]["nhead"]),
        num_layers=int(config["neurallog"]["num_layers"]),
        dim_feedforward=int(config["neurallog"]["dim_feedforward"]),
        dropout=float(config["neurallog"]["dropout"]),
    )

    criterion = nn.BCEWithLogitsLoss(pos_weight=pos_weight)
    optimizer = torch.optim.Adam(model.parameters(), lr=1e-4)

    for epoch in range(1, args.epochs + 1):
        loss = _train_epoch(model, train_loader, optimizer, criterion)
        f1, precision, recall = _evaluate(model, test_loader)
        logger.info(
            "epoch=%d loss=%.4f f1=%.4f precision=%.4f recall=%.4f",
            epoch,
            loss,
            f1,
            precision,
            recall,
        )

    if args.output is None:
        if args.dataset == "hdfs":
            output_path = Path("data/models/neurallog_hdfs.pt")
        elif args.dataset == "bgl":
            output_path = Path("data/models/neurallog_bgl.pt")
        else:
            output_path = Path("data/models/neurallog.pt")
    else:
        output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    torch.save(
        {
            "model_state_dict": model.state_dict(),
            "config": config["neurallog"],
        },
        output_path,
    )

    f1, precision, recall = _evaluate(model, test_loader)
    print(
        f"Training complete. Test F1: {f1:.2f} | Precision: {precision:.2f} | Recall: {recall:.2f}"
    )


if __name__ == "__main__":
    main()
