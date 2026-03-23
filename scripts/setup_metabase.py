import logging
import os
import time

import requests

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# Configuration
METABASE_URL = os.getenv("METABASE_URL", "http://metabase:3000")
MB_ADMIN_EMAIL = os.getenv("MB_ADMIN_EMAIL", "admin@example.com")
MB_ADMIN_PASSWORD = os.getenv(
    "MB_ADMIN_PASSWORD", "StrongPassword123!"
)  # Must be strong
MB_DB_NAME = os.getenv("POSTGRES_DB", "process_metrics")
MB_DB_HOST = os.getenv("POSTGRES_HOST", "postgres")
MB_DB_PORT = os.getenv("POSTGRES_PORT", "5432")
MB_DB_USER = os.getenv("POSTGRES_USER", "postgres")
MB_DB_PASS = os.getenv("POSTGRES_PASSWORD", "postgres")


def wait_for_metabase():
    """Wait for Metabase to be healthy."""
    logger.info("Waiting for Metabase to be ready...")
    retries = 30
    for i in range(retries):
        try:
            response = requests.get(f"{METABASE_URL}/api/health", timeout=10)
            if response.status_code == 200:
                logger.info("Metabase is ready!")
                return True
        except requests.ConnectionError:
            pass

        logger.info(f"Waiting... ({i + 1}/{retries})")
        time.sleep(5)

    logger.error("Metabase did not start in time.")
    return False


def get_setup_token():
    """Get the setup token if Metabase is not set up."""
    try:
        response = requests.get(f"{METABASE_URL}/api/session/properties", timeout=10)
        data = response.json()
        if data.get("setup-token"):
            return data["setup-token"]
        return None
    except Exception as e:
        logger.error(f"Error checking setup status: {e}")
        return None


def setup_admin(setup_token):
    """Create the initial admin user."""
    logger.info("Setting up admin user...")
    payload = {
        "token": setup_token,
        "user": {
            "first_name": "Admin",
            "last_name": "User",
            "email": MB_ADMIN_EMAIL,
            "password": MB_ADMIN_PASSWORD,
        },
        "prefs": {"site_name": "Process Metrics Platform", "allow_tracking": False},
        "database": {
            "engine": "postgres",
            "name": "Process Metrics DB",
            "details": {
                "host": MB_DB_HOST,
                "port": int(MB_DB_PORT),
                "dbname": MB_DB_NAME,
                "user": MB_DB_USER,
                "password": MB_DB_PASS,
                "schema": "metrics",  # Focus on metrics schema by default
            },
        },
    }

    response = requests.post(f"{METABASE_URL}/api/setup", json=payload, timeout=10)
    if response.status_code == 200:
        logger.info("Admin user and initial database configured successfully.")
        return response.json().get("id")  # Returns session ID
    else:
        logger.error(f"Failed to setup admin: {response.text}")
        return None


def get_session_token():
    """Login and get session token."""
    payload = {"username": MB_ADMIN_EMAIL, "password": MB_ADMIN_PASSWORD}
    response = requests.post(f"{METABASE_URL}/api/session", json=payload, timeout=10)
    if response.status_code == 200:
        return response.json()["id"]
    else:
        logger.error("Failed to login.")
        return None


def get_database_id(headers):
    """Get the ID of the connected database."""
    response = requests.get(f"{METABASE_URL}/api/database", headers=headers, timeout=10)
    if response.status_code == 200:
        dbs = response.json()
        for db in dbs:
            # Look for the DB we just created or one named appropriately
            if db["name"] == "Process Metrics DB" or db["engine"] == "postgres":
                return db["id"]
    return None


def create_collection(headers, name="Process Metrics"):
    """Create a collection for our questions."""
    # Check if exists
    response = requests.get(
        f"{METABASE_URL}/api/collection", headers=headers, timeout=10
    )
    for col in response.json():
        if col["name"] == name:
            return col["id"]

    payload = {"name": name, "color": "#509EE3"}
    response = requests.post(
        f"{METABASE_URL}/api/collection", headers=headers, json=payload, timeout=10
    )
    if response.status_code == 200:
        return response.json()["id"]
    return None


def create_question(
    headers,
    collection_id,
    db_id,
    name,
    query_sql,
    visualization="table",
    viz_settings=None,
):
    """Create a new question (card)."""
    # Check if question exists to avoid duplicates
    # Getting all cards is separate, skipping check for simplicity in this script or could impl simple check

    payload = {
        "name": name,
        "collection_id": collection_id,
        "display": visualization,
        "dataset_query": {
            "database": db_id,
            "type": "native",
            "native": {"query": query_sql},
        },
        "visualization_settings": viz_settings or {},
    }

    response = requests.post(
        f"{METABASE_URL}/api/card", headers=headers, json=payload, timeout=10
    )
    if response.status_code == 200:
        logger.info(f"Created question: {name}")
        return response.json()["id"]
    else:
        logger.error(f"Failed to create question {name}: {response.text}")
        return None


def create_dashboard(
    headers, collection_id, name="Process Metrics Overview", cards=None
):
    """Create a dashboard and add cards to it."""
    # Check if dashboard exists
    response = requests.get(
        f"{METABASE_URL}/api/dashboard", headers=headers, timeout=10
    )
    for dash in response.json():
        if dash["name"] == name:
            logger.info(f"Dashboard '{name}' already exists.")
            return dash["id"]

    # Create dashboard
    payload = {"name": name, "collection_id": collection_id, "parameters": []}

    response = requests.post(
        f"{METABASE_URL}/api/dashboard", headers=headers, json=payload, timeout=10
    )
    if response.status_code != 200:
        logger.error(f"Failed to create dashboard: {response.text}")
        return None

    dashboard_id = response.json()["id"]
    logger.info(f"Created dashboard: {name} (ID: {dashboard_id})")

    # Add cards
    if cards:
        for card in cards:
            card_id = card["id"]
            width = card.get("width", 8)
            height = card.get("height", 6)
            x = card.get("x", 0)
            y = card.get("y", 0)  # Simple layout logic can be improved

            card_payload = {
                "cardId": card_id,
                "sizeX": width,
                "sizeY": height,
                "col": x,
                "row": y,
            }
            requests.post(
                f"{METABASE_URL}/api/dashboard/{dashboard_id}/cards",
                headers=headers,
                json=card_payload,
                timeout=10,
            )

    return dashboard_id


def main():
    if not wait_for_metabase():
        return

    setup_token = get_setup_token()
    session_token = None

    if setup_token:
        logger.info("Metabase needs setup.")
        session_token = setup_admin(setup_token)
    else:
        logger.info("Metabase likely already setup. Attempting login.")
        session_token = get_session_token()

    if not session_token:
        logger.error("Could not obtain session token. Exiting.")
        return

    headers = {"X-Metabase-Session": session_token}

    # 1. Get Database ID
    db_id = get_database_id(headers)
    if not db_id:
        logger.error("Database not found. Please ensure DB is connected.")
        # If we logged in but didn't run setup (e.g. restart), we might need to add DB manually?
        # For this script assuming setup created it or it exists.
        # Fallback: Create DB connection if missing logic could be added here.
        return

    # 2. Create Collection
    collection_id = create_collection(headers)

    # 3. Create Questions
    logger.info("Creating metrics questions...")

    card_ids = []

    # --- Velocity ---
    q_velocity = create_question(
        headers,
        collection_id,
        db_id,
        "Velocity (Sprint Completion)",
        "SELECT sprint_name, completed_story_points, planned_story_points FROM metrics.mv_velocity ORDER BY start_date ASC LIMIT 10",
        "bar",
        {
            "graph.dimensions": ["sprint_name"],
            "graph.metrics": ["completed_story_points", "planned_story_points"],
            "series_settings": {
                "planned_story_points": {"title": "Planned Points", "color": "#A0A0A0"},
                "completed_story_points": {
                    "title": "Completed Points",
                    "color": "#509EE3",
                },
            },
        },
    )
    if q_velocity:
        card_ids.append({"id": q_velocity, "x": 0, "y": 0, "width": 12, "height": 6})

    # --- Lead Time Scatter ---
    q_lead_time = create_question(
        headers,
        collection_id,
        db_id,
        "Lead Time Distribution",
        "SELECT commitment_end_at::date as completed_date, lead_time_days, issue_type FROM metrics.mv_lead_time WHERE commitment_end_at IS NOT NULL ORDER BY commitment_end_at DESC LIMIT 500",
        "scatter",
        {
            "graph.dimensions": ["completed_date"],
            "graph.metrics": ["lead_time_days"],
            "graph.group_by": ["issue_type"],  # Color by issue type
        },
    )
    if q_lead_time:
        card_ids.append({"id": q_lead_time, "x": 0, "y": 6, "width": 12, "height": 6})

    # --- CFD ---
    q_cfd = create_question(
        headers,
        collection_id,
        db_id,
        "Cumulative Flow Diagram",
        """
        SELECT date, status_category, sum(issue_count) as total_issues
        FROM metrics.mv_cfd
        WHERE date >= current_date - interval '30 days'
        GROUP BY date, status_category
        ORDER BY date
        """,
        "area",
        {
            "graph.dimensions": ["date"],
            "graph.metrics": ["total_issues"],
            "graph.group_by": ["status_category"],
            "stackable.stack_type": "stacked",
        },
    )
    if q_cfd:
        card_ids.append({"id": q_cfd, "x": 0, "y": 12, "width": 12, "height": 6})

    # --- Throughput Weekly ---
    q_throughput = create_question(
        headers,
        collection_id,
        db_id,
        "Weekly Throughput",
        "SELECT week_start_date, sum(issues_completed) as total_completed FROM metrics.mv_throughput_weekly GROUP BY week_start_date ORDER BY week_start_date ASC",
        "bar",
        {"graph.dimensions": ["week_start_date"], "graph.metrics": ["total_completed"]},
    )
    if q_throughput:
        card_ids.append({"id": q_throughput, "x": 12, "y": 0, "width": 6, "height": 6})

    # --- Work Item Aging ---
    q_aging = create_question(
        headers,
        collection_id,
        db_id,
        "Work Item Aging (Active Issues)",
        "SELECT issue_key, current_status_id, age_days FROM metrics.fact_work_item_aging ORDER BY age_days DESC LIMIT 20",
        "bar",
        {
            "graph.dimensions": ["issue_key"],
            "graph.metrics": ["age_days"],
            "graph.x_axis.title_text": "Age (Days)",
            "graph.y_axis.title_text": "Issue Key",
        },
    )
    if q_aging:
        card_ids.append({"id": q_aging, "x": 12, "y": 6, "width": 6, "height": 8})

    # --- Flow Efficiency (Avg) ---
    q_flow = create_question(
        headers,
        collection_id,
        db_id,
        "Avg Flow Efficiency",
        "SELECT AVG(flow_efficiency_pct) as avg_efficiency FROM metrics.fact_flow_efficiency",
        "scalar",  # Number
        {},
    )
    if q_flow:
        card_ids.append({"id": q_flow, "x": 12, "y": 14, "width": 6, "height": 4})

    # --- Backlog Health ---
    q_backlog = create_question(
        headers,
        collection_id,
        db_id,
        "Backlog Health",
        """
        SELECT project_key, total_backlog_size, avg_age_days, stale_percentage
        FROM metrics.mv_backlog_health
        """,
        "table",
        {},
    )
    if q_backlog:
        card_ids.append({"id": q_backlog, "x": 0, "y": 18, "width": 12, "height": 5})

    # --- Time to Market ---
    q_ttm = create_question(
        headers,
        collection_id,
        db_id,
        "Time to Market (Features)",
        """
        SELECT released_at::date as release_date, time_to_market_days, issue_key
        FROM metrics.mv_time_to_market
        ORDER BY released_at DESC LIMIT 100
        """,
        "scatter",
        {
            "graph.dimensions": ["release_date"],
            "graph.metrics": ["time_to_market_days"],
        },
    )
    if q_ttm:
        card_ids.append({"id": q_ttm, "x": 0, "y": 23, "width": 18, "height": 6})

    # --- Release Cadence ---
    q_releases = create_question(
        headers,
        collection_id,
        db_id,
        "Release Stats",
        "SELECT project_key, releases_per_month, avg_days_between_releases FROM metrics.mv_release_cadence",
        "table",
        {},
    )
    if q_releases:
        card_ids.append({"id": q_releases, "x": 12, "y": 23, "width": 6, "height": 6})

    # 4. Create Dashboard
    create_dashboard(headers, collection_id, "Process Metrics Overview", card_ids)

    logger.info("Metabase setup complete!")


if __name__ == "__main__":
    main()
