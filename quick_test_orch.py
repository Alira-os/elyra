"""Quick test to see where orchestrator hangs - with timing per step."""
import sys
import time
from datetime import datetime

sys.path.insert(0, ".")

from conductor.orchestrator import MigrationManager

tc = {
    "url": "https://merimeesolutions.wixstudio.com/my-site-2",
    "platform": "wix",
    "site_name": "Merimee Digital Solutions",
    "migration_id": datetime.now().strftime("%Y%m%d_%H%M%S"),
}

print(f"Starting migration {tc['migration_id']}...")
print(f"URL: {tc['url']}")

t0 = time.time()
m = MigrationManager()

# Monkey-patch _decide_next_action to log timing
original_decide = m._decide_next_action
def logged_decide(step, *args, **kwargs):
    t = time.time()
    result = original_decide(step, *args, **kwargs)
    elapsed = time.time() - t
    print(f"  [TIMING] _decide_next_action({step}) took {elapsed:.1f}s -> action={result.action}")
    return result
m._decide_next_action = logged_decide

# Monkey-patch _invoke_persona to log timing
original_invoke = m._invoke_persona
def logged_invoke(persona, *args, **kwargs):
    t = time.time()
    print(f"[INVOKE] Starting {persona}...")
    result = original_invoke(persona, *args, **kwargs)
    elapsed = time.time() - t
    print(f"[INVOKE] {persona} took {elapsed:.1f}s -> success={result.get('success')}")
    return result
m._invoke_persona = logged_invoke

result = m.run(tc)
total = time.time() - t0

print(f"\n=== DONE in {total:.0f}s ({total/60:.1f}min) ===")
print(f"Phase: {result['phase_reached']}")
print(f"Success: {result['success']}")

# Print last few trace events for debugging
trace = result.get("trace", [])
print(f"\nLast 5 trace events:")
for event in trace[-5:]:
    print(f"  {event.get('timestamp', '?')} {event.get('event', '?')}: {str(event.get('payload', {}))[:200]}")