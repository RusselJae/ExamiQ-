import pytest

from apps.reviews.icebreakers import ICEBREAKERS, icebreaker_for_session


class TestIcebreakers:
    def test_all_icebreakers_have_required_fields(self):
        assert len(ICEBREAKERS) == 4
        for item in ICEBREAKERS:
            assert item["slug"]
            assert item["title"]
            assert item["description"]

    def test_icebreaker_is_stable_per_session(self):
        first = icebreaker_for_session(42)
        second = icebreaker_for_session(42)
        assert first == second

    @pytest.mark.parametrize("session_pk", [1, 2, 3, 4, 5, 6, 7, 8])
    def test_icebreaker_is_one_of_four(self, session_pk):
        assert icebreaker_for_session(session_pk) in ICEBREAKERS
