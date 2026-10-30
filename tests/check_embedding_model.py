"""Explicit local model integration check; no authenticated agent session is started."""
import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from orbehelm.infrastructure.memory.embeddings import DEFAULT_MODEL, FastEmbed

parser = argparse.ArgumentParser()
parser.add_argument('--download', action='store_true')
args = parser.parse_args()
root = Path(__file__).resolve().parents[1] / 'state/verification/knowledge-memory/real-model'
root.mkdir(parents=True, exist_ok=True)
settings_file = root / 'settings.json'
settings = json.loads(settings_file.read_text()) if settings_file.exists() else {'name': DEFAULT_MODEL}
provider = FastEmbed(root / 'models', settings, download=args.download, reconfigure=True)
settings_file.write_text(json.dumps(provider.settings, indent=2) + '\n')
vectors = provider.documents(['A dog waits beside its owner.', 'Database migrations preserve table history.'])
query = provider.query('Un perro espera junto a su dueño.')
def score(vector):
    return sum(a*b for a,b in zip(query, vector))
assert score(vectors[0]) > score(vectors[1]), 'Multilingual semantic relevance check failed'
assert all(len(vector) == 384 for vector in [*vectors, query])
parts = provider._parts('A dog waits beside its owner. ' * 200)
assert len(parts) > 1 and all(len(provider.raw_tokenizer.encode(part).ids) <= provider.max_tokens for part in parts)
print('Real local multilingual embeddings passed: Spanish paraphrase ranks the English dog fact above database text.')
print('Model artifact identity:', provider.model_id)
