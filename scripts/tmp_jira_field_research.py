import json
import os

import requests

base = os.getenv("JIRA_BASE_URL", "").rstrip("/")
auth = (os.getenv("JIRA_USER_EMAIL"), os.getenv("JIRA_API_TOKEN"))

projects = {
    "TWBACKEND": [
        "TWBACKEND-156",
        "TWBACKEND-6",
        "TWBACKEND-170",
        "TWBACKEND-131",
        "TWBACKEND-139",
        "TWBACKEND-113",
        "TWBACKEND-209",
        "TWBACKEND-198",
        "TWBACKEND-141",
        "TWBACKEND-211",
        "TWBACKEND-204",
        "TWBACKEND-313",
        "TWBACKEND-248",
        "TWBACKEND-194",
        "TWBACKEND-247",
        "TWBACKEND-234",
        "TWBACKEND-280",
        "TWBACKEND-299",
        "TWBACKEND-260",
        "TWBACKEND-232",
    ],
    "TWMOB": [
        "TWMOB-2170",
        "TWMOB-2168",
        "TWMOB-2017",
        "TWMOB-2158",
        "TWMOB-2124",
        "TWMOB-2172",
        "TWMOB-2156",
        "TWMOB-2140",
        "TWMOB-2208",
        "TWMOB-2196",
        "TWMOB-2210",
        "TWMOB-2223",
        "TWMOB-2323",
        "TWMOB-2219",
        "TWMOB-2202",
        "TWMOB-2403",
        "TWMOB-2354",
        "TWMOB-2289",
        "TWMOB-2287",
        "TWMOB-2083",
        "TWMOB-1931",
        "TWMOB-2450",
        "TWMOB-2329",
        "TWMOB-2278",
        "TWMOB-2149",
    ],
    "TWWB": [
        "TWWB-307",
        "TWWB-1588",
        "TWWB-1617",
        "TWWB-1635",
        "TWWB-1607",
        "TWWB-1674",
        "TWWB-1717",
        "TWWB-1692",
        "TWWB-1643",
        "TWWB-631",
        "TWWB-190",
        "TWWB-308",
        "TWWB-1789",
        "TWWB-1776",
        "TWWB-1782",
        "TWWB-1727",
        "TWWB-1792",
        "TWWB-1613",
        "TWWB-1639",
        "TWWB-1811",
    ],
}

field_list = "summary,customfield_10036,customfield_10016,customfield_10187"
out = {}

for prj, keys in projects.items():
    rec = {
        "total": 0,
        "cf10036_non_null": 0,
        "cf10016_non_null": 0,
        "cf10187_non_null": 0,
        "errors": 0,
        "examples": [],
    }

    for key in keys:
        r = requests.get(
            f"{base}/rest/api/3/issue/{key}",
            params={"fields": field_list},
            auth=auth,
            headers={"Accept": "application/json"},
            timeout=60,
        )
        if r.status_code != 200:
            rec["errors"] += 1
            continue

        data = r.json()
        fields = data.get("fields", {})
        v36 = fields.get("customfield_10036")
        v16 = fields.get("customfield_10016")
        v187 = fields.get("customfield_10187")

        rec["total"] += 1
        rec["cf10036_non_null"] += int(v36 is not None)
        rec["cf10016_non_null"] += int(v16 is not None)
        rec["cf10187_non_null"] += int(v187 is not None)

        if len(rec["examples"]) < 12:
            rec["examples"].append(
                {
                    "key": data.get("key", key),
                    "cf10036": v36,
                    "cf10016": v16,
                    "cf10187": v187,
                }
            )

    out[prj] = rec

print(json.dumps(out, ensure_ascii=False, indent=2))
