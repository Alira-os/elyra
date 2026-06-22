import subprocess, time, sys
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
sys.path.insert(0, '.')
from skills.agentic.scraper_agent import build_scraper_prompt
prompt = build_scraper_prompt('https://highlandtreeservices.com/')
print(f'Prompt: {len(prompt):,} chars')
t0 = time.time()
try:
    r = subprocess.run(
        [r'C:\Users\micha\AppData\Roaming\npm\node_modules\@kilocode\cli\node_modules\@kilocode\cli-windows-x64\bin\kilo.exe',
         'run', '--format', 'json', '--auto', '--', prompt],
        capture_output=True, text=True, cwd='.', timeout=60,
        encoding='utf-8', errors='replace',
    )
    print(f'rc={r.returncode} in {time.time()-t0:.1f}s')
    # Just dump the full output
    print('=== STDOUT ===')
    print(r.stdout)
    print('=== STDERR ===')
    print(r.stderr[-1000:] if r.stderr else '(empty)')
except subprocess.TimeoutExpired as e:
    print(f'TIMEOUT after {time.time()-t0:.1f}s')
    print('=== partial stdout ===')
    print(e.stdout if e.stdout else '(empty)')
