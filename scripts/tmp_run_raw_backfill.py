from pipelines.assets.jira.raw import run_jira_pipeline, validate_jira_credentials
from pipelines.utils.db_config import get_project_credentials

projects = ["TWBACKEND", "TWWB", "TWMOB"]
for p in projects:
    creds = get_project_credentials(p)
    if not creds:
        print(f"[ERR] no credentials for {p}")
        raise SystemExit(1)
    validate_jira_credentials(creds.instance_url, creds.user_email, creds.api_token)
    print(f"[START] {p}", flush=True)
    res = run_jira_pipeline(
        base_url=creds.instance_url,
        email=creds.user_email,
        api_token=creds.api_token,
        projects=[p],
        pipeline_name=f"jira_raw_{p}",
    )
    print(f"[DONE] {p} load_info={res.get('load_info')}", flush=True)
