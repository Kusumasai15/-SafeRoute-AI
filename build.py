"""Copy browser assets to Vercel's public directory."""
from pathlib import Path
from shutil import copytree

root = Path(__file__).resolve().parent
copytree(root / 'app' / 'static', root / 'public' / 'static', dirs_exist_ok=True)
