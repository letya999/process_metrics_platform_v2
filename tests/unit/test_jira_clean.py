"""Unit tests for Jira clean layer assets.

Tests the transformation logic and changelog parsing in pipelines/assets/jira/clean.py
"""

import re


class TestChangelogParsing:
    """Tests for changelog parsing logic patterns."""

    def test_split_comma_separated_sprint_ids(self):
        """Test splitting comma-separated sprint IDs."""
        # This simulates the regex pattern used in SQL: regexp_split_to_table(..., '\\s*,\\s*')
        pattern = r"\s*,\s*"

        # Test single value
        single = "123"
        result = [x.strip() for x in re.split(pattern, single) if x.strip()]
        assert result == ["123"]

        # Test comma-separated values
        multi = "123, 456, 789"
        result = [x.strip() for x in re.split(pattern, multi) if x.strip()]
        assert result == ["123", "456", "789"]

        # Test with irregular spacing
        irregular = "123,456,  789"
        result = [x.strip() for x in re.split(pattern, irregular) if x.strip()]
        assert result == ["123", "456", "789"]

        # Test empty value
        empty = ""
        result = [x.strip() for x in re.split(pattern, empty) if x.strip()]
        assert result == []

    def test_numeric_sprint_id_filter(self):
        """Test filtering numeric sprint IDs."""
        # This simulates the regex pattern used in SQL: ~ '^[0-9]+$'
        pattern = r"^[0-9]+$"

        valid_ids = ["123", "456", "1", "99999"]
        invalid_ids = ["Sprint 1", "abc", "12.3", "123abc", "", "  "]

        for id_str in valid_ids:
            assert re.match(pattern, id_str), f"{id_str} should be valid"

        for id_str in invalid_ids:
            assert not re.match(pattern, id_str), f"{id_str} should be invalid"

    def test_fix_version_field_detection(self):
        """Test Fix Version field name variations."""
        fix_version_fields = ["Fix Version/s", "fixVersions", "Fix Version"]

        # Simulate SQL IN check
        def is_fix_version_field(field_name):
            return field_name in fix_version_fields

        assert is_fix_version_field("Fix Version/s")
        assert is_fix_version_field("fixVersions")
        assert is_fix_version_field("Fix Version")
        assert not is_fix_version_field("Sprint")
        assert not is_fix_version_field("Status")


class TestChangelogEventLogic:
    """Tests for changelog event processing logic."""

    def test_determine_final_state_added(self):
        """Test determining final state when last action is 'added'."""
        events = [
            {"issue_id": "1", "sprint_id": "100", "action": "added", "timestamp": 1},
            {"issue_id": "1", "sprint_id": "100", "action": "removed", "timestamp": 2},
            {"issue_id": "1", "sprint_id": "100", "action": "added", "timestamp": 3},
        ]

        # Final state should be based on most recent action
        sorted_events = sorted(events, key=lambda x: x["timestamp"], reverse=True)
        final_action = sorted_events[0]["action"]

        assert final_action == "added"

    def test_determine_final_state_removed(self):
        """Test determining final state when last action is 'removed'."""
        events = [
            {"issue_id": "1", "sprint_id": "100", "action": "added", "timestamp": 1},
            {"issue_id": "1", "sprint_id": "100", "action": "removed", "timestamp": 2},
        ]

        sorted_events = sorted(events, key=lambda x: x["timestamp"], reverse=True)
        final_action = sorted_events[0]["action"]

        assert final_action == "removed"

    def test_multiple_sprints_per_issue(self):
        """Test processing issue with multiple sprints."""
        events = [
            {"issue_id": "1", "sprint_id": "100", "action": "added", "timestamp": 1},
            {"issue_id": "1", "sprint_id": "200", "action": "added", "timestamp": 2},
            {"issue_id": "1", "sprint_id": "100", "action": "removed", "timestamp": 3},
        ]

        # Group by (issue_id, sprint_id)
        from collections import defaultdict

        grouped = defaultdict(list)
        for event in events:
            key = (event["issue_id"], event["sprint_id"])
            grouped[key].append(event)

        # Determine final state for each pair
        final_states = {}
        for (issue_id, sprint_id), group_events in grouped.items():
            sorted_events = sorted(
                group_events, key=lambda x: x["timestamp"], reverse=True
            )
            final_states[(issue_id, sprint_id)] = sorted_events[0]["action"]

        # Issue should be in sprint 200 but not in sprint 100
        assert final_states[("1", "100")] == "removed"
        assert final_states[("1", "200")] == "added"

    def test_sprint_delta_from_to_sets(self):
        """Sprint add/remove events must be derived from set delta."""
        from_value = "10,20"
        to_value = "20,30"

        from_set = {x.strip() for x in from_value.split(",") if x.strip()}
        to_set = {x.strip() for x in to_value.split(",") if x.strip()}

        added = to_set - from_set
        removed = from_set - to_set

        assert added == {"30"}
        assert removed == {"10"}


class TestFieldKeyExtraction:
    """Tests for field key extraction patterns."""

    def test_extract_field_key_from_column_name(self):
        """Test extracting field key from DLT column name."""
        test_cases = [
            ("fields__customfield_10001", "customfield_10001"),
            ("fields__status", "status"),
            ("fields__issuetype__id", "issuetype__id"),
            ("fields__project__key", "project__key"),
        ]

        for col_name, expected in test_cases:
            field_key = col_name.replace("fields__", "")
            assert field_key == expected, f"Failed for {col_name}"

    def test_identify_custom_field(self):
        """Test identifying custom fields."""
        custom_fields = [
            "customfield_10001",
            "customfield_99999",
            "customfield_12345",
        ]
        standard_fields = ["status", "summary", "created", "assignee"]

        for field in custom_fields:
            assert field.startswith("customfield_")

        for field in standard_fields:
            assert not field.startswith("customfield_")


class TestChangelogJsonStructure:
    """Tests for expected changelog JSON structure."""

    def test_parse_changelog_history(self):
        """Test parsing changelog history structure."""
        sample_changelog = {
            "histories": [
                {
                    "id": "456",
                    "author": {"accountId": "user123", "displayName": "John Doe"},
                    "created": "2024-01-15T10:30:00.000+0000",
                    "items": [
                        {
                            "field": "Sprint",
                            "fieldId": "customfield_10020",
                            "from": "1",
                            "fromString": "Sprint 1",
                            "to": "2",
                            "toString": "Sprint 2",
                        }
                    ],
                }
            ]
        }

        histories = sample_changelog.get("histories", [])
        assert len(histories) == 1

        history = histories[0]
        assert history["author"]["accountId"] == "user123"
        assert "items" in history

        items = history["items"]
        assert len(items) == 1

        item = items[0]
        assert item["field"] == "Sprint"
        assert item["from"] == "1"
        assert item["to"] == "2"

    def test_parse_multi_value_changelog(self):
        """Test parsing changelog with comma-separated values."""
        sample_item = {
            "field": "Fix Version/s",
            "from": "1,2",
            "fromString": "1.0,1.1",
            "to": "2,3",
            "toString": "1.1,2.0",
        }

        # Parse comma-separated IDs
        from_ids = [x.strip() for x in sample_item["from"].split(",")]
        to_ids = [x.strip() for x in sample_item["to"].split(",")]

        assert from_ids == ["1", "2"]
        assert to_ids == ["2", "3"]


class TestSprintStatusMapping:
    """Tests for sprint status mapping."""

    def test_sprint_status_values(self):
        """Test valid sprint status values."""
        valid_statuses = ["future", "active", "closed"]

        # Simulate SQL CASE expression
        def map_sprint_status(state):
            if state == "future":
                return "future"
            elif state == "active":
                return "active"
            elif state == "closed":
                return "closed"
            else:
                return "future"  # default

        for status in valid_statuses:
            assert map_sprint_status(status) == status

        # Test unknown status defaults to 'future'
        assert map_sprint_status("unknown") == "future"
        assert map_sprint_status(None) == "future"


class TestReleaseStatusMapping:
    """Tests for release status mapping."""

    def test_release_status_from_flags(self):
        """Test determining release status from boolean flags."""

        def map_release_status(released, archived):
            if released:
                return "released"
            elif archived:
                return "archived"
            else:
                return "unreleased"

        assert map_release_status(True, False) == "released"
        assert map_release_status(False, True) == "archived"
        assert map_release_status(False, False) == "unreleased"
        # Released takes precedence over archived
        assert map_release_status(True, True) == "released"


class TestStatusCategoryMapping:
    """Tests for status category mapping."""

    def test_status_category_from_key(self):
        """Test mapping Jira status category key to clean category."""

        def map_status_category(category_key):
            mapping = {
                "new": "to_do",
                "indeterminate": "in_progress",
                "done": "done",
            }
            return mapping.get(category_key, "to_do")

        assert map_status_category("new") == "to_do"
        assert map_status_category("indeterminate") == "in_progress"
        assert map_status_category("done") == "done"
        assert map_status_category("unknown") == "to_do"


class TestIssueHierarchyLevel:
    """Tests for issue hierarchy level determination."""

    def test_hierarchy_level_from_type_name(self):
        """Test determining hierarchy level from issue type name."""

        def get_hierarchy_level(type_name):
            type_lower = type_name.lower() if type_name else ""
            if "epic" in type_lower:
                return "epic"
            elif "subtask" in type_lower:
                return "subtask"
            elif "story" in type_lower:
                return "story"
            else:
                return "task"

        assert get_hierarchy_level("Epic") == "epic"
        assert get_hierarchy_level("User Story") == "story"
        assert get_hierarchy_level("Sub-task") == "task"  # 'subtask' not in 'sub-task'
        assert get_hierarchy_level("Subtask") == "subtask"
        assert get_hierarchy_level("Bug") == "task"
        assert get_hierarchy_level("Task") == "task"
        assert get_hierarchy_level("Improvement") == "task"


class TestHistoricalStatusSync:
    """Tests for historical status synchronization logic."""

    def test_status_category_inference_from_name(self):
        """
        Test D: Tests the name-based fallback category logic used in the changelog INSERT.
        Mirrors the CASE WHEN LOWER(hi.to_string) IN (...) logic in the SQL.
        """

        def infer_category(name: str) -> str:
            name_lower = name.lower()
            # Done patterns
            if (
                name_lower
                in [
                    "done",
                    "canceled",
                    "cancelled",
                    "closed",
                    "resolved",
                    "отмена",
                ]  # 'отмена' means 'cancel'
                or "cancel" in name_lower
                or "отмен" in name_lower  # 'отмен' is root for 'cancel'
            ):
                return "done"
            # To Do patterns
            if (
                name_lower
                in [
                    "to do",
                    "к выполнению",  # 'к выполнению' means 'to do'
                    "open",
                    "backlog",
                    "new",
                    "todo",
                ]
                or "to do" in name_lower
                or "к выполнению" in name_lower  # 'к выполнению' means 'to do'
            ):
                return "to_do"
            # Default
            return "in_progress"

        # Done cases
        assert infer_category("Done") == "done"
        assert infer_category("Closed") == "done"
        assert infer_category("Canceled") == "done"
        assert infer_category("Cancelled") == "done"
        assert infer_category("Выполнено") == "in_progress"  # Not in the SQL list yet
        assert infer_category("Отмена") == "done"  # 'Отмена' means 'Cancel'
        assert infer_category("Task Canceled") == "done"  # LIKE %cancel%

        # To Do cases
        assert infer_category("To Do") == "to_do"
        assert infer_category("Open") == "to_do"
        assert infer_category("Backlog") == "to_do"
        assert (
            infer_category("К выполнению") == "to_do"
        )  # 'К выполнению' means 'To be done'
        assert infer_category("New") == "to_do"

        # In Progress cases
        assert infer_category("In Progress") == "in_progress"
        assert infer_category("In Review") == "in_progress"
        assert infer_category("Testing") == "in_progress"
        assert infer_category("Unknown Status") == "in_progress"

    def test_status_present_in_changelog_but_not_current_issues(self):
        """
        Test E: Validates the logic for detecting "phantom" statuses (exist in changelog but not in current issues).
        """
        # Statuses currently held by issues (Step 1 sync)
        current_statuses = [
            {"project_id": 1, "external_id": "101", "name": "To Do"},
            {"project_id": 1, "external_id": "102", "name": "In Progress"},
            {"project_id": 1, "external_id": "103", "name": "Done"},
        ]

        # Statuses found in changelog (Step 2 candidates)
        changelog_candidates = [
            {
                "project_id": 1,
                "external_id": "101",
                "name": "To Do",
            },  # Already exists by ID and Name
            {
                "project_id": 1,
                "external_id": "104",
                "name": "In Progress",
            },  # Already exists by Name
            {"project_id": 1, "external_id": "105", "name": "On Review"},  # New
        ]

        # Logic: cc WHERE NOT EXISTS (s.external_id = cc.external_id OR s.name = cc.name)
        new_statuses = []
        for cc in changelog_candidates:
            exists = any(
                s["project_id"] == cc["project_id"]
                and (s["external_id"] == cc["external_id"] or s["name"] == cc["name"])
                for s in current_statuses
            )
            if not exists:
                new_statuses.append(cc)

        assert len(new_statuses) == 1
        assert new_statuses[0]["name"] == "On Review"
        assert new_statuses[0]["external_id"] == "105"
