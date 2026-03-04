import os
import json
import base64
import requests
import streamlit as st

# Function to get the token, checking Streamlit Secrets first, then local Env.
def get_github_token():
    try:
        if "GITHUB_TOKEN" in st.secrets:
            return st.secrets["GITHUB_TOKEN"]
    except:
        pass
    return os.getenv("GITHUB_TOKEN")

REPO_OWNER = "DG-Kim1002"
REPO_NAME = "BioJobAgent"
FILE_PATH = "jobs.json"
BRANCH = "db"

def get_headers():
    token = get_github_token()
    if not token:
        return None
    return {
        "Authorization": f"token {token}",
        "Accept": "application/vnd.github.v3+json"
    }

def init_db_branch_if_missing():
    headers = get_headers()
    if not headers:
        return

    # Check if branch exists
    url = f"https://api.github.com/repos/{REPO_OWNER}/{REPO_NAME}/branches/{BRANCH}"
    res = requests.get(url, headers=headers)
    if res.status_code == 200:
        return # Branch exists
    
    # Needs to create branch. Get main branch SHA
    main_url = f"https://api.github.com/repos/{REPO_OWNER}/{REPO_NAME}/git/refs/heads/main"
    main_res = requests.get(main_url, headers=headers)
    if main_res.status_code == 200:
        main_sha = main_res.json()["object"]["sha"]
        # Create db branch
        create_url = f"https://api.github.com/repos/{REPO_OWNER}/{REPO_NAME}/git/refs"
        requests.post(create_url, headers=headers, json={
            "ref": f"refs/heads/{BRANCH}",
            "sha": main_sha
        })

def get_file_sha_and_content():
    headers = get_headers()
    if not headers:
        return None, None
        
    url = f"https://api.github.com/repos/{REPO_OWNER}/{REPO_NAME}/contents/{FILE_PATH}?ref={BRANCH}"
    response = requests.get(url, headers=headers)
    
    if response.status_code == 200:
        data = response.json()
        sha = data['sha']
        content = base64.b64decode(data['content']).decode('utf-8')
        return sha, content
    return None, None

def load_jobs_from_github():
    token = get_github_token()
    
    if token:
        try:
            init_db_branch_if_missing()
            _, content = get_file_sha_and_content()
            if content:
                # Also save locally as cache
                with open("jobs.json", "w", encoding="utf-8") as f:
                    f.write(content)
                return json.loads(content)
        except Exception as e:
            print("Error loading from GitHub:", e)

    # Fallback to local
    if os.path.exists("jobs.json"):
        try:
            with open("jobs.json", "r", encoding="utf-8") as f:
                return json.load(f)
        except:
            return []
    return []

def save_jobs_to_github(jobs_list):
    # Always save locally as a backup/cache
    with open("jobs.json", "w", encoding="utf-8") as f:
        json.dump(jobs_list, f, ensure_ascii=False, indent=2)

    token = get_github_token()
    if not token:
        print("No GitHub token found, skipping remote save.")
        return

    try:
        init_db_branch_if_missing()
        sha, current_content = get_file_sha_and_content()
        
        # Don't push if the content hasn't actually changed
        new_content_str = json.dumps(jobs_list, ensure_ascii=False, indent=2)
        if current_content and new_content_str == current_content:
            return

        url = f"https://api.github.com/repos/{REPO_OWNER}/{REPO_NAME}/contents/{FILE_PATH}"
        headers = get_headers()
        
        content_bytes = new_content_str.encode('utf-8')
        encoded_content = base64.b64encode(content_bytes).decode('utf-8')
        
        payload = {
            "message": "Update jobs.json via Streamlit UI",
            "content": encoded_content,
            "branch": BRANCH
        }
        if sha:
            payload["sha"] = sha
            
        res = requests.put(url, headers=headers, json=payload)
        if res.status_code not in [200, 201]:
             print("Failed to save to github", res.text)
    except Exception as e:
        print("Error saving to GitHub:", e)
