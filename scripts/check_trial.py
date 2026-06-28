"""Quick check trial results."""
import json
d = json.load(open("results/fix-parse-int/fix-parse-int-trial-0.json"))
o = d["outcome"]
print(f"Events: {o.get('transcript_events',0)}")
print(f"Tokens: {o.get('total_tokens',0)}")
print(f"Duration: {o.get('total_duration',0):.1f}s")
print(f"Tool calls: {o.get('tool_call_count',0)}")
print(f"Exit code: {o.get('exit_code')}")
print(f"Scores: {d.get('scores',{})}")
stdout = (o.get("stdout","") or "")[-300:]
if stdout:
    print(f"Last output: {stdout}")
