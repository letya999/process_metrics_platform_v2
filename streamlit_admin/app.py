"""Streamlit Admin Studio for metrics configuration."""

from __future__ import annotations

import os
import time
from typing import Any
from urllib.parse import urlsplit

import pandas as pd
import streamlit as st

try:
    from streamlit_admin.client import AdminApiClient
    from streamlit_admin.components import (
        json_editor,
        save_bar,
        section_title,
        show_error,
        show_success,
    )
except ModuleNotFoundError:
    from client import AdminApiClient
    from components import (
        json_editor,
        save_bar,
        section_title,
        show_error,
        show_success,
    )

st.set_page_config(page_title="Metrics Admin Studio", layout="wide")


@st.cache_resource
def get_client() -> AdminApiClient:
    return AdminApiClient()


def _selectbox_index(options: list[Any], value: Any) -> int:
    try:
        return options.index(value)
    except ValueError:
        return 0


def _reset_form_state_on_edit_change(
    scope_key: str, edit_id: str | None, widget_keys: list[str]
) -> None:
    state_key = f"{scope_key}__last_edit_id"
    previous = st.session_state.get(state_key, "__unset__")
    if previous != edit_id:
        for key in widget_keys:
            st.session_state.pop(key, None)
    st.session_state[state_key] = edit_id


def _ensure_state() -> None:
    st.session_state.setdefault("token", None)
    st.session_state.setdefault("me", None)
    st.session_state.setdefault("jobs_active_run_id", None)
    st.session_state.setdefault("jobs_active_job_name", None)
    st.session_state.setdefault("jobs_history", [])
    st.session_state.setdefault("metrics_run_active", [])


def _login_view(client: AdminApiClient) -> None:
    st.title("Metrics Admin Studio")
    st.caption("Admin authentication required")

    with st.form("login"):
        email = st.text_input("Email")
        password = st.text_input("Password", type="password")
        submitted = st.form_submit_button("Login", type="primary")

    if submitted:
        try:
            data = client.request(
                "POST",
                "/admin/auth/login",
                json={"email": email, "password": password},
            )
            st.session_state.token = data["access_token"]
            st.session_state.me = client.request(
                "GET", "/admin/auth/me", token=st.session_state.token
            )
            st.rerun()
        except Exception as exc:
            show_error(exc)

    st.divider()

    # Google Login Button
    # Note: st.link_button is available in Streamlit 1.27+
    public_api_base_url = _resolve_public_api_base_url(client)
    redirect_url = f"{public_api_base_url}/admin/auth/google/redirect"
    if hasattr(st, "link_button"):
        st.link_button(
            "Sign in with Google",
            redirect_url,
            use_container_width=True,
        )
    else:
        # Fallback for older Streamlit versions
        if st.button("Sign in with Google", use_container_width=True):
            st.markdown(
                f'<meta http-equiv="refresh" content="0; url={redirect_url}">',
                unsafe_allow_html=True,
            )
            st.stop()


def _resolve_public_api_base_url(client: AdminApiClient) -> str:
    explicit = os.getenv("ADMIN_PUBLIC_API_URL", "").strip().rstrip("/")
    if explicit:
        return explicit

    callback_url = os.getenv("ADMIN_GOOGLE_REDIRECT_URI", "").strip()
    if callback_url:
        parsed = urlsplit(callback_url)
        if parsed.scheme and parsed.netloc:
            marker = "/admin/auth/google/callback"
            if parsed.path.endswith(marker):
                base_path = parsed.path[: -len(marker)].rstrip("/")
                return f"{parsed.scheme}://{parsed.netloc}{base_path}"
            return f"{parsed.scheme}://{parsed.netloc}/api/v1"

    return client.base_url


def _logout(client: AdminApiClient) -> None:
    try:
        if st.session_state.token:
            client.request("POST", "/admin/auth/logout", token=st.session_state.token)
    except Exception:  # noqa: BLE001,S110 - best-effort logout
        pass  # noqa: S110
    st.session_state.token = None
    st.session_state.me = None
    st.rerun()


def _tab_validate(client: AdminApiClient, token: str, project_id: str | None) -> None:
    section_title("Validation")
    if st.button("Run validation", type="primary"):
        try:
            params = {"project_id": project_id} if project_id else None
            res = client.request("POST", "/admin/validate", token=token, params=params)
            st.dataframe(res["issues"], use_container_width=True, hide_index=True)
            show_success(f"Validation completed. Issues: {len(res['issues'])}")
        except Exception as exc:
            show_error(exc)


def _format_duration(seconds: float | None) -> str:
    if seconds is None:
        return "-"
    total = int(round(seconds))
    minutes, sec = divmod(total, 60)
    hours, minutes = divmod(minutes, 60)
    if hours:
        return f"{hours}h {minutes}m {sec}s"
    if minutes:
        return f"{minutes}m {sec}s"
    return f"{sec}s"


def _tab_jobs(client: AdminApiClient, token: str) -> None:
    section_title(
        "Orchestration",
        "Run Dagster jobs from admin studio and monitor progress.",
    )
    try:
        jobs = client.request("GET", "/admin/jobs", token=token)
    except Exception as exc:
        show_error(exc)
        return

    if not jobs:
        st.info("No jobs available.")
        return

    cols = st.columns(min(4, len(jobs)))
    for idx, job in enumerate(jobs):
        with cols[idx % len(cols)]:
            if st.button(f"Run {job['job_name']}", key=f"run_job_{job['job_name']}"):
                try:
                    launch = client.request(
                        "POST",
                        "/admin/jobs/launch",
                        token=token,
                        json={"job_name": job["job_name"]},
                    )
                    st.session_state["jobs_active_run_id"] = launch["run_id"]
                    st.session_state["jobs_active_job_name"] = job["job_name"]
                    history = st.session_state.get("jobs_history") or []
                    history.insert(
                        0,
                        {
                            "job_name": job["job_name"],
                            "run_id": launch["run_id"],
                            "status": launch["status"],
                            "duration": None,
                            "progress_pct": 0.0,
                            "errors": 0,
                        },
                    )
                    st.session_state["jobs_history"] = history[:20]
                    show_success(
                        f"Job started: {job['job_name']} (run: {launch['run_id']})"
                    )
                except Exception as exc:
                    show_error(exc)

    st.divider()
    c1, c2 = st.columns([1, 4])
    with c1:
        auto_poll = st.toggle("Auto refresh", value=True, key="jobs_auto_refresh")
    with c2:
        st.caption("Polling interval: 3 seconds while run is active.")
    st.button("Refresh now", key="jobs_refresh_now")

    run_id = st.session_state.get("jobs_active_run_id")
    if not run_id:
        st.info("No active run. Start a job above.")
        return

    try:
        details = client.request("GET", f"/admin/jobs/runs/{run_id}", token=token)
    except Exception as exc:
        show_error(exc)
        return

    status = (details.get("status") or "UNKNOWN").upper()
    st.markdown(
        f"**Active run:** `{run_id}`  |  **Job:** `{st.session_state.get('jobs_active_job_name') or '-'}`"
    )
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Status", status, border=True)
    m2.metric("Progress", f"{details.get('progress_pct', 0)}%", border=True)
    m3.metric(
        "Steps",
        f"{details.get('completed_steps', 0)}/{details.get('total_steps', 0)}",
        border=True,
    )
    m4.metric(
        "Duration",
        _format_duration(details.get("duration_seconds")),
        border=True,
    )

    progress_pct = float(details.get("progress_pct", 0.0))
    st.progress(max(0.0, min(1.0, progress_pct / 100)))

    step_rows = details.get("steps") or []
    if step_rows:
        st.markdown("#### Step Status")
        st.dataframe(pd.DataFrame(step_rows), use_container_width=True, hide_index=True)

    errors = details.get("errors") or []
    if errors:
        st.markdown("#### Recent Errors")
        st.dataframe(pd.DataFrame(errors), use_container_width=True, hide_index=True)

    history = st.session_state.get("jobs_history") or []
    for row in history:
        if row.get("run_id") == run_id:
            row["status"] = status
            row["duration"] = details.get("duration_seconds")
            row["progress_pct"] = details.get("progress_pct")
            row["errors"] = len(errors)
            break
    st.session_state["jobs_history"] = history

    terminal = status in {"SUCCESS", "FAILURE", "CANCELED", "CANCELING"}
    if terminal:
        if status == "SUCCESS":
            show_success("Run finished successfully.")
        elif status == "FAILURE":
            st.error("Run failed.")
    elif auto_poll:
        time.sleep(3)
        st.rerun()

    if history:
        st.markdown("#### Recent Runs")
        history_df = pd.DataFrame(history)
        if "duration" in history_df.columns:
            history_df["duration"] = history_df["duration"].apply(_format_duration)
        st.dataframe(history_df, use_container_width=True, hide_index=True)


def _build_project_settings_matrix(
    projects: list[dict[str, Any]],
    contracts: list[dict[str, Any]],
    project_settings: dict[str, list[dict[str, Any]]],
    project_commitment_rules: dict[str, list[dict[str, Any]]],
    project_units: dict[str, list[dict[str, Any]]],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for project in projects:
        pid = project["project_id"]
        pkey = project["project_key"]
        settings = project_settings.get(pid, [])
        rules = project_commitment_rules.get(pid, [])
        units = project_units.get(pid, [])

        settings_by_calc: dict[str, list[str]] = {}
        for s in settings:
            if s.get("enabled"):
                settings_by_calc.setdefault(s["calc_code"], []).append(
                    s["settings_type"]
                )

        commitment_by_calc: dict[str, int] = {}
        for r in rules:
            commitment_by_calc[r["calc_code"]] = (
                commitment_by_calc.get(r["calc_code"], 0) + 1
            )

        unit_bindings = {
            f"{u['unit_code']}:{u.get('source_field_id')}"
            for u in units
            if u.get("source_field_id")
        }

        for c in contracts:
            configured_settings = sorted(settings_by_calc.get(c["calc_code"], []))
            required_settings = sorted(c.get("required_settings_types", []))
            missing = sorted(set(required_settings) - set(configured_settings))
            needs_commitment = c["requires_commitment"] == "required"
            has_commitment = commitment_by_calc.get(c["calc_code"], 0) > 0
            needs_unit = c["requires_unit_binding"] == "required"
            has_unit_binding = any(
                x.startswith(f"{c['unit_code']}:") for x in unit_bindings
            )
            is_ok = (
                (not needs_commitment or has_commitment)
                and (not needs_unit or has_unit_binding)
                and not missing
            )
            status_label = "OK" if is_ok else "ISSUE"
            missing_parts: list[str] = []
            if needs_commitment and not has_commitment:
                missing_parts.append("commitment_rule")
            if needs_unit and not has_unit_binding:
                missing_parts.append("unit_binding")
            if missing:
                missing_parts.append(f"settings({', '.join(missing)})")

            rows.append(
                {
                    "status": status_label,
                    "project_key": pkey,
                    "project_id": pid,
                    "metric_code": c["metric_code"],
                    "calc_code": c["calc_code"],
                    "unit_code": c["unit_code"],
                    "needs_commitment_rule": needs_commitment,
                    "has_commitment_rule": has_commitment,
                    "required_settings_types": ", ".join(required_settings),
                    "configured_settings_types": ", ".join(configured_settings),
                    "missing_settings_types": ", ".join(missing),
                    "needs_unit_binding": needs_unit,
                    "has_unit_binding": has_unit_binding,
                    "missing_summary": ", ".join(missing_parts),
                }
            )
    return rows


def _project_filter(
    projects: list[dict[str, Any]], key: str, label: str = "Project Filter"
) -> str | None:
    """Render a project selection filter."""
    options = {"All": None}
    for p in projects:
        options[f"{p['project_key']} - {p['project_name']}"] = p["project_id"]
    selected = st.selectbox(
        label,
        list(options.keys()),
        key=key,
        help="Filter data by project.",
    )
    return options[selected]


def _calc_filter(
    calc_codes: list[str], key: str, label: str = "Calculation Filter"
) -> str | None:
    """Render a calculation selection filter."""
    options = ["All"] + sorted(calc_codes)
    selected = st.selectbox(
        label,
        options,
        key=key,
        help="Filter data by calc_code.",
    )
    return None if selected == "All" else selected


def _tab_metrics_catalog(client: AdminApiClient, token: str) -> None:
    """Render the Metrics Catalog tab, showing project configurations."""
    section_title(
        "Metrics Catalog",
        "Which metrics are configured by project, and what is missing.",
    )
    try:
        projects = client.request("GET", "/admin/catalog/projects", token=token)
        contracts = client.request("GET", "/admin/contracts/catalog", token=token)

        all_settings = client.request("GET", "/admin/calculation-settings", token=token)
        all_commitment_rules = client.request(
            "GET", "/admin/commitment-rules", token=token
        )
        all_units = client.request("GET", "/admin/units", token=token)

        project_settings = {}
        project_commitment_rules = {}
        project_units = {}
        for project in projects:
            pid = project["project_id"]
            project_settings[pid] = [
                s
                for s in all_settings
                if s.get("project_id") == pid or s.get("project_id") is None
            ]
            project_commitment_rules[pid] = [
                r
                for r in all_commitment_rules
                if r.get("project_id") == pid or r.get("project_id") is None
            ]
            project_units[pid] = [
                u
                for u in all_units
                if u.get("project_id") == pid or u.get("project_id") is None
            ]

        rows = _build_project_settings_matrix(
            projects,
            contracts,
            project_settings,
            project_commitment_rules,
            project_units,
        )
        if not rows:
            st.info("No metrics found.")
            return
        df = pd.DataFrame(rows)
        df["matrix_status"] = df.apply(
            lambda row: (
                "OK"
                if row["status"] == "OK"
                else f"ISSUE: {row['missing_summary'] or 'configuration incomplete'}"
            ),
            axis=1,
        )
        matrix = df.pivot_table(
            index="calc_code",
            columns="project_key",
            values="matrix_status",
            aggfunc="first",
            fill_value="N/A",
        ).sort_index()
        st.dataframe(matrix, use_container_width=True)

        details = df[
            [
                "status",
                "project_key",
                "metric_code",
                "calc_code",
                "unit_code",
                "missing_summary",
            ]
        ].copy()

        def _mark(row: pd.Series) -> list[str]:
            if row["status"] == "ISSUE":
                return [
                    "background-color: #ff4d4f; color: #000000; font-weight: 700"
                ] * len(row)
            return ["background-color: #ffffff; color: #000000"] * len(row)

        st.markdown("#### Missing/Problem rows")
        st.dataframe(
            details.style.apply(_mark, axis=1),
            use_container_width=True,
            hide_index=True,
        )
    except Exception as exc:
        show_error(exc)


def _tab_commitment_v2(client: AdminApiClient, token: str) -> None:
    section_title("Commitment Rules")
    try:
        projects = client.request("GET", "/admin/catalog/projects", token=token)
        contracts = client.request("GET", "/admin/contracts/catalog", token=token)
        required_calcs = sorted(
            {
                c["calc_code"]
                for c in contracts
                if c["requires_commitment"] == "required"
            }
        )
        all_rules = client.request("GET", "/admin/commitment-rules", token=token)
    except Exception as exc:
        show_error(exc)
        return

    f1, f2 = st.columns(2)
    with f1:
        project_filter = _project_filter(projects, "commitment_project_filter")
    with f2:
        calc_filter = _calc_filter(required_calcs, "commitment_calc_filter")

    filtered_rules = [
        r
        for r in all_rules
        if (
            project_filter is None
            or r.get("project_id") == project_filter
            or r.get("project_id") is None
        )
        and (calc_filter is None or r.get("calc_code") == calc_filter)
    ]
    project_key_by_id = {p["project_id"]: p["project_key"] for p in projects}
    display_rules = [
        {
            "scope": (
                "Global (all projects)"
                if r.get("project_id") is None
                else project_key_by_id.get(
                    r.get("project_id"), str(r.get("project_id"))
                )
            ),
            "calc_code": r.get("calc_code"),
            "board_id": r.get("board_id"),
            "start_column_name_snapshot": r.get("start_column_name_snapshot"),
            "end_column_name_snapshot": r.get("end_column_name_snapshot"),
            "id": r.get("id"),
        }
        for r in filtered_rules
    ]
    with st.expander("Current Commitment Rules", expanded=True):
        st.caption(
            "'Global (all projects)' rules apply to every project unless overridden by a project-specific rule."
        )
        st.dataframe(display_rules, use_container_width=True, hide_index=True)

    missing_rows: list[dict[str, Any]] = []
    rules_set = {(r.get("project_id"), r.get("calc_code")) for r in all_rules}
    for p in projects:
        for calc in required_calcs:
            if (p["project_id"], calc) not in rules_set and (
                None,
                calc,
            ) not in rules_set:
                missing_rows.append(
                    {
                        "project_id": p["project_id"],
                        "project_key": p["project_key"],
                        "calc_code": calc,
                        "missing": "commitment_rule",
                    }
                )
    missing_rows = [
        r
        for r in missing_rows
        if (project_filter is None or r["project_id"] == project_filter)
        and (calc_filter is None or r["calc_code"] == calc_filter)
    ]
    with st.expander("Missing required Commitment Rules", expanded=True):
        if not missing_rows:
            st.success("✓ All required commitment rules are configured")
        else:
            st.dataframe(missing_rows, use_container_width=True, hide_index=True)

    st.markdown("#### Create / Edit Commitment Rule")
    edit_candidates = [r for r in filtered_rules if r.get("id")]
    edit_options = {"Create new": None}
    for r in edit_candidates:
        edit_options[f"{r['id']} | {r['calc_code']} | {r.get('project_id')}"] = r["id"]
    selected_edit = st.selectbox(
        "Rule to edit",
        list(edit_options.keys()),
        key="commitment_edit_rule",
        help="Select an existing record to update, or leave as 'Create new'.",
    )
    edit_id = edit_options[selected_edit]
    edit_row = next((r for r in all_rules if r.get("id") == edit_id), None)
    _reset_form_state_on_edit_change(
        "commitment_form",
        str(edit_id) if edit_id is not None else None,
        [
            "commitment_project_input",
            "commitment_board_source_project_input",
            "commitment_board_input",
            "commitment_start_input",
            "commitment_end_input",
            "commitment_calc_input_single",
            "commitment_calc_input_multi",
        ],
    )
    project_map = {"All (NULL)": None}
    for p in projects:
        project_map[f"{p['project_key']} - {p['project_name']}"] = p["project_id"]
    project_labels = list(project_map.keys())
    default_project_id = edit_row.get("project_id") if edit_row else None
    default_project_label = next(
        (label for label, pid in project_map.items() if pid == default_project_id),
        project_labels[0],
    )
    selected_project = st.selectbox(
        "Project",
        project_labels,
        index=_selectbox_index(project_labels, default_project_label),
        key="commitment_project_input",
        help="Rule project. 'All (NULL)' will create a global rule with project_id = NULL.",
    )
    project_id = project_map[selected_project]

    board_project_id = project_id
    if project_id is None:
        source_project_map = {
            f"{p['project_key']} - {p['project_name']}": p["project_id"]
            for p in projects
        }
        if not source_project_map:
            st.info(
                "No projects imported yet. Import projects first in Integrations tab."
            )
            return
        source_project_labels = list(source_project_map.keys())
        source_project_label = st.selectbox(
            "Board Source Project",
            source_project_labels,
            index=0,
            key="commitment_board_source_project_input",
            help="Project to fetch board/columns from for the global (NULL) rule.",
        )
        if source_project_label is None:
            st.info("Select a project to fetch board/column catalog.")
            return
        board_project_id = source_project_map[source_project_label]

    try:
        boards = client.request(
            "GET",
            "/admin/catalog/boards",
            token=token,
            params={"project_id": board_project_id},
        )
    except Exception as exc:
        show_error(exc)
        return
    if not boards:
        st.info("No boards for selected project.")
        return
    board_map = {f"{b['board_name']} ({b['board_id']})": b["board_id"] for b in boards}
    board_labels = list(board_map.keys())
    default_board_id = edit_row.get("board_id") if edit_row else None
    default_board_label = next(
        (label for label, bid in board_map.items() if bid == default_board_id),
        board_labels[0],
    )
    board_label = st.selectbox(
        "Board",
        board_labels,
        index=_selectbox_index(board_labels, default_board_label),
        key="commitment_board_input",
    )
    board_id = board_map[board_label]
    try:
        columns = client.request(
            "GET",
            "/admin/catalog/board-columns",
            token=token,
            params={"board_id": board_id},
        )
    except Exception as exc:
        show_error(exc)
        return
    column_map = {
        f"{c['column_name']} ({c['column_id']})": c["column_id"] for c in columns
    }
    column_labels = list(column_map.keys())
    default_start_id = edit_row.get("start_column_id") if edit_row else None
    default_end_id = edit_row.get("end_column_id") if edit_row else None
    default_start_label = next(
        (label for label, cid in column_map.items() if cid == default_start_id),
        column_labels[0],
    )
    default_end_label = next(
        (label for label, cid in column_map.items() if cid == default_end_id),
        column_labels[0],
    )
    c1, c2, c3 = st.columns(3)
    with c1:
        start_label = st.selectbox(
            "Commitment Start",
            column_labels,
            index=_selectbox_index(column_labels, default_start_label),
            key="commitment_start_input",
        )
    with c2:
        end_label = st.selectbox(
            "Commitment End",
            column_labels,
            index=_selectbox_index(column_labels, default_end_label),
            key="commitment_end_input",
        )
    with c3:
        calc_code: str | None = None
        calc_codes_multi: list[str] = []
        if edit_id is not None:
            calc_code = st.selectbox(
                "Metric Calculation",
                required_calcs,
                index=_selectbox_index(
                    required_calcs,
                    edit_row.get("calc_code") if edit_row else required_calcs[0],
                ),
                key="commitment_calc_input_single",
                help="Only one metric can be selected for editing a single record.",
            )
        else:
            calc_codes_multi = st.multiselect(
                "Metric Calculations",
                required_calcs,
                default=[],
                key="commitment_calc_input_multi",
                help="You can select multiple metrics and create rules for all of them at once.",
            )
    if save_bar("Save Commitment Rule"):
        try:
            existing_key_to_id = {
                (r.get("project_id"), r.get("board_id"), r.get("calc_code")): r.get(
                    "id"
                )
                for r in all_rules
            }
            if edit_id is not None:
                update_key = (project_id, board_id, calc_code)
                existing_id = existing_key_to_id.get(update_key)
                if existing_id and existing_id != edit_id:
                    st.warning(
                        "Rule with the same Project + Board + Metric already exists. "
                        "Select that rule in edit mode instead of creating/updating a duplicate."
                    )
                    return
                payloads = [
                    {
                        "id": edit_id,
                        "project_id": project_id,
                        "board_id": board_id,
                        "calc_code": calc_code,
                        "start_column_id": column_map[start_label],
                        "end_column_id": column_map[end_label],
                    }
                ]
            else:
                if not calc_codes_multi:
                    st.warning("Select at least one metric calculation.")
                    return
                skipped_duplicates: list[str] = []
                payloads: list[dict[str, Any]] = []
                for code in calc_codes_multi:
                    key = (project_id, board_id, code)
                    if key in existing_key_to_id:
                        skipped_duplicates.append(code)
                        continue
                    payloads.append(
                        {
                            "id": None,
                            "project_id": project_id,
                            "board_id": board_id,
                            "calc_code": code,
                            "start_column_id": column_map[start_label],
                            "end_column_id": column_map[end_label],
                        }
                    )
                if skipped_duplicates:
                    st.info(
                        "Skipped existing rules (already in DB): "
                        + ", ".join(sorted(skipped_duplicates))
                    )
                if not payloads:
                    st.warning(
                        "Nothing to save: all selected metrics already have rules for this project + board."
                    )
                    return
            for payload in payloads:
                client.request(
                    "POST", "/admin/commitment-rules", token=token, json=payload
                )
            show_success("Commitment rule saved")
            st.rerun()
        except Exception as exc:
            show_error(exc)

    st.markdown("#### Delete Commitment Rule")
    del_rules = [r for r in all_rules if r.get("id")]
    del_options: dict[str, Any] = {"-- select to delete --": None}
    for r in del_rules:
        scope = (
            "Global"
            if r.get("project_id") is None
            else project_key_by_id.get(r.get("project_id"), str(r.get("project_id")))
        )
        del_options[f"{scope} | {r['calc_code']} | {r['id']}"] = r["id"]
    del_select = st.selectbox(
        "Rule to delete", list(del_options.keys()), key="commitment_del_select"
    )
    del_id = del_options[del_select]
    if del_id and st.button("Delete", type="secondary", key="commitment_del_btn"):
        try:
            client.request("DELETE", f"/admin/commitment-rules/{del_id}", token=token)
            show_success("Commitment rule deleted")
            st.rerun()
        except Exception as exc:
            show_error(exc)


def _render_settings_json_editor(
    settings_type: str,
    edit_row: dict[str, Any] | None,
    statuses: list[dict[str, Any]],
    issue_types: list[dict[str, Any]],
    field_keys: list[dict[str, Any]],
) -> Any:
    """Render a structured editor for settings_json based on settings_type.

    Returns the settings_json dict to save.
    """
    existing = edit_row.get("settings_json") if edit_row else None
    if existing is None:
        existing = {}

    if settings_type == "flow_status_categories":
        categories = sorted({s["category"] for s in statuses if s.get("category")})
        if not categories:
            categories = ["Done", "In Progress", "To Do"]
        st.caption(
            "Map Jira status categories to flow phases. Statuses not mapped are excluded from flow calculations."
        )
        active_default = [
            c
            for c in existing.get("active_categories", ["In Progress"])
            if c in categories
        ]
        passive_default = [
            c for c in existing.get("passive_categories", ["To Do"]) if c in categories
        ]
        done_default = [
            c for c in existing.get("done_categories", ["Done"]) if c in categories
        ]
        c1, c2, c3 = st.columns(3)
        with c1:
            active = st.multiselect(
                "Active (in-progress)",
                categories,
                default=active_default,
                key="sjson_active",
            )
        with c2:
            passive = st.multiselect(
                "Wait / Passive",
                categories,
                default=passive_default,
                key="sjson_passive",
            )
        with c3:
            done = st.multiselect(
                "Done", categories, default=done_default, key="sjson_done"
            )
        return {
            "active_categories": active,
            "passive_categories": passive,
            "done_categories": done,
        }

    if settings_type == "issue_type_filter":
        type_names = sorted(
            {t["issue_type_name"] for t in issue_types if t.get("issue_type_name")}
        )
        st.caption("Include only these issue types in TTM calculations.")
        default = [t for t in existing.get("include", ["Epic"]) if t in type_names]
        include = st.multiselect(
            "Include issue types",
            type_names,
            default=default,
            key="sjson_include_types",
        )
        return {"include": include}

    if settings_type == "defect_density_types":
        type_names = sorted(
            {t["issue_type_name"] for t in issue_types if t.get("issue_type_name")}
        )
        st.caption(
            "Select numerator (defect) and denominator (total) issue types for defect density."
        )
        num_default = existing.get(
            "numerator_type", type_names[0] if type_names else ""
        )
        den_default = existing.get(
            "denominator_type", type_names[0] if type_names else ""
        )
        c1, c2 = st.columns(2)
        with c1:
            num_type = st.selectbox(
                "Numerator type (defects)",
                type_names,
                index=_selectbox_index(type_names, num_default),
                key="sjson_num_type",
            )
        with c2:
            den_type = st.selectbox(
                "Denominator type (total)",
                type_names,
                index=_selectbox_index(type_names, den_default),
                key="sjson_den_type",
            )
        return {"numerator_type": num_type, "denominator_type": den_type}

    if settings_type == "target_status":
        status_map = {
            s["status_name"]: str(s["status_id"])
            for s in statuses
            if s.get("status_name")
        }
        st.caption("Status whose daily entry count is tracked.")
        existing_id = existing.get("target_status", "")
        id_to_name = {v: k for k, v in status_map.items()}
        default_name = id_to_name.get(
            existing_id, list(status_map.keys())[0] if status_map else ""
        )
        status_labels = list(status_map.keys())
        sel = st.selectbox(
            "Target Status",
            status_labels,
            index=_selectbox_index(status_labels, default_name),
            key="sjson_target_status",
        )
        return {"target_status": status_map[sel] if sel else ""}

    if settings_type == "field_key_id":
        fk_map = {
            f"{f['external_key']} - {f['name']}": str(f["field_key_id"])
            for f in field_keys
            if f.get("field_key_id")
        }
        st.caption("Field key whose change count is tracked per sprint.")
        existing_fk = existing.get("field_key_id", "")
        fk_id_to_label = {v: k for k, v in fk_map.items()}
        default_label = fk_id_to_label.get(
            existing_fk, list(fk_map.keys())[0] if fk_map else ""
        )
        fk_labels = list(fk_map.keys())
        sel_fk = st.selectbox(
            "Field Key",
            fk_labels,
            index=_selectbox_index(fk_labels, default_label),
            key="sjson_field_key",
        )
        return {"field_key_id": fk_map[sel_fk] if sel_fk else ""}

    if settings_type == "cancelled_status_ids":
        status_map = {
            s["status_name"]: str(s["status_id"])
            for s in statuses
            if s.get("status_name")
        }
        id_to_name = {v: k for k, v in status_map.items()}
        st.caption("Statuses that count as cancelled/rejected issues.")
        existing_ids = existing.get("cancelled_status_ids", [])
        default_names = [id_to_name[sid] for sid in existing_ids if sid in id_to_name]
        selected = st.multiselect(
            "Cancelled Statuses",
            list(status_map.keys()),
            default=default_names,
            key="sjson_cancelled",
        )
        return {"cancelled_status_ids": [status_map[s] for s in selected]}

    # fallback: raw JSON editor for unknown / field_value_match
    st.caption("Raw JSON configuration.")
    return json_editor("settings_json_editor_v2", existing)


def _tab_settings_v2(client: AdminApiClient, token: str) -> None:
    section_title("Calculation Settings")
    try:
        projects = client.request("GET", "/admin/catalog/projects", token=token)
        contracts = client.request("GET", "/admin/contracts/catalog", token=token)
        all_settings = client.request("GET", "/admin/calculation-settings", token=token)
    except Exception as exc:
        show_error(exc)
        return
    calc_codes = sorted({c["calc_code"] for c in contracts})
    req_by_calc = {
        c["calc_code"]: c.get("required_settings_types", []) for c in contracts
    }
    f1, f2 = st.columns(2)
    with f1:
        project_filter = _project_filter(projects, "settings_project_filter")
    with f2:
        calc_filter = _calc_filter(calc_codes, "settings_calc_filter")

    filtered = [
        s
        for s in all_settings
        if (
            project_filter is None
            or s.get("project_id") == project_filter
            or s.get("project_id") is None
        )
        and (calc_filter is None or s.get("calc_code") == calc_filter)
    ]
    project_key_by_id = {p["project_id"]: p["project_key"] for p in projects}
    display_settings = [
        {
            "scope": (
                "Global (all projects)"
                if s.get("project_id") is None
                else project_key_by_id.get(
                    s.get("project_id"), str(s.get("project_id"))
                )
            ),
            "calc_code": s.get("calc_code"),
            "settings_type": s.get("settings_type"),
            "enabled": s.get("enabled"),
            "settings_json": s.get("settings_json"),
            "id": s.get("id"),
        }
        for s in filtered
    ]
    with st.expander("Current Calculation Settings", expanded=True):
        st.caption(
            "'Global (all projects)' settings apply to every project unless overridden by a project-specific setting."
        )
        st.dataframe(display_settings, use_container_width=True, hide_index=True)

    enabled_set = {
        (s.get("project_id"), s.get("calc_code"), s.get("settings_type"))
        for s in all_settings
        if s.get("enabled")
    }
    missing_rows: list[dict[str, Any]] = []
    for p in projects:
        for calc, reqs in req_by_calc.items():
            for st_type in reqs:
                if (p["project_id"], calc, st_type) not in enabled_set and (
                    None,
                    calc,
                    st_type,
                ) not in enabled_set:
                    missing_rows.append(
                        {
                            "project_id": p["project_id"],
                            "project_key": p["project_key"],
                            "calc_code": calc,
                            "settings_type": st_type,
                        }
                    )
    missing_rows = [
        r
        for r in missing_rows
        if (project_filter is None or r["project_id"] == project_filter)
        and (calc_filter is None or r["calc_code"] == calc_filter)
    ]
    with st.expander("Missing required Calculation Settings", expanded=True):
        if not missing_rows:
            st.success("✓ All required calculation settings are configured")
        else:
            st.dataframe(missing_rows, use_container_width=True, hide_index=True)

    st.markdown("#### Create / Edit Calculation Setting")
    edit_options: dict[str, Any] = {"Create new": None}
    for s in all_settings:
        scope = (
            "Global"
            if s.get("project_id") is None
            else project_key_by_id.get(s.get("project_id"), str(s.get("project_id")))
        )
        edit_options[
            f"{scope} | {s['calc_code']} | {s['settings_type']} | {s['id']}"
        ] = s["id"]
    selected_edit = st.selectbox(
        "Setting to edit", list(edit_options.keys()), key="settings_edit_id"
    )
    edit_id = edit_options[selected_edit]
    edit_row = next((s for s in all_settings if s.get("id") == edit_id), None)
    _reset_form_state_on_edit_change(
        "settings_form",
        str(edit_id) if edit_id is not None else None,
        [
            "settings_project_input",
            "settings_source_project_input",
            "settings_calc_input",
            "settings_type_select",
            "settings_enabled_input",
            "sjson_active",
            "sjson_passive",
            "sjson_done",
            "sjson_include_types",
            "sjson_num_type",
            "sjson_den_type",
            "sjson_target_status",
            "sjson_field_key",
            "sjson_cancelled",
            "settings_json_editor_v2",
        ],
    )
    project_map: dict[str, Any] = {"All (NULL)": None}
    for p in projects:
        project_map[f"{p['project_key']} - {p['project_name']}"] = p["project_id"]
    project_labels = list(project_map.keys())
    default_project_id = edit_row.get("project_id") if edit_row else None
    default_project_label = next(
        (label for label, pid in project_map.items() if pid == default_project_id),
        project_labels[0],
    )
    project_label = st.selectbox(
        "Project",
        project_labels,
        index=_selectbox_index(project_labels, default_project_label),
        key="settings_project_input",
        help="'All (NULL)' creates a global setting that applies to all projects.",
    )
    project_id = project_map[project_label]

    # For catalog lookups (statuses, issue types, field keys), we need a concrete project_id.
    catalog_project_id = project_id
    if project_id is None:
        source_project_map = {
            f"{p['project_key']} - {p['project_name']}": p["project_id"]
            for p in projects
        }
        if not source_project_map:
            st.info(
                "No projects imported yet. Import projects first in Integrations tab."
            )
            return
        source_project_label = st.selectbox(
            "Catalog Source Project",
            list(source_project_map.keys()),
            key="settings_source_project_input",
            help="Project used to fetch status/issue-type/field-key options for this global setting.",
        )
        if source_project_label is None:
            st.info("Select a project to load catalog options.")
            return
        catalog_project_id = source_project_map[source_project_label]

    default_calc_code = edit_row.get("calc_code") if edit_row else calc_codes[0]
    calc_code = st.selectbox(
        "Metric Calculation",
        calc_codes,
        index=_selectbox_index(calc_codes, default_calc_code),
        key="settings_calc_input",
    )
    suggestions = req_by_calc.get(calc_code, []) + ["custom"]
    default_settings_type = edit_row.get("settings_type") if edit_row else None
    default_selected_type = (
        default_settings_type if default_settings_type in suggestions else "custom"
    )
    selected_type = st.selectbox(
        "Settings Type",
        suggestions,
        index=_selectbox_index(suggestions, default_selected_type),
        key="settings_type_select",
    )
    settings_type = (
        selected_type if selected_type != "custom" else (default_settings_type or "")
    )
    if selected_type == "custom":
        settings_type = st.text_input(
            "Settings Type (manual)",
            value=default_settings_type or "",
            key="settings_type_custom_input",
        )

    enabled = st.checkbox(
        "Enabled",
        value=bool(edit_row.get("enabled")) if edit_row else True,
        key="settings_enabled_input",
    )

    # Fetch catalog data for structured editor
    statuses: list[dict[str, Any]] = []
    issue_types_cat: list[dict[str, Any]] = []
    field_keys_cat: list[dict[str, Any]] = []
    if catalog_project_id:
        try:
            statuses = client.request(
                "GET",
                "/admin/catalog/statuses",
                token=token,
                params={"project_id": catalog_project_id},
            )
        except Exception:  # noqa: S110
            pass
        try:
            issue_types_cat = client.request(
                "GET",
                "/admin/catalog/issue-types",
                token=token,
                params={"project_id": catalog_project_id},
            )
        except Exception:  # noqa: S110
            pass
        try:
            field_keys_cat = client.request(
                "GET",
                "/admin/catalog/field-keys",
                token=token,
                params={"project_id": catalog_project_id},
            )
        except Exception:  # noqa: S110
            pass

    settings_json = _render_settings_json_editor(
        settings_type, edit_row, statuses, issue_types_cat, field_keys_cat
    )

    if save_bar("Save Setting"):
        try:
            payload = {
                "id": edit_id,
                "project_id": project_id,
                "calc_code": calc_code,
                "settings_type": settings_type,
                "settings_json": settings_json,
                "enabled": enabled,
            }
            client.request(
                "POST", "/admin/calculation-settings", token=token, json=payload
            )
            show_success("Calculation setting saved")
            st.rerun()
        except Exception as exc:
            show_error(exc)

    st.markdown("#### Delete Calculation Setting")
    del_options: dict[str, Any] = {"-- select to delete --": None}
    for s in all_settings:
        scope = (
            "Global"
            if s.get("project_id") is None
            else project_key_by_id.get(s.get("project_id"), str(s.get("project_id")))
        )
        del_options[
            f"{scope} | {s['calc_code']} | {s['settings_type']} | {s['id']}"
        ] = s["id"]
    del_select = st.selectbox(
        "Setting to delete", list(del_options.keys()), key="settings_del_select"
    )
    del_id = del_options[del_select]
    if del_id and st.button("Delete", type="secondary", key="settings_del_btn"):
        try:
            client.request(
                "DELETE", f"/admin/calculation-settings/{del_id}", token=token
            )
            show_success("Calculation setting deleted")
            st.rerun()
        except Exception as exc:
            show_error(exc)


def _tab_units_v2(client: AdminApiClient, token: str) -> None:
    section_title("Units")
    try:
        projects = client.request("GET", "/admin/catalog/projects", token=token)
        contracts = client.request("GET", "/admin/contracts/catalog", token=token)
        all_units = client.request("GET", "/admin/units", token=token)
    except Exception as exc:
        show_error(exc)
        return
    required_contracts = [
        c for c in contracts if c["requires_unit_binding"] == "required"
    ]
    calc_codes = sorted({c["calc_code"] for c in required_contracts})
    calc_to_unit = {c["calc_code"]: c["unit_code"] for c in contracts}
    f1, f2 = st.columns(2)
    with f1:
        project_filter = _project_filter(projects, "units_project_filter")
    with f2:
        calc_filter = _calc_filter(calc_codes, "units_calc_filter")
    filtered = [
        u
        for u in all_units
        if project_filter is None
        or u.get("project_id") == project_filter
        or u.get("project_id") is None
    ]
    if calc_filter:
        filtered = [
            u for u in filtered if u.get("unit_code") == calc_to_unit.get(calc_filter)
        ]
    # --- Display: Current Unit Bindings ---
    project_key_by_id = {p["project_id"]: p["project_key"] for p in projects}
    display_units = [
        {
            "scope": (
                "Global (all projects)"
                if u.get("project_id") is None
                else project_key_by_id.get(
                    u.get("project_id"), str(u.get("project_id"))
                )
            ),
            "unit_code": u.get("unit_code"),
            "display_symbol": u.get("display_symbol"),
            "source_field_id": u.get("source_field_id"),
            "source_entity": u.get("source_entity"),
        }
        for u in filtered
    ]
    with st.expander("Current Unit Bindings", expanded=True):
        st.caption(
            "Global (all projects) bindings apply to every project unless a project-specific binding overrides them."
        )
        st.dataframe(display_units, use_container_width=True, hide_index=True)

    # --- Missing check (deduplicated by unit_code) ---
    unit_set = {
        (u.get("project_id"), u.get("unit_code"))
        for u in all_units
        if u.get("source_field_id")
    }
    missing_by_unit: dict[tuple, dict[str, Any]] = {}
    for p in projects:
        for c in required_contracts:
            dedup_key = (p["project_id"], c["unit_code"])
            if dedup_key not in unit_set and (None, c["unit_code"]) not in unit_set:
                if dedup_key not in missing_by_unit:
                    missing_by_unit[dedup_key] = {
                        "project_id": p["project_id"],
                        "project_key": p["project_key"],
                        "unit_code": c["unit_code"],
                        "required_by_calcs": [],
                    }
                missing_by_unit[dedup_key]["required_by_calcs"].append(c["calc_code"])

    missing_rows = [
        {
            "project_key": v["project_key"],
            "unit_code": v["unit_code"],
            "required_by": ", ".join(sorted(v["required_by_calcs"])),
        }
        for v in missing_by_unit.values()
        if (project_filter is None or v["project_id"] == project_filter)
        and (calc_filter is None or calc_filter in v["required_by_calcs"])
    ]
    with st.expander("Missing required Unit Bindings", expanded=True):
        if not missing_rows:
            st.success("✓ All required unit bindings are configured")
        else:
            st.dataframe(missing_rows, use_container_width=True, hide_index=True)

    st.markdown("#### Create / Update Unit Binding")
    project_map = {"All (NULL)": None}
    for p in projects:
        project_map[f"{p['project_key']} - {p['project_name']}"] = p["project_id"]
    project_label = st.selectbox(
        "Project", list(project_map.keys()), key="units_project_input"
    )
    project_id = project_map[project_label]
    source_project_id = project_id
    if project_id is None:
        source_project_map = {
            f"{p['project_key']} - {p['project_name']}": p["project_id"]
            for p in projects
        }
        if not source_project_map:
            st.info(
                "No projects imported yet. Import projects first in Integrations tab."
            )
            return
        source_project_label = st.selectbox(
            "Field Source Project",
            list(source_project_map.keys()),
            key="units_source_project_input",
            help="Project from which to take field keys list for the global (NULL) binding.",
        )
        if source_project_label is None:
            st.info("Select a project to load field keys.")
            return
        source_project_id = source_project_map[source_project_label]
    try:
        field_keys = client.request(
            "GET",
            "/admin/catalog/field-keys",
            token=token,
            params={"project_id": source_project_id},
        )
    except Exception as exc:
        show_error(exc)
        return
    calc_codes_for_units = sorted({c["calc_code"] for c in required_contracts})
    field_map = {"None": None}
    for f in field_keys:
        field_map[f"{f['external_key']} - {f['name']} ({f['field_key_id']})"] = f[
            "field_key_id"
        ]
    c1, c2, c3 = st.columns(3)
    with c1:
        selected_calc_codes = st.multiselect(
            "Metric Calculations",
            calc_codes_for_units,
            default=[],
            key="units_calc_codes_input",
            help="You can select multiple metrics and save unit binding for all of them at once.",
        )
    # Pre-fill display_symbol from existing binding if any
    existing_symbol = "SP"
    if selected_calc_codes:
        first_unit_code = next(
            (calc_to_unit[c] for c in selected_calc_codes if c in calc_to_unit), None
        )
        if first_unit_code:
            existing_binding = next(
                (
                    u
                    for u in all_units
                    if u.get("unit_code") == first_unit_code
                    and (
                        u.get("project_id") == project_id
                        or (project_id is None and u.get("project_id") is None)
                    )
                ),
                None,
            )
            if existing_binding:
                existing_symbol = existing_binding.get("display_symbol") or "SP"
    edit_key = f"{project_id}|{'_'.join(sorted(selected_calc_codes))}"
    _reset_form_state_on_edit_change(
        "units_v2", edit_key, ["units_display_symbol_input"]
    )

    with c2:
        display_symbol = st.text_input(
            "Display Symbol", value=existing_symbol, key="units_display_symbol_input"
        )
    with c3:
        field_label = st.selectbox(
            "Source Field", list(field_map.keys()), key="units_source_field_input"
        )
    # Warn if creating project-specific binding when a global one already exists for same unit_code
    if project_id is not None and selected_calc_codes:
        selected_unit_codes_preview = {
            calc_to_unit[c] for c in selected_calc_codes if c in calc_to_unit
        }
        conflicting = [
            uc
            for uc in selected_unit_codes_preview
            if any(
                u.get("project_id") is None and u.get("unit_code") == uc
                for u in all_units
            )
        ]
        if conflicting:
            st.warning(
                f"A global (all-projects) binding already exists for: {', '.join(sorted(conflicting))}. "
                "Adding a project-specific binding will override the global one for this project only."
            )

    if save_bar("Save Unit"):
        try:
            if not selected_calc_codes:
                st.warning("Select at least one metric calculation.")
                return
            selected_unit_codes = sorted(
                {
                    calc_to_unit[calc]
                    for calc in selected_calc_codes
                    if calc in calc_to_unit
                }
            )
            payload = {
                "project_id": project_id,
                "display_symbol": display_symbol,
                "source_field_id": field_map[field_label],
                "source_entity": "clean_jira.field_keys",
            }
            for unit_code in selected_unit_codes:
                client.request(
                    "PUT", f"/admin/units/{unit_code}", token=token, json=payload
                )
            show_success("Unit binding saved")
            st.rerun()
        except Exception as exc:
            show_error(exc)

    st.markdown("#### Delete Unit Binding")
    del_unit_options: dict[str, Any] = {"-- select to delete --": None}
    project_key_by_id_units = {p["project_id"]: p["project_key"] for p in projects}
    for u in all_units:
        if not u.get("id"):
            continue
        scope = (
            "Global"
            if u.get("project_id") is None
            else project_key_by_id_units.get(
                u.get("project_id"), str(u.get("project_id"))
            )
        )
        del_unit_options[
            f"{scope} | {u['unit_code']} | {u.get('source_field_id')} | {u['id']}"
        ] = u["id"]
    del_unit_select = st.selectbox(
        "Unit binding to delete", list(del_unit_options.keys()), key="units_del_select"
    )
    del_unit_id = del_unit_options[del_unit_select]
    if del_unit_id and st.button("Delete", type="secondary", key="units_del_btn"):
        try:
            client.request("DELETE", f"/admin/units/{del_unit_id}", token=token)
            show_success("Unit binding deleted")
            st.rerun()
        except Exception as exc:
            show_error(exc)


def _tab_slices_v2(client: AdminApiClient, token: str) -> None:
    section_title("Slice Rules")
    try:
        projects = client.request("GET", "/admin/catalog/projects", token=token)
        contracts = client.request("GET", "/admin/contracts/catalog", token=token)
        all_slices = client.request("GET", "/admin/slice-rules", token=token)
        schema_map = client.request(
            "GET", "/admin/catalog/clean-jira-schema-map", token=token
        )
    except Exception as exc:
        show_error(exc)
        return
    calc_codes = sorted(
        {c["calc_code"] for c in contracts if c.get("supports_slicing")}
    )
    f1, f2 = st.columns(2)
    with f1:
        project_filter = _project_filter(projects, "slices_project_filter")
    with f2:
        calc_filter = _calc_filter(calc_codes, "slices_calc_filter")
    filtered = [
        s
        for s in all_slices
        if project_filter is None or s.get("project_id") == project_filter
    ]
    with st.expander("Current Slice Rules", expanded=True):
        st.dataframe(filtered, use_container_width=True, hide_index=True)

    has_slice_project = {s.get("project_id") for s in all_slices if s.get("enabled")}
    has_global_slice = any(
        s.get("project_id") is None and s.get("enabled") for s in all_slices
    )
    missing_rows: list[dict[str, Any]] = []
    for p in projects:
        for calc in calc_codes:
            if p["project_id"] not in has_slice_project and not has_global_slice:
                missing_rows.append(
                    {
                        "project_id": p["project_id"],
                        "project_key": p["project_key"],
                        "calc_code": calc,
                        "missing": "slice_rule",
                    }
                )
    missing_rows = [
        r
        for r in missing_rows
        if (project_filter is None or r["project_id"] == project_filter)
        and (calc_filter is None or r["calc_code"] == calc_filter)
    ]
    with st.expander("Missing required Slice Rules", expanded=True):
        if not missing_rows:
            st.success("✓ All required slice rules are configured")
        else:
            st.dataframe(missing_rows, use_container_width=True, hide_index=True)

    st.markdown("#### Create / Edit Slice Rule")
    edit_options = {"Create new": None}
    for s in filtered:
        edit_options[f"{s['id']} | {s['rule_name']} | {s.get('project_id')}"] = s["id"]
    selected_edit = st.selectbox(
        "Slice rule to edit", list(edit_options.keys()), key="slices_edit_id"
    )
    edit_id = edit_options[selected_edit]
    edit_row = next((s for s in all_slices if s.get("id") == edit_id), None)
    _reset_form_state_on_edit_change(
        "slices_form",
        str(edit_id) if edit_id is not None else None,
        [
            "slices_project_input",
            "slices_schema_input",
            "slices_table_input",
            "slices_group_input",
            "slices_rule_name_input",
            "slices_enabled_input",
            "slices_target_definition_input",
        ],
    )
    project_options = {"All (NULL)": None}
    for p in projects:
        project_options[f"{p['project_key']} - {p['project_name']}"] = p["project_id"]
    project_labels = list(project_options.keys())
    default_project_id = edit_row.get("project_id") if edit_row else None
    default_project_label = next(
        (label for label, pid in project_options.items() if pid == default_project_id),
        project_labels[0],
    )
    project_label = st.selectbox(
        "Project",
        project_labels,
        index=_selectbox_index(project_labels, default_project_label),
        key="slices_project_input",
    )
    project_id = project_options[project_label]

    tables = schema_map.get("tables", [])
    source_map: dict[str, list[str]] = {}
    schemas: dict[str, list[str]] = {}
    for t in tables:
        raw = t["table_name"]
        if "." in raw:
            schema_name, table_name = raw.split(".", 1)
        else:
            schema_name, table_name = "clean_jira", raw
        fq = f"{schema_name}.{table_name}"
        source_map[fq] = [c["column_name"] for c in t["columns"]]
        schemas.setdefault(schema_name, []).append(fq)
    schema_names = sorted(schemas.keys())
    default_source_table = edit_row.get("source_table") if edit_row else None
    default_schema_name = (
        default_source_table.split(".", 1)[0]
        if default_source_table and "." in default_source_table
        else schema_names[0]
    )
    schema_name = st.selectbox(
        "Source Schema",
        schema_names,
        index=_selectbox_index(schema_names, default_schema_name),
        key="slices_schema_input",
    )
    source_tables = sorted(schemas[schema_name])
    source_table = st.selectbox(
        "Source Table",
        source_tables,
        index=(
            _selectbox_index(source_tables, default_source_table)
            if default_source_table
            else 0
        ),
        key="slices_table_input",
    )
    group_columns = source_map[source_table]
    default_group_by = edit_row.get("group_by_source_column") if edit_row else None
    group_by = st.selectbox(
        "Group By Column",
        group_columns,
        index=(
            _selectbox_index(group_columns, default_group_by) if default_group_by else 0
        ),
        key="slices_group_input",
    )
    rule_name = st.text_input(
        "Rule Name",
        value=edit_row.get("rule_name") if edit_row else "By Issue Type",
        key="slices_rule_name_input",
    )
    enabled = st.checkbox(
        "Enabled",
        value=bool(edit_row.get("enabled")) if edit_row else True,
        key="slices_enabled_input",
    )

    td_options = {"All (NULL)": (None, None)}
    for s in all_slices:
        if s.get("target_definition_id") or s.get("target_definition_name"):
            label = f"{s.get('target_definition_name') or 'Unnamed'} ({s.get('target_definition_id')})"
            td_options[label] = (
                s.get("target_definition_id"),
                s.get("target_definition_name"),
            )
    td_labels = list(td_options.keys())
    default_td_pair = (
        edit_row.get("target_definition_id") if edit_row else None,
        edit_row.get("target_definition_name") if edit_row else None,
    )
    default_td_label = next(
        (label for label, pair in td_options.items() if pair == default_td_pair),
        "All (NULL)",
    )
    td_label = st.selectbox(
        "Target Definition (ID + Name)",
        td_labels,
        index=_selectbox_index(td_labels, default_td_label),
        key="slices_target_definition_input",
        help="'All (NULL)' writes NULL to target_definition_id and target_definition_name.",
    )
    target_definition_id, target_definition_name = td_options[td_label]

    if save_bar("Save Slice Rule"):
        try:
            payload = {
                "id": edit_id,
                "project_id": project_id,
                "rule_name": rule_name,
                "target_definition_id": target_definition_id,
                "target_definition_name": target_definition_name,
                "source_table": source_table,
                "group_by_source_column": group_by,
                "enabled": enabled,
            }
            client.request("POST", "/admin/slice-rules", token=token, json=payload)
            show_success("Slice rule saved")
            st.rerun()
        except Exception as exc:
            show_error(exc)

    st.markdown("#### Delete Slice Rule")
    project_key_by_id_slices = {p["project_id"]: p["project_key"] for p in projects}
    del_slice_options: dict[str, Any] = {"-- select to delete --": None}
    for s in all_slices:
        if not s.get("id"):
            continue
        scope = (
            "Global"
            if s.get("project_id") is None
            else project_key_by_id_slices.get(
                s.get("project_id"), str(s.get("project_id"))
            )
        )
        del_slice_options[f"{scope} | {s['rule_name']} | {s['id']}"] = s["id"]
    del_slice_select = st.selectbox(
        "Slice rule to delete", list(del_slice_options.keys()), key="slices_del_select"
    )
    del_slice_id = del_slice_options[del_slice_select]
    if del_slice_id and st.button("Delete", type="secondary", key="slices_del_btn"):
        try:
            client.request("DELETE", f"/admin/slice-rules/{del_slice_id}", token=token)
            show_success("Slice rule deleted")
            st.rerun()
        except Exception as exc:
            show_error(exc)


def _tab_integrations(client: AdminApiClient, token: str) -> None:
    """Manage data source integrations and imported projects."""
    section_title(
        "Integrations", "Connect external tools and select projects to import."
    )

    me = st.session_state.get("me") or {}
    user_id = me.get("user_id") or me.get("id")

    # ── Create new integration ────────────────────────────────────────────
    with st.expander("Add integration", expanded=False):
        try:
            int_types = client.request("GET", "/integration-types", token=token)
        except Exception as exc:
            show_error(exc)
            int_types = []

        type_options = {t["name"]: t["id"] for t in int_types if t.get("is_active")}
        if not type_options:
            st.info("No active integration types available.")
        else:
            with st.form("new_integration"):
                selected_type_name = st.selectbox(
                    "Integration type", list(type_options)
                )
                instance_url = st.text_input(
                    "Instance URL",
                    placeholder="https://yourcompany.atlassian.net",
                    help="Leave blank only for SaaS tools where URL is fixed.",
                )
                user_email = st.text_input("Login email")
                api_token = st.text_input("API token", type="password")
                submitted = st.form_submit_button("Save", type="primary")

            if submitted:
                if not api_token:
                    st.error("API token is required.")
                elif not user_id:
                    st.error("Cannot determine current user ID.")
                else:
                    try:
                        client.request(
                            "POST",
                            "/integrations",
                            token=token,
                            params={"user_id": user_id},
                            json={
                                "integration_type_id": type_options[selected_type_name],
                                "instance_url": instance_url or None,
                                "user_email": user_email or None,
                                "api_token": api_token,
                                "secret_provider": "hardcoded",
                            },
                        )
                        show_success("Integration saved.")
                        st.rerun()
                    except Exception as exc:
                        show_error(exc)

    st.divider()

    # ── List existing integrations ────────────────────────────────────────
    try:
        integrations = client.request("GET", "/integrations", token=token)
    except Exception as exc:
        show_error(exc)
        return

    if not integrations:
        st.info("No integrations configured yet. Add one above.")
        return

    int_options = {
        f"{i['integration_type_name']} — {i['instance_url'] or 'cloud'} (id: {i['id'][:8]}…)": i
        for i in integrations
    }
    selected_label = st.selectbox(
        "Select integration", list(int_options), key="sel_integration"
    )
    integration = int_options[selected_label]
    int_id = integration["id"]

    _reset_form_state_on_edit_change(
        "integrations",
        int_id,
        ["discovered_projects", "sel_jira_projects"],
    )

    col1, col2 = st.columns([1, 5])
    with col1:
        active_toggle = st.toggle(
            "Active",
            value=integration["is_active"],
            key=f"int_active_{int_id}",
        )
        if active_toggle != integration["is_active"]:
            try:
                client.request(
                    "PUT",
                    f"/integrations/{int_id}",
                    token=token,
                    json={"is_active": active_toggle},
                )
                st.rerun()
            except Exception as exc:
                show_error(exc)
    with col2:
        st.caption(
            f"**URL:** {integration['instance_url'] or '—'}  |  "
            f"**Email:** {integration['user_email'] or '—'}  |  "
            f"**Last sync:** {integration['last_sync_status'] or 'never'}"
        )

    st.divider()

    # ── Discover Jira projects ────────────────────────────────────────────
    section_title("Import projects", "Fetch available projects from this integration.")

    if st.button("Fetch Jira projects", key="btn_fetch_jira"):
        with st.spinner("Connecting to Jira…"):
            try:
                discovered = client.request(
                    "GET",
                    f"/integrations/{int_id}/jira-projects",
                    token=token,
                )
                st.session_state["discovered_projects"] = discovered
            except Exception as exc:
                show_error(exc)

    discovered: list[dict[str, Any]] = st.session_state.get("discovered_projects") or []

    if discovered:
        not_imported = [p for p in discovered if not p.get("already_imported")]
        already_imported = [p for p in discovered if p.get("already_imported")]

        if not_imported:
            options = [f"{p['key']} — {p['name']}" for p in not_imported]
            selected_labels = st.multiselect(
                f"Projects available to import ({len(not_imported)})",
                options,
                key="sel_jira_projects",
            )

            if selected_labels and st.button("Import selected", type="primary"):
                key_to_project = {f"{p['key']} — {p['name']}": p for p in not_imported}
                errors = []
                imported_count = 0
                for label in selected_labels:
                    p = key_to_project[label]
                    try:
                        client.request(
                            "POST",
                            "/projects",
                            token=token,
                            params={"user_id": user_id},
                            json={
                                "tool_integration_id": int_id,
                                "external_key": p["key"],
                                "external_id": p["id"],
                                "name": p["name"],
                                "external_url": p.get("url"),
                            },
                        )
                        imported_count += 1
                    except Exception as exc:
                        errors.append(f"{p['key']}: {exc}")

                if imported_count:
                    show_success(f"Imported {imported_count} project(s).")
                for err in errors:
                    st.error(err)
                st.session_state.pop("discovered_projects", None)
                st.rerun()

        if already_imported:
            st.caption(
                f"Already imported: {', '.join(p['key'] for p in already_imported)}"
            )

    st.divider()

    # ── Manage imported projects ──────────────────────────────────────────
    section_title("Imported projects")
    try:
        projects = client.request(
            "GET",
            f"/projects?integration_id={int_id}",
            token=token,
        )
    except Exception as exc:
        show_error(exc)
        return

    if not projects:
        st.info("No projects imported yet for this integration.")
        return

    for proj in projects:
        pid = proj["id"]
        c1, c2, c3 = st.columns([1, 3, 6])
        with c1:
            is_active = st.toggle(
                "Active",
                value=proj["is_active"],
                key=f"proj_active_{pid}",
                label_visibility="collapsed",
            )
            if is_active != proj["is_active"]:
                try:
                    client.request(
                        "PUT",
                        f"/projects/{pid}",
                        token=token,
                        json={"is_active": is_active},
                    )
                    st.rerun()
                except Exception as exc:
                    show_error(exc)
        with c2:
            st.write(f"**{proj['external_key']}**")
        with c3:
            st.caption(proj["name"])


def _tab_metrics_run(client: AdminApiClient, token: str) -> None:
    section_title(
        "Metrics Run",
        "Select individual metrics to recalculate and monitor progress.",
    )

    try:
        metric_jobs = client.request("GET", "/admin/metric-jobs", token=token)
    except Exception as exc:
        show_error(exc)
        return

    if not metric_jobs:
        st.info("No metric jobs available.")
        return

    job_by_name = {j["job_name"]: j for j in metric_jobs}

    st.markdown("#### Select metrics to run")
    c_all, c_none, _ = st.columns([1, 1, 6])
    if c_all.button("Select all", key="mrun_select_all"):
        for j in metric_jobs:
            st.session_state[f"mrun_chk_{j['job_name']}"] = True
    if c_none.button("Clear", key="mrun_clear"):
        for j in metric_jobs:
            st.session_state[f"mrun_chk_{j['job_name']}"] = False

    cols_per_row = 3
    rows = [
        metric_jobs[i : i + cols_per_row]
        for i in range(0, len(metric_jobs), cols_per_row)
    ]
    for row in rows:
        cols = st.columns(cols_per_row)
        for col, job in zip(cols, row, strict=False):
            with col:
                st.checkbox(
                    job["title"],
                    key=f"mrun_chk_{job['job_name']}",
                    help=job.get("description", ""),
                )

    selected = [
        j["job_name"]
        for j in metric_jobs
        if st.session_state.get(f"mrun_chk_{j['job_name']}", False)
    ]

    st.markdown(f"**Selected:** {len(selected)} / {len(metric_jobs)}")

    if st.button(
        "Run selected",
        type="primary",
        disabled=not selected,
        key="mrun_launch",
    ):
        try:
            launches = client.request(
                "POST",
                "/admin/metric-jobs/launch-batch",
                token=token,
                json={"job_names": selected},
            )
            new_runs = []
            for item in launches:
                title = job_by_name.get(item["job_name"], {}).get(
                    "title", item["job_name"]
                )
                new_runs.append(
                    {
                        "job_name": item["job_name"],
                        "title": title,
                        "run_id": item.get("run_id"),
                        "status": item.get("status", "UNKNOWN"),
                        "progress_pct": 0.0,
                        "error": item.get("error"),
                    }
                )
            st.session_state["metrics_run_active"] = new_runs
            launched = sum(1 for r in new_runs if r["run_id"])
            show_success(f"Launched {launched} of {len(selected)} metric jobs.")
        except Exception as exc:
            show_error(exc)

    st.divider()

    active_runs: list[dict] = st.session_state.get("metrics_run_active", [])
    if not active_runs:
        st.info("No active metric runs. Select metrics and click Run.")
        return

    c1, c2 = st.columns([1, 4])
    with c1:
        auto_poll = st.toggle("Auto refresh", value=True, key="mrun_auto_refresh")
    with c2:
        st.caption("Polling interval: 3 seconds while runs are active.")
    st.button("Refresh now", key="mrun_refresh_now")

    any_running = False
    for run_entry in active_runs:
        run_id = run_entry.get("run_id")
        if not run_id:
            run_entry["status"] = "LAUNCH_FAILED"
            continue
        current_status = (run_entry.get("status") or "UNKNOWN").upper()
        if current_status in {"SUCCESS", "FAILURE", "CANCELED", "LAUNCH_FAILED"}:
            continue
        try:
            details = client.request("GET", f"/admin/jobs/runs/{run_id}", token=token)
            run_entry["status"] = (details.get("status") or "UNKNOWN").upper()
            run_entry["progress_pct"] = details.get("progress_pct", 0.0)
        except Exception:  # noqa: BLE001,S110
            pass  # noqa: S110
        if run_entry["status"] not in {
            "SUCCESS",
            "FAILURE",
            "CANCELED",
            "LAUNCH_FAILED",
        }:
            any_running = True

    st.session_state["metrics_run_active"] = active_runs

    st.markdown("#### Run Status")
    status_rows = [
        {
            "metric": r["title"],
            "job": r["job_name"],
            "run_id": r.get("run_id") or "-",
            "status": r.get("status", "UNKNOWN"),
            "progress_%": r.get("progress_pct", 0.0),
            "error": r.get("error") or "",
        }
        for r in active_runs
    ]
    st.dataframe(
        pd.DataFrame(status_rows),
        use_container_width=True,
        hide_index=True,
    )

    if any_running and auto_poll:
        time.sleep(3)
        st.rerun()


def _page_configuration(client: AdminApiClient, token: str) -> None:
    tabs = st.tabs(
        [
            "Integrations",
            "Metrics catalog",
            "Commitment",
            "Calc Settings",
            "Units",
            "Slices",
            "Validate",
            "Jobs",
            "Metrics Run",
        ]
    )

    with tabs[0]:
        _tab_integrations(client, token)
    with tabs[1]:
        _tab_metrics_catalog(client, token)
    with tabs[2]:
        _tab_commitment_v2(client, token)
    with tabs[3]:
        _tab_settings_v2(client, token)
    with tabs[4]:
        _tab_units_v2(client, token)
    with tabs[5]:
        _tab_slices_v2(client, token)
    with tabs[6]:
        _tab_validate(client, token, None)
    with tabs[7]:
        _tab_jobs(client, token)
    with tabs[8]:
        _tab_metrics_run(client, token)


def main() -> None:
    _ensure_state()
    client = get_client()

    # Handle Google OAuth callback token or errors from URL params
    # Note: st.query_params is available in Streamlit 1.30+
    params = st.query_params
    if "token" in params:
        st.session_state.token = params["token"]
        st.query_params.clear()
        st.rerun()

    if "error" in params:
        error_code = params["error"]
        show_error(f"Authentication error: {error_code}")
        st.query_params.clear()

    if not st.session_state.token:
        _login_view(client)
        return

    try:
        if not st.session_state.me:
            st.session_state.me = client.request(
                "GET", "/admin/auth/me", token=st.session_state.token
            )
    except Exception:
        st.session_state.token = None
        st.session_state.me = None
        st.rerun()

    with st.sidebar:
        st.markdown("### Admin")
        st.write(st.session_state.me["email"])
        if st.button("Logout"):
            _logout(client)
    _page_configuration(client, st.session_state.token)


if __name__ == "__main__":
    main()
