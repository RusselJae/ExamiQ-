"""Tests for tutor structured-reply parsing and question-context rendering."""

from apps.ai.prompts import format_question_context
from apps.ai.stubs import StubTutorEngine
from apps.reviews.tutor_services import parse_tutor_structured_reply


def test_stub_text_reply_includes_table_and_remember():
    reply = StubTutorEngine().chat("Algebra", "Hello")
    structured = parse_tutor_structured_reply(reply)
    assert structured["type"] == "text"
    assert structured["remember"]
    assert any(
        block.get("kind") == "table" for block in structured["blocks"]
    )


class TestParseTextReplies:
    def test_new_text_blocks_normalized(self):
        reply = (
            '{"type":"text",'
            '"blocks":[{"kind":"paragraph","text":"A paragraph sentence."},'
            '{"kind":"list","items":["item one","item two"]},'
            '{"kind":"math","latex":"p \\\\land q"}],'
            '"remember":"Name the rule first.",'
            '"follow_ups":["Ask a follow-up question"]}'
        )
        structured = parse_tutor_structured_reply(reply)
        assert structured["type"] == "text"
        assert structured["blocks"] == [
            {"kind": "paragraph", "text": "A paragraph sentence."},
            {"kind": "list", "items": ["item one", "item two"]},
            {"kind": "math", "latex": "p \\land q"},
        ]
        assert structured["remember"] == "Name the rule first."
        assert structured["follow_ups"] == ["Ask a follow-up question"]
        # Plain fallback keeps old-style rendering paths working.
        assert structured["content"] == "A paragraph sentence.\nitem one\nitem two"

    def test_text_table_block_normalized(self):
        reply = (
            '{"type":"text",'
            '"blocks":[{"kind":"table",'
            '"headers":["Symbol","Name"],'
            '"rows":[["p","Simple"],["p \\\\land q","Compound"]]}]}'
        )
        structured = parse_tutor_structured_reply(reply)
        assert structured["type"] == "text"
        assert structured["blocks"] == [
            {
                "kind": "table",
                "headers": ["Symbol", "Name"],
                "rows": [["p", "Simple"], ["p \\land q", "Compound"]],
            }
        ]
        assert "Symbol | Name" in structured["content"]

    def test_text_table_block_rejects_bad_shape(self):
        reply = (
            '{"type":"text",'
            '"blocks":[{"kind":"table","headers":["Only one"],'
            '"rows":[["value"]]},'
            '{"kind":"paragraph","text":"Kept."}]}'
        )
        structured = parse_tutor_structured_reply(reply)
        assert structured["blocks"] == [{"kind": "paragraph", "text": "Kept."}]

    def test_text_content_preserves_remember_and_follow_ups(self):
        reply = (
            '{"type":"text","content":"A short answer.",'
            '"remember":"Check the condition first.",'
            '"follow_ups":["Give an example"]}'
        )
        structured = parse_tutor_structured_reply(reply)
        assert structured == {
            "type": "text",
            "content": "A short answer.",
            "follow_ups": ["Give an example"],
            "remember": "Check the condition first.",
        }

    def test_legacy_text_content_still_parses(self):
        structured = parse_tutor_structured_reply('{"type":"text","content":"Hi"}')
        assert structured == {"type": "text", "content": "Hi"}

    def test_text_without_content_or_blocks_is_none(self):
        assert parse_tutor_structured_reply('{"type":"text"}') is None

    def test_redirect_single_step_reply_parses_as_text(self):
        reply = (
            '{"type":"solution",'
            '"steps":[{"title":"Redirect","operation":"stay on the current topic"}],'
            '"answer":""}'
        )
        structured = parse_tutor_structured_reply(reply)
        assert structured["type"] == "text"
        assert "stay on the current topic" in structured["content"]


class TestParseSolutionReplies:
    def test_new_latex_steps_pass_through(self):
        reply = (
            '{"type":"solution",'
            '"steps":[{"title":"Apply the rule","latex":["x = 2\\\\hl{3}"],'
            '"explain":"The rule doubles each term."}],'
            '"answer":"x = 6",'
            '"check":"Plug in x = 6.",'
            '"follow_ups":["Why is that so?"]}'
        )
        structured = parse_tutor_structured_reply(reply)
        assert structured["type"] == "solution"
        assert structured["steps"] == [
            {
                "title": "Apply the rule",
                "latex": ["x = 2\\hl{3}"],
                "explain": "The rule doubles each term.",
            }
        ]
        assert structured["answer"] == "x = 6"
        assert structured["check"] == "Plug in x = 6."
        assert structured["follow_ups"] == ["Why is that so?"]

    def test_legacy_equations_highlight_rows_pass_through(self):
        reply = (
            '{"type":"solution",'
            '"steps":[{"title":"Expand the brackets",'
            '"equations":["$3(x - 2) = 2x + 5$","$3x - 6 = 2x + 5$"],'
            '"highlight":"3x - 6"}],'
            '"answer":"$x = 11$"}'
        )
        structured = parse_tutor_structured_reply(reply)
        assert structured["type"] == "solution"
        assert structured["steps"][0]["equations"] == [
            "$3(x - 2) = 2x + 5$",
            "$3x - 6 = 2x + 5$",
        ]
        assert structured["steps"][0]["highlight"] == "3x - 6"
        assert structured["answer"] == "$x = 11$"

    def test_bad_step_type_falls_back(self):
        reply = '{"type":"solution","steps":["not a dict"],"answer":"x = 1"}'
        structured = parse_tutor_structured_reply(reply)
        assert structured is None or structured.get("type") != "solution"

    def test_bad_latex_type_falls_back(self):
        reply = '{"type":"solution","steps":[{"latex":"x = 1"}],"answer":""}'
        structured = parse_tutor_structured_reply(reply)
        assert structured is None or structured.get("type") != "solution"


class TestParseConceptCheckReplies:
    def test_concept_check_normalized(self):
        reply = (
            '{"type":"concept_check",'
            '"student_pick":"B","correct":"D",'
            '"mistake":"B skips the defining condition.",'
            '"rule":"Test each option against the definition.",'
            '"options":[{"id":"A","text":"The sky is blue","fits":false,'
            '"tag":"Simple","reason":"Does not fit."},'
            '{"id":"D","text":"It is raining and the sun is shining",'
            '"fits":true,"tag":"Compound","reason":"Matches."}],'
            '"symbolic":{"latex":"p \\\\land q","explain":"Both must hold."},'
            '"quick_check":"Try another one.",'
            '"remember":"Test the defining condition first.",'
            '"follow_ups":["Why is B wrong?"]}'
        )
        structured = parse_tutor_structured_reply(reply)
        assert structured["type"] == "concept_check"
        assert structured["student_pick"] == "B"
        assert structured["correct"] == "D"
        assert structured["mistake"] == "B skips the defining condition."
        assert structured["options"] == [
            {
                "id": "A",
                "fits": False,
                "reason": "Does not fit.",
                "text": "The sky is blue",
                "tag": "Simple",
            },
            {
                "id": "D",
                "fits": True,
                "reason": "Matches.",
                "text": "It is raining and the sun is shining",
                "tag": "Compound",
            },
        ]
        assert structured["symbolic"] == {
            "latex": "p \\land q",
            "explain": "Both must hold.",
        }
        assert structured["quick_check"] == "Try another one."
        assert structured["remember"] == "Test the defining condition first."
        assert structured["follow_ups"] == ["Why is B wrong?"]

    def test_concept_check_without_options_fails(self):
        reply = '{"type":"concept_check","correct":"D","options":[]}'
        assert parse_tutor_structured_reply(reply) is None

    def test_concept_check_without_correct_fails(self):
        reply = (
            '{"type":"concept_check",'
            '"options":[{"id":"A","fits":true,"reason":"ok"}]}'
        )
        assert parse_tutor_structured_reply(reply) is None

    def test_concept_check_beats_legacy_steps_heuristic(self):
        # No steps / no equations → concept_check must not become a solution.
        reply = (
            '{"type":"concept_check","correct":"A",'
            '"options":[{"id":"A","fits":true,"reason":"ok"}],'
            '"rule":"definition"}'
        )
        structured = parse_tutor_structured_reply(reply)
        assert structured["type"] == "concept_check"


class TestFormatQuestionContext:
    def test_renders_subject_and_choices(self):
        block = format_question_context(
            {
                "stem": "Which statement is compound?",
                "subject_code": "BSEM 22",
                "subject_name": "College Algebra",
                "choices": [
                    {"id": "A", "text": "p AND q"},
                    {"id": "B", "text": "not p"},
                ],
                "student_pick": "B",
            }
        )
        assert "Subject: BSEM 22 – College Algebra" in block
        assert "A) p AND q" in block
        assert "B) not p" in block
        assert "Student picked: B" in block

    def test_omits_subject_line_without_code(self):
        block = format_question_context({"stem": "Solve 2x = 4"})
        assert "Subject:" not in block
        assert "Solve 2x = 4" in block

    def test_empty_context_is_blank(self):
        assert format_question_context({}) == ""
        assert format_question_context(None) == ""
