"""Generate an original EPUB for a manual reading and packaging smoke check."""

import argparse
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tests.fixtures.epub_factory import make_epub  # noqa: E402

parser = argparse.ArgumentParser()
parser.add_argument(
    "destination",
    type=Path,
    nargs="?",
    default=Path(tempfile.gettempdir()) / "epubify-demo.epub",
)
args = parser.parse_args()
print(make_epub(args.destination))
