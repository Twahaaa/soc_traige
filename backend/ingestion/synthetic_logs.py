"""Synthetic log generator for pipeline testing."""

from __future__ import annotations

import random
import time
from datetime import datetime, timedelta
from typing import Generator, Optional


def generate_logs(
    mode: str = "normal",
    rate: float = 10.0,
    count: Optional[int] = None,
    sleep: bool = True,
    start_time: datetime | None = None,
) -> Generator[dict, None, None]:
    """Yield synthetic log entries at a fixed rate.

    Args:
        mode: "normal" for mostly benign traffic, "attack" for mostly malicious.
        rate: Lines per second.
        count: Total lines to produce, or None to stream indefinitely.
        sleep: If False, yield as fast as possible for offline training.
        start_time: Optional starting timestamp for the synthetic stream.
    """
    if mode not in {"normal", "attack"}:
        raise ValueError("mode must be 'normal' or 'attack'")
    if rate <= 0:
        raise ValueError("rate must be > 0")

    # Fixed IP pools keep brute-force detection reliable across runs.
    internal_ips = [f"192.168.1.{i}" for i in range(10, 21)]
    attacker_ips = [f"203.0.113.{i}" for i in range(10, 21)]
    hosts = ["server01", "server02", "server03"]
    users = ["user1", "user2", "user3", "admin"]
    ports = ["22", "2222", "54321", "44444"]
    pids = ["1234", "2222", "5678", "9999", "3141"]

    normal_templates = [
        "{ts} {host} sshd[{pid}]: Accepted password for {user} from {ip} port {port} ssh2",
        "{ts} {host} CRON[{pid}]: (root) CMD (run-parts /etc/cron.hourly)",
        "{ts} {host} systemd[1]: Started OpenSSH Server Daemon",
        "{ts} {host} sshd[{pid}]: pam_unix(sshd:session): session opened for user {user}",
    ]

    attack_templates = [
        "{ts} {host} sshd[{pid}]: Failed password for invalid user {user} from {ip} port 22 ssh2",
        "{ts} {host} sudo: {user} : TTY=pts/0 ; PWD=/home/{user} ; USER=root ; COMMAND=/bin/bash",
        "{ts} {host} kernel: CRITICAL: memory allocation failure in zone DMA",
        "{ts} {host} sshd[{pid}]: Accepted password for root from {ip} port {port} ssh2",
        "{ts} {host} bash[{pid}]: /dev/tcp/{ip}/4444",
    ]

    if mode == "normal":
        attack_probability = 0.1
    else:
        attack_probability = 0.6

    current_time = start_time or datetime(2024, 5, 15, 10, 23, 1)
    produced = 0

    while True:
        # Control attack frequency based on the selected mode.
        is_attack = random.random() < attack_probability
        if is_attack:
            template = random.choice(attack_templates)
            ip = random.choice(attacker_ips)
        else:
            template = random.choice(normal_templates)
            ip = random.choice(internal_ips)

        timestamp = current_time.strftime("%b %d %H:%M:%S")
        line = template.format(
            ts=timestamp,
            host=random.choice(hosts),
            pid=random.choice(pids),
            user=random.choice(users),
            ip=ip,
            port=random.choice(ports),
        )

        yield {"log_line": line, "source_type": "synthetic"}

        produced += 1
        if count is not None and produced >= count:
            break

        # Advance timestamps so logs look like a realistic stream.
        current_time += timedelta(seconds=random.randint(1, 5))
        if sleep:
            time.sleep(1.0 / rate)
