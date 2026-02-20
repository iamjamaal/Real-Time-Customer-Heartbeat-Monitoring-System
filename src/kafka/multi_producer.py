"""
Multi-Process Kafka Producer
============================
Launches multiple independent producer processes in parallel to multiply
throughput and better demonstrate Kafka's distributed capabilities.

Each worker process creates its own KafkaProducer connection and draws
randomly from the full 10,000-customer pool.  Because all workers use
customer_id as the partition key, Kafka still delivers all readings for
a given customer to the same partition, preserving per-customer ordering
regardless of which worker sent the message.

Throughput scales linearly with the number of workers:
  1 worker  → ~2 events/sec  (0.5s interval per worker)
  4 workers → ~8 events/sec
  8 workers → ~16 events/sec

Usage:
    # Default — PRODUCER_WORKERS from .env (default 1)
    python -m src.kafka.multi_producer

    # Override at runtime
    PRODUCER_WORKERS=4 python -m src.kafka.multi_producer
"""

import logging
import multiprocessing
import sys

from src.config import LOG_LEVEL, PRODUCER_WORKERS

logger = logging.getLogger(__name__)


def _worker_entry(worker_id: int) -> None:
    """
    Entry point for each producer subprocess.

    Logging is re-initialised inside the child process because Python's
    logging handlers are not inherited safely across the process boundary
    on Windows (which uses the 'spawn' start method).
    """
    logging.basicConfig(
        level=getattr(logging, LOG_LEVEL),
        format=(
            f"%(asctime)s [%(levelname)s] "
            f"Worker-{worker_id} %(name)s: %(message)s"
        ),
    )
    # Import here so the heavy module load happens in the child, not the parent
    from src.kafka.producer import run_producer
    run_producer()


def run_multi_producer(workers: int = None) -> None:
    """
    Launch `workers` independent Kafka producer processes in parallel.

    Args:
        workers: Number of producer processes.
                 Defaults to PRODUCER_WORKERS from config / .env.
    """
    n = workers if workers is not None else PRODUCER_WORKERS

    logging.basicConfig(
        level=getattr(logging, LOG_LEVEL),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    logger.info(
        f"Launching {n} producer worker(s) "
        f"(~{n * 2} events/sec combined throughput)"
    )

    processes: list[multiprocessing.Process] = []
    for i in range(n):
        p = multiprocessing.Process(
            target=_worker_entry,
            args=(i,),
            name=f"producer-worker-{i}",
            daemon=True,
        )
        p.start()
        logger.info(f"Worker-{i} started (PID={p.pid})")
        processes.append(p)

    try:
        for p in processes:
            p.join()
    except KeyboardInterrupt:
        logger.info("KeyboardInterrupt received — stopping all workers...")
        for p in processes:
            p.terminate()
        for p in processes:
            p.join(timeout=5)
        logger.info(f"All {n} worker(s) stopped cleanly.")


if __name__ == "__main__":
    # Required on Windows: multiprocessing 'spawn' start method needs this guard
    multiprocessing.freeze_support()
    run_multi_producer()
