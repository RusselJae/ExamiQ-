import pytest

from apps.reviews.tutor_services import parse_tutor_structured_reply


class TestParseTutorStructuredReply:
    def test_parses_text_type(self):
        reply = '{"type": "text", "content": "Symmetry means balanced halves."}'
        parsed = parse_tutor_structured_reply(reply)
        assert parsed == {
            "type": "text",
            "content": "Symmetry means balanced halves.",
        }

    def test_parses_solution_type(self):
        reply = (
            '{"type": "solution", "steps": [{"title": "Step 1", "equations": ["$x=1$"]}], '
            '"answer": "$x=1$"}'
        )
        parsed = parse_tutor_structured_reply(reply)
        assert parsed["type"] == "solution"
        assert len(parsed["steps"]) == 1
        assert parsed["answer"] == "$x=1$"

    def test_legacy_steps_infer_solution(self):
        reply = '{"steps": [{"title": "Divide", "equations": ["$x=2$"]}], "answer": "$x=2$"}'
        parsed = parse_tutor_structured_reply(reply)
        assert parsed["type"] == "solution"
        assert parsed["steps"]

    def test_legacy_answer_only_becomes_text(self):
        reply = '{"answer": "Use the definition of symmetry."}'
        parsed = parse_tutor_structured_reply(reply)
        assert parsed == {
            "type": "text",
            "content": "Use the definition of symmetry.",
        }

    def test_invalid_json_returns_none(self):
        assert parse_tutor_structured_reply("not json") is None

    def test_plain_numbered_calculus_coerces_to_solution(self):
        reply = (
            "1. Set up the integral $\\int_0^{10} x\\,dx$\n"
            "2. Evaluate: $[\\frac{x^2}{2}]_0^{10} = 50$\n"
            "Final answer: 50"
        )
        parsed = parse_tutor_structured_reply(reply)
        assert parsed is not None
        assert parsed["type"] == "solution"
        assert len(parsed["steps"]) >= 2
