"""Measure isolated keyword memory retrieval; never opens an operational store."""

import argparse
import json
from pathlib import Path
import statistics
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))


def positive(value: str) -> int:
    count = int(value)
    if count < 1:
        raise argparse.ArgumentTypeError('must be positive')
    return count


def main() -> None:
    from orbehelm.application.use_cases.memory import MemoryService
    from orbehelm.infrastructure.memory.sqlite import SQLiteMemory
    from orbehelm.product.database import Store, migrate
    from orbehelm.product.models import Project

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--units', type=positive, default=100)
    parser.add_argument('--queries', type=positive, default=30)
    args = parser.parse_args()
    base = ROOT / 'state/verification/benchmarks'
    base.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=base) as directory:
        root = Path(directory)
        migrate(root)
        store = Store(root)
        try:
            with store.write() as db:
                db.add(Project(id='benchmark', path=str(root / 'project'), name='benchmark'))
            repo = SQLiteMemory(root / 'state/orbehelm.sqlite3', root / 'state/memory-index.sqlite3')
            repo.ensure_owner('benchmark-owner', 'benchmark')
            service = MemoryService(repo, 'benchmark-owner')
            for number in range(args.units):
                service.put(
                    f'Migration decision {number} preserves history for component {number % 10}.',
                    f'benchmark:{number}',
                    kind='decision',
                    evidence=[f'fixture:component:{number}'],
                )
            repo.finish_index()
            samples = []
            result = service.query('migration component history')
            for _ in range(args.queries):
                started = time.perf_counter()
                result = service.query('migration component history')
                samples.append((time.perf_counter() - started) * 1000)
            ordered = sorted(samples)
            print(
                json.dumps(
                    {
                        'units': args.units,
                        'queries': args.queries,
                        'mode': result['mode'],
                        'p50_ms': statistics.median(samples),
                        'p95_ms': ordered[min(len(ordered) - 1, int(len(ordered) * 0.95))],
                        'pending_index_units': result['pending_index_units'],
                        'pending_embeddings': result['pending_embeddings'],
                    },
                    indent=2,
                )
            )
        finally:
            store.close()


if __name__ == '__main__':
    main()
