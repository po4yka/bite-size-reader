import pytest
from pydantic import ValidationError as PydanticValidationError

from app.api.models.requests import CreateGoalRequest


class TestCreateGoalValidation:
    def test_global_goal_valid(self):
        req = CreateGoalRequest(goal_type="daily", target_count=5)
        assert req.scope_type == "global"
        assert req.scope_id is None

    def test_global_goal_with_scope_id_rejected(self):
        """Global goals must not have scope_id."""
        with pytest.raises(PydanticValidationError):
            CreateGoalRequest(goal_type="daily", target_count=5, scope_type="global", scope_id=1)

    def test_tag_goal_valid(self):
        req = CreateGoalRequest(goal_type="weekly", target_count=3, scope_type="tag", scope_id=42)
        assert req.scope_type == "tag"
        assert req.scope_id == 42

    def test_tag_goal_without_scope_id_rejected(self):
        """Tag-scoped goals require scope_id."""
        with pytest.raises(PydanticValidationError):
            CreateGoalRequest(goal_type="weekly", target_count=3, scope_type="tag")

    def test_collection_goal_valid(self):
        req = CreateGoalRequest(
            goal_type="monthly", target_count=10, scope_type="collection", scope_id=7
        )
        assert req.scope_type == "collection"
        assert req.scope_id == 7

    def test_collection_goal_without_scope_id_rejected(self):
        """Collection-scoped goals require scope_id."""
        with pytest.raises(PydanticValidationError):
            CreateGoalRequest(goal_type="monthly", target_count=10, scope_type="collection")

    def test_invalid_scope_type(self):
        with pytest.raises(PydanticValidationError):
            CreateGoalRequest(goal_type="daily", target_count=5, scope_type="domain")

    def test_target_count_bounds(self):
        # Min
        req = CreateGoalRequest(goal_type="daily", target_count=1)
        assert req.target_count == 1
        # Max
        req = CreateGoalRequest(goal_type="daily", target_count=1000)
        assert req.target_count == 1000
        # Over max
        with pytest.raises(PydanticValidationError):
            CreateGoalRequest(goal_type="daily", target_count=1001)

    def test_target_count_zero_rejected(self):
        with pytest.raises(PydanticValidationError):
            CreateGoalRequest(goal_type="daily", target_count=0)

    def test_target_count_negative_rejected(self):
        with pytest.raises(PydanticValidationError):
            CreateGoalRequest(goal_type="daily", target_count=-1)

    def test_invalid_goal_type(self):
        with pytest.raises(PydanticValidationError):
            CreateGoalRequest(goal_type="yearly", target_count=5)

    def test_scope_id_zero_rejected_for_tag(self):
        """scope_id must be a positive integer for non-global scopes."""
        with pytest.raises(PydanticValidationError):
            CreateGoalRequest(goal_type="daily", target_count=5, scope_type="tag", scope_id=0)

    def test_scope_id_negative_rejected_for_collection(self):
        """scope_id must be a positive integer for non-global scopes."""
        with pytest.raises(PydanticValidationError):
            CreateGoalRequest(
                goal_type="daily", target_count=5, scope_type="collection", scope_id=-1
            )
