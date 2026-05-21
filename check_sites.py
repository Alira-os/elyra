import json
from pathlib import Path

for f in sorted(Path("memory/site_understandings").glob("*.json")):
    data = json.loads(f.read_text())
    print(f"{f.stem}: {data.get('source_url', 'N/A')} | {data.get('site_name', 'N/A')}")