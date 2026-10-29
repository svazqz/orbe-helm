"""Direct-file CLI entry for runtime bridges, including alternate definitions roots."""
import sys
from pathlib import Path

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from orbehelm.cli import main

if __name__ == '__main__':
    raise SystemExit(main())
