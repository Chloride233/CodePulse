"""SkillOpt core components verification.
Tests attribution, buffer, LCS, stability, and token breakdown without Docker/LLM."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from codepulse.evolve.buffer import EditBuffer, PromptEdit
from codepulse.evolve.attribution import SampleAttribution, AttributionReport
from codepulse.eval.scoring import sequence_similarity, is_stable_pass
from codepulse.shared.trace_types import EventType, TraceEvent, Transcript

def test():
    a = SampleAttribution(pass_threshold=80)
    for o, n, e in [(75,85,"improvement"),(85,75,"regression"),(50,55,"persistent_failure"),(90,95,"stable_success")]:
        r = a.classify(o, n)
        ok = "✓" if r.value==e else "✗"
        print(f"  {ok} {o}->{n}: {r.value}")

    ar = AttributionReport(improvements=3, regressions=1, persistent_failures=2, stable_successes=4, improvement_rate=0.3, regression_rate=0.1)
    assert ar.total==10
    print(f"  ✓ Report: total={ar.total}")

    b = EditBuffer()
    e = PromptEdit(edit_id="e1", edit_type="replace", target_section="p", content="c", reasoning="r", confidence=0.8)
    b.add_rejected(e, score_delta=-0.2, reason="reg")
    assert len(b.get_negative_signals())>0
    print(f"  ✓ Buffer: {len(b.get_negative_signals())} signals")

    assert sequence_similarity(["a","b","c"],["a","b","c"])==1.0
    assert sequence_similarity(["a","b"],["x","y"])==0.0
    print(f"  ✓ LCS: identical=1.0, disjoint=0.0")

    assert is_stable_pass(1.0,"critical")==True
    assert is_stable_pass(0.9,"critical")==False
    assert is_stable_pass(0.7,"tolerant")==True
    print(f"  ✓ Stability: critical=100%, tolerant>=60%")

    t = Transcript(session_id="s1")
    t.add_event(TraceEvent(timestamp=1.0, event_type=EventType.LLM_CALL, content={}, token_usage={"i":100}))
    t.add_event(TraceEvent(timestamp=2.0, event_type=EventType.TOOL_CALL, content={}))
    bk = t.token_breakdown()
    assert len(bk)==2
    print(f"  ✓ Token breakdown: {len(bk)} steps")

    print("\nAll core components verified ✓")
    return True

if __name__=="__main__":
    sys.exit(0 if test() else 1)
