"""Check installed optional-memory binaries without downloading or loading a model."""

import argparse
from importlib.metadata import version
import json
from pathlib import Path
import platform
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))


def main() -> None:
    argparse.ArgumentParser(description=__doc__).parse_args()
    from orbehelm.infrastructure.memory.embeddings import DEFAULT_MODEL, model_environment

    cache = ROOT / 'state/verification/memory-runtime'
    cache.mkdir(parents=True, exist_ok=True)
    with model_environment(cache):
        import numpy as np
        import onnxruntime
        from fastembed import TextEmbedding

        onnxruntime.disable_telemetry_events()
        values = np.array([[1.0, 2.0], [3.0, 4.0]], dtype=np.float32)
        if not np.allclose(values @ values.T, [[5.0, 11.0], [11.0, 25.0]]):
            raise RuntimeError('NumPy binary operations failed')
        providers = onnxruntime.get_available_providers()
        if 'CPUExecutionProvider' not in providers:
            raise RuntimeError('ONNX Runtime CPU provider is unavailable')
        if not any(model['model'] == DEFAULT_MODEL for model in TextEmbedding.list_supported_models()):
            raise RuntimeError('FastEmbed no longer supports the configured default model')
        print(
            json.dumps(
                {
                    'python': platform.python_version(),
                    'packages': {
                        name: version(name) for name in ('fastembed', 'numpy', 'onnxruntime', 'tokenizers')
                    },
                    'providers': providers,
                    'model_downloaded': False,
                },
                indent=2,
            )
        )


if __name__ == '__main__':
    main()
