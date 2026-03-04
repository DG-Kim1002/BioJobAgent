from github_db import load_jobs_from_github, save_jobs_to_github
import os
import json

print("Checking env token...", bool(os.getenv("GITHUB_TOKEN")))

jobs = load_jobs_from_github()
print(f"Loaded {len(jobs)} jobs initially.")

# modify slightly for testing
if jobs and isinstance(jobs, list):
    jobs[0]["test_db"] = "successful"

save_jobs_to_github(jobs)
print("Saved to GitHub.")

jobs2 = load_jobs_from_github()
print(f"Loaded {len(jobs2)} jobs after save.")
