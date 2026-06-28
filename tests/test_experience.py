"""三级经验进化测试。"""

from codepulse.evolve.experience import ExperienceEvolution, Instinct, Lesson, Pattern


class TestExperienceEvolution:
    def test_initial_state(self) -> None:
        ee = ExperienceEvolution()
        assert ee.lessons == []
        assert ee.patterns == []
        assert ee.instincts == []

    def test_record_lesson(self) -> None:
        ee = ExperienceEvolution()
        lesson = ee.record_lesson("Agent retried 5 times on task X", source="evaluation")
        assert lesson.lesson_id.startswith("lesson-")
        assert lesson.source == "evaluation"
        assert len(ee.lessons) == 1

    def test_record_lesson_with_context(self) -> None:
        ee = ExperienceEvolution()
        lesson = ee.record_lesson("High token usage", context={"tokens": 50000}, source="observe")
        assert lesson.context["tokens"] == 50000

    def test_no_promotion_when_below_threshold(self) -> None:
        ee = ExperienceEvolution()
        ee.record_lesson("Some observation", source="eval")
        patterns = ee.try_promote_to_pattern(min_occurrences=2)
        assert patterns == []
        assert len(ee.patterns) == 0

    def test_promote_to_pattern(self) -> None:
        ee = ExperienceEvolution()
        for _ in range(3):
            ee.record_lesson("Agent ignores error handling", source="eval")
        patterns = ee.try_promote_to_pattern(min_occurrences=2)
        assert len(patterns) == 1
        assert patterns[0].observation == "Agent ignores error handling"
        assert patterns[0].lesson_count == 3

    def test_promote_multiple_patterns(self) -> None:
        ee = ExperienceEvolution()
        for _ in range(2):
            ee.record_lesson("Pattern A")
        for _ in range(2):
            ee.record_lesson("Pattern B")
        patterns = ee.try_promote_to_pattern(min_occurrences=2)
        assert len(patterns) == 2

    def test_deduplicate_patterns(self) -> None:
        ee = ExperienceEvolution()
        for _ in range(2):
            ee.record_lesson("Same pattern")
        patterns_a = ee.try_promote_to_pattern(min_occurrences=2)
        for _ in range(2):
            ee.record_lesson("Same pattern")
        patterns_b = ee.try_promote_to_pattern(min_occurrences=2)
        assert len(patterns_a) == 1
        assert len(patterns_b) == 0

    def test_no_promotion_to_instinct_when_low_confidence(self) -> None:
        ee = ExperienceEvolution()
        for _ in range(2):
            ee.record_lesson("Low confidence pattern")
        ee.try_promote_to_pattern(min_occurrences=2)
        instincts = ee.try_promote_to_instinct(confidence_threshold=0.9, verification_threshold=1)
        assert instincts == []

    def test_verify_pattern(self) -> None:
        ee = ExperienceEvolution()
        for _ in range(2):
            ee.record_lesson("Test pattern")
        ee.try_promote_to_pattern(min_occurrences=2)
        pattern_id = ee.patterns[0].pattern_id
        assert ee.verify_pattern(pattern_id) is True
        assert ee.verify_pattern("nonexistent") is False
        assert ee.patterns[0].verification_count == 1

    def test_get_active_instincts(self) -> None:
        ee = ExperienceEvolution()
        for _ in range(2):
            ee.record_lesson("High confidence test pattern")
        ee.try_promote_to_pattern(min_occurrences=2)
        ee.get_stats()  # smoke test

    def test_get_stats(self) -> None:
        ee = ExperienceEvolution()
        ee.record_lesson("Lesson 1")
        ee.record_lesson("Lesson 2")
        stats = ee.get_stats()
        assert stats["lessons"] == 2
        assert stats["patterns"] == 0
        assert stats["instincts"] == 0

    def test_infer_tags_blackhole(self) -> None:
        tags = ExperienceEvolution._infer_tags("retry loop detected")
        assert "blackhole" in tags

    def test_infer_tags_efficiency(self) -> None:
        tags = ExperienceEvolution._infer_tags("high token cost")
        assert "efficiency" in tags

    def test_infer_tags_prompt(self) -> None:
        tags = ExperienceEvolution._infer_tags("prompt instruction unclear")
        assert "prompt" in tags

    def test_infer_tags_tool(self) -> None:
        tags = ExperienceEvolution._infer_tags("tool call failed")
        assert "tool" in tags

    def test_infer_tags_context(self) -> None:
        tags = ExperienceEvolution._infer_tags("context window exceeded")
        assert "context" in tags

    def test_infer_tags_general(self) -> None:
        tags = ExperienceEvolution._infer_tags("something general")
        assert tags == ["general"]


class TestDataClasses:
    def test_lesson_defaults(self) -> None:
        lesson = Lesson(lesson_id="l1", observation="obs")
        assert lesson.context == {}
        assert lesson.timestamp == ""
        assert lesson.source == ""

    def test_pattern_defaults(self) -> None:
        pattern = Pattern(pattern_id="p1", observation="obs")
        assert pattern.confidence == 0.0
        assert pattern.tags == []

    def test_instinct_defaults(self) -> None:
        instinct = Instinct(instinct_id="i1", pattern_id="p1", rule="do X")
        assert instinct.active is True
        assert instinct.confidence == 0.0
