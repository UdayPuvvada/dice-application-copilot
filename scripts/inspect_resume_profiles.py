from pathlib import Path
import re
import sys

from pypdf import PdfReader


root = Path(sys.argv[1])
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
start_after = sys.argv[2].lower() if len(sys.argv) > 2 else ""
started = not start_after
for path in sorted(root.rglob("*.pdf"), key=lambda item: str(item).lower()):
    relative = str(path.relative_to(root))
    if not started:
        started = start_after in relative.lower()
    if not started:
        continue
    reader = PdfReader(path)
    text = "\n".join((page.extract_text() or "") for page in reader.pages[:2])
    lines = [re.sub(r"\s+", " ", line).strip() for line in text.splitlines()]
    lines = [line for line in lines if line]
    print(f"\n## {relative} | pages={len(reader.pages)}")
    print(" | ".join(lines[:14])[:1800])
