from datetime import datetime, timezone
from uuid import uuid4

from app.schemas.admin import (
    AdminLoginResponse,
    CalculationSettingUpsert,
    SchemaMapColumn,
    SchemaMapResponse,
    SchemaMapTable,
    ValidationIssue,
    ValidationResponse,
)


def test_admin_login_response_defaults_token_type():
    model = AdminLoginResponse(
        access_token="token",
        expires_at=datetime.now(timezone.utc),
        user_id=uuid4(),
        email="admin@example.com",
    )

    assert model.token_type == "bearer"


def test_calculation_setting_upsert_defaults():
    model = CalculationSettingUpsert(
        calc_code="ttm_days",
        settings_type="issue_type_filter",
    )

    assert model.settings_json == {}
    assert model.enabled is True


def test_schema_map_response_nested_models():
    response = SchemaMapResponse(
        tables=[
            SchemaMapTable(
                table_name="projects",
                columns=[SchemaMapColumn(column_name="id", data_type="uuid")],
            )
        ],
        relations=[],
    )

    assert response.tables[0].table_name == "projects"
    assert response.tables[0].columns[0].column_name == "id"


def test_validation_response_contains_issues():
    issue = ValidationIssue(
        project_id=uuid4(),
        project_key="KEY",
        severity="warning",
        code="missing_setting",
        details="details",
    )

    response = ValidationResponse(issues=[issue])

    assert response.issues[0].code == "missing_setting"
