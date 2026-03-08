import pytest

from code_compass_acp.memory.memory_extractor import (
    ExtractedMemory,
    MemoryExtractor,
    MemoryKind,
    MemoryStance,
    MemoryTopic,
)


def _one(result: list[ExtractedMemory]) -> ExtractedMemory:
    assert len(result) == 1, f"Esperava 1 memória, vieram {len(result)}: {result}"
    return result[0]


def test_extract_name_ptbr() -> None:
    extractor = MemoryExtractor()
    result = extractor.extract(user_text="meu nome é Junior Martins")

    memory = _one(result)
    assert memory.kind == MemoryKind.PROFILE
    assert memory.topic == MemoryTopic.NAME
    assert memory.value == "Junior Martins"
    assert memory.stance == MemoryStance.IDENTITY
    assert memory.confidence == pytest.approx(0.95)
    assert "meu nome é Junior Martins" in memory.source_excerpt
    assert memory.source_start >= 0
    assert memory.source_end > memory.source_start


def test_extract_name_en() -> None:
    extractor = MemoryExtractor()
    result = extractor.extract(user_text="my name is Junior Martins")

    memory = _one(result)
    assert memory.kind == MemoryKind.PROFILE
    assert memory.topic == MemoryTopic.NAME
    assert memory.value == "Junior Martins"
    assert memory.stance == MemoryStance.IDENTITY


def test_extract_language_preference_ptbr() -> None:
    extractor = MemoryExtractor()
    result = extractor.extract(user_text="prefiro TypeScript como linguagem")

    memory = _one(result)
    assert memory.kind == MemoryKind.PREFERENCE
    assert memory.topic == MemoryTopic.LANGUAGE_PREFERENCE
    assert memory.value == "TypeScript"
    assert memory.stance == MemoryStance.PREFER
    assert memory.confidence == pytest.approx(0.80)


def test_extract_language_preference_en() -> None:
    extractor = MemoryExtractor()
    result = extractor.extract(user_text="I prefer Python as a language")

    memory = _one(result)
    assert memory.topic == MemoryTopic.LANGUAGE_PREFERENCE
    assert memory.value == "Python"
    assert memory.stance == MemoryStance.PREFER


def test_extract_framework_avoidance_ptbr() -> None:
    extractor = MemoryExtractor()
    result = extractor.extract(user_text="não gosto de NestJS framework")

    memory = _one(result)
    assert memory.kind == MemoryKind.PREFERENCE
    assert memory.topic == MemoryTopic.FRAMEWORK_PREFERENCE
    assert memory.value == "NestJS"
    assert memory.stance == MemoryStance.AVOID


def test_extract_framework_preference_with_alias() -> None:
    extractor = MemoryExtractor()
    result = extractor.extract(user_text="i love reactjs library")

    memory = _one(result)
    assert memory.topic == MemoryTopic.FRAMEWORK_PREFERENCE
    assert memory.value == "React"
    assert memory.stance == MemoryStance.PREFER


def test_extract_state_management_direct() -> None:
    extractor = MemoryExtractor()
    result = extractor.extract(user_text="odeio redux")

    memory = _one(result)
    assert memory.kind == MemoryKind.PREFERENCE
    assert memory.topic == MemoryTopic.STATE_MANAGEMENT_PREFERENCE
    assert memory.value == "Redux"
    assert memory.stance == MemoryStance.AVOID


def test_extract_state_management_contextual() -> None:
    extractor = MemoryExtractor()
    result = extractor.extract(user_text="prefiro Zustand para estado")

    memory = _one(result)
    assert memory.topic == MemoryTopic.STATE_MANAGEMENT_PREFERENCE
    assert memory.value == "Zustand"
    assert memory.stance == MemoryStance.PREFER


def test_extract_naming_convention() -> None:
    extractor = MemoryExtractor()
    result = extractor.extract(user_text="sempre uso camelCase para nomear")

    memory = _one(result)
    assert memory.kind == MemoryKind.CONVENTION
    assert memory.topic == MemoryTopic.NAMING_CONVENTION
    assert memory.value == "camelCase"
    assert memory.stance == MemoryStance.REQUIRE


def test_extract_testing_convention() -> None:
    extractor = MemoryExtractor()
    result = extractor.extract(user_text="uso vitest para testes")

    memory = _one(result)
    assert memory.kind == MemoryKind.CONVENTION
    assert memory.topic == MemoryTopic.TESTING_CONVENTION
    assert memory.value == "Vitest"
    assert memory.stance == MemoryStance.REQUIRE


def test_extract_general_convention() -> None:
    extractor = MemoryExtractor()
    result = extractor.extract(user_text="não use redux toolkit")

    memory = _one(result)
    assert memory.kind == MemoryKind.CONVENTION
    assert memory.topic == MemoryTopic.DEVELOPMENT_CONVENTION
    assert memory.value == "Redux Toolkit"
    assert memory.stance == MemoryStance.AVOID


def test_extract_multiple_memories_same_text() -> None:
    extractor = MemoryExtractor()
    result = extractor.extract(user_text="prefiro Zustand para estado e uso Vitest para testes")

    assert len(result) == 2

    topics = {item.topic for item in result}
    values = {item.value for item in result}

    assert MemoryTopic.STATE_MANAGEMENT_PREFERENCE in topics
    assert MemoryTopic.TESTING_CONVENTION in topics
    assert "Zustand" in values
    assert "Vitest" in values


def test_reject_hedged_preference() -> None:
    extractor = MemoryExtractor()
    result = extractor.extract(
        user_text="prefiro TypeScript como linguagem, mas nesse projeto tanto faz"
    )

    assert result == []


def test_reject_usually_marker() -> None:
    extractor = MemoryExtractor()
    result = extractor.extract(user_text="geralmente uso Jest para testes")

    assert result == []


def test_ignore_empty_text() -> None:
    extractor = MemoryExtractor()
    assert extractor.extract(user_text="   ") == []


def test_ignore_long_text_over_limit() -> None:
    extractor = MemoryExtractor()
    long_text = "a" * 501

    assert extractor.extract(user_text=long_text) == []


def test_accept_explicit_zero_min_confidence() -> None:
    extractor = MemoryExtractor(min_confidence=0.0)
    result = extractor.extract(user_text="uso vitest para testes")

    memory = _one(result)
    assert memory.value == "Vitest"


def test_default_threshold_filters_low_confidence_when_needed() -> None:
    extractor = MemoryExtractor(min_confidence=0.90)
    result = extractor.extract(user_text="uso vitest para testes")

    assert result == []


def test_dedupe_same_semantic_value_with_aliases() -> None:
    extractor = MemoryExtractor()
    result = extractor.extract(
        user_text="prefiro ts como linguagem. prefiro TypeScript como linguagem"
    )

    # Dependendo do regex, pode capturar uma ou duas ocorrências,
    # mas a dedupe deve manter apenas uma memória semântica.
    assert len(result) == 1
    assert result[0].topic == MemoryTopic.LANGUAGE_PREFERENCE
    assert result[0].value == "TypeScript"


def test_overlap_keeps_single_best_match_for_same_region() -> None:
    extractor = MemoryExtractor()
    result = extractor.extract(user_text="prefiro redux para estado")

    assert len(result) == 1
    assert result[0].topic == MemoryTopic.STATE_MANAGEMENT_PREFERENCE
    assert result[0].value == "Redux"


def test_source_excerpt_and_offsets_are_consistent() -> None:
    extractor = MemoryExtractor()
    text = "Eu diria que prefiro TypeScript como linguagem."
    result = extractor.extract(user_text=text)

    memory = _one(result)
    extracted_slice = text[memory.source_start : memory.source_end]
    assert "prefiro TypeScript como linguagem" in extracted_slice
    assert "prefiro TypeScript como linguagem" in memory.source_excerpt


def test_assistant_text_is_ignored_for_safety() -> None:
    extractor = MemoryExtractor()
    result = extractor.extract(
        user_text="",
        assistant_text="Você parece preferir TypeScript",
    )

    assert result == []


def test_composed_value_limitation_is_currently_preserved() -> None:
    extractor = MemoryExtractor()
    result = extractor.extract(user_text="não gosto de redux e zustand framework")

    memory = _one(result)
    assert memory.topic == MemoryTopic.FRAMEWORK_PREFERENCE
    assert memory.stance == MemoryStance.AVOID
    assert memory.value == "redux e zustand"


@pytest.mark.parametrize(
    ("text", "expected_value"),
    [
        ("prefiro ts como linguagem", "TypeScript"),
        ("prefiro javascript como linguagem", "JavaScript"),
        ("uso rtl para testes", "React Testing Library"),
        ("não use redux toolkit", "Redux Toolkit"),
        ("prefiro nodejs framework", "Node.js"),
    ],
)
def test_alias_canonicalization(text: str, expected_value: str) -> None:
    extractor = MemoryExtractor(min_confidence=0.0)
    result = extractor.extract(user_text=text)

    memory = _one(result)
    assert memory.value == expected_value
