"""Explicitly configured local FastEmbed inference; ordinary queries never download."""
import hashlib
import importlib.metadata
from contextlib import contextmanager
import math
import os
from pathlib import Path

from ...domain.shared.errors import OrbeHelmError

DEFAULT_MODEL = 'sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2'


def cache_digest(cache):
    root = Path(cache).resolve()
    hashes = []
    for file in sorted(root.rglob('*')):
        if not file.is_file() or file.suffix not in {'.onnx', '.json', '.txt', '.model', '.bin', '.safetensors'}:
            continue
        if not file.resolve().is_relative_to(root):
            raise OrbeHelmError('Embedding model cache escapes its configured directory')
        sha = hashlib.sha256()
        with file.open('rb') as handle:
            for block in iter(lambda: handle.read(1024 * 1024), b''):
                sha.update(block)
        hashes.append(file.relative_to(root).as_posix() + ':' + sha.hexdigest())
    if not hashes:
        raise OrbeHelmError('No local embedding model artifacts found; configure with --download-model')
    return hashlib.sha256('\n'.join(hashes).encode()).hexdigest()


@contextmanager
def model_environment(cache):
    # Scope third-party caches to application storage. Never consult a personal HF token.
    values = {'HF_HOME': str(cache / 'hub-home'), 'HF_TOKEN_PATH': str(cache / 'anonymous-token'),
              'HF_HUB_DISABLE_IMPLICIT_TOKEN': '1', 'HF_HUB_DISABLE_TELEMETRY': '1',
              'HF_HUB_DISABLE_XET': '1', 'HF_XET_CACHE': str(cache / 'xet'), 'DO_NOT_TRACK': '1'}
    previous = {key: os.environ.get(key) for key in values}
    os.environ.update(values)
    try:
        yield
    finally:
        for key, value in previous.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


class FastEmbed:
    def __init__(self, cache, settings, download=False, reconfigure=False):
        self.cache = Path(cache).resolve()
        self.cache.mkdir(parents=True, exist_ok=True, mode=0o700)
        if any(p.is_symlink() for p in (Path(cache), *Path(cache).parents)):
            raise OrbeHelmError('Embedding cache must not traverse symlinks')
        name = settings.get('name', DEFAULT_MODEL)
        with model_environment(self.cache):
            try:
                from fastembed import TextEmbedding
                import onnxruntime
                onnxruntime.disable_telemetry_events()
            except ImportError as error:
                raise OrbeHelmError('Local embeddings need the memory extra; install requirements-memory.lock in the application venv') from error
            supported = {row['model']: row for row in TextEmbedding.list_supported_models()}
            if name not in supported:
                raise OrbeHelmError('Unsupported local embedding model: ' + name)
            if download:
                from huggingface_hub import snapshot_download, constants
                description = supported[name]
                source = description['sources'].get('hf')
                if not source:
                    raise OrbeHelmError('Choose a supported public Hugging Face embedding model')
                patterns = [description['model_file'], *description.get('additional_files', []),
                            'config.json', 'tokenizer.json', 'tokenizer_config.json', 'special_tokens_map.json']
                old_xet = constants.HF_HUB_DISABLE_XET
                constants.HF_HUB_DISABLE_XET = True
                try:
                    # Explicit token=False also prevents reading cached personal credentials.
                    model_path = Path(snapshot_download(source, cache_dir=str(self.cache),
                        allow_patterns=patterns, token=False)).resolve()
                finally:
                    constants.HF_HUB_DISABLE_XET = old_xet
            else:
                model_path = (self.cache / settings.get('model_path', '')).resolve()
                if cache_digest(self.cache) != settings.get('artifact_digest'):
                    raise OrbeHelmError('Embedding artifacts changed; explicitly reconfigure and reindex memory')
            if not model_path.is_relative_to(self.cache) or not model_path.is_dir():
                raise OrbeHelmError('Embedding model path must remain in its application cache')
            self.model = TextEmbedding(model_name=name, cache_dir=str(self.cache),
                specific_model_path=str(model_path), local_files_only=True, threads=2,
                providers=['CPUExecutionProvider'])
        digest = cache_digest(self.cache)
        version = importlib.metadata.version('fastembed')
        runtime_versions = {name: importlib.metadata.version(name) for name in ('onnxruntime', 'numpy', 'tokenizers')}
        self.settings = {'provider': 'fastembed', 'name': name, 'artifact_digest': digest,
                         'library_version': version, 'model_path': model_path.relative_to(self.cache).as_posix(),
                         'adapter_version': 1, 'runtime_versions': runtime_versions}
        runtime_id = hashlib.sha256(str(sorted(runtime_versions.items())).encode()).hexdigest()[:16]
        self.model_id = name + ':' + version + ':' + digest + ':pool-v1:' + runtime_id
        if not download and not reconfigure and (version != settings.get('library_version')
                or runtime_versions != settings.get('runtime_versions') or settings.get('adapter_version') != 1):
            raise OrbeHelmError('Embedding library changed; explicitly reconfigure and reindex memory')
        tokenizer = getattr(self.model.model, 'tokenizer', None)
        if tokenizer is None:
            raise OrbeHelmError('Choose a tokenizer-backed local text embedding model')
        self.max_tokens = (tokenizer.truncation or {}).get('max_length', 128)
        from tokenizers import Tokenizer
        self.raw_tokenizer = Tokenizer.from_str(tokenizer.to_str())
        self.raw_tokenizer.no_truncation()
        self.raw_tokenizer.no_padding()

    def _parts(self, text):
        # The provider's token_count applies truncation; use a non-truncating clone.
        pending, result = [text], []
        while pending:
            part = pending.pop(0)
            count = len(self.raw_tokenizer.encode(part).ids)
            if count <= self.max_tokens or len(part) <= 1:
                result.append(part)
            else:
                middle = len(part) // 2
                cut = part.rfind(' ', 0, middle + 1)
                cut = cut if cut > middle // 2 else middle
                pending[0:0] = [part[:cut], part[cut:]]
        return result

    @staticmethod
    def _pool(vectors):
        vectors = [row.tolist() for row in vectors]
        mean = [sum(values) / len(vectors) for values in zip(*vectors)]
        norm = math.sqrt(sum(value * value for value in mean))
        return [value / norm for value in mean] if norm else mean

    def documents(self, texts):
        return [self._pool(self.model.passage_embed(self._parts(text))) for text in texts]

    def query(self, text):
        return self._pool(self.model.query_embed(self._parts(text)))
