"""AIT-LDS v2.0 loader placeholder for future transfer learning work."""

from __future__ import annotations

from typing import Any, Iterator


class AITLoader:
    """AIT-LDS v2.0 per-host chronological loader.

    Reference: Zenodo DOI 10.5281/zenodo.5789064, CC BY-NC-SA 4.0 license.
    """

    def load_sequences(self, data_dir: str) -> Iterator[dict[str, Any]]:
        """AIT-LDS is reserved for the transfer-learning stretch goal."""
        raise NotImplementedError(
            "AIT-LDS loader not yet implemented. Reserved for transfer learning stretch goal."
        )
