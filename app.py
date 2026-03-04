import streamlit as st
import pandas as pd
import json
import os
from datetime import datetime, date
from dotenv import load_dotenv

# Load env variables (GEMINI_API_KEY)
load_dotenv()

# Import our custom modules
from scraper import run_full_scraping
from gemini import analyze_job_postings_batch

# Constants
JOBS_FILE = "jobs.json"

st.set_page_config(page_title="BioJob Agent", page_icon="🧬", layout="wide")

def load_jobs():
    if os.path.exists(JOBS_FILE):
        try:
            with open(JOBS_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return []
    return []

def save_jobs(jobs_list):
    with open(JOBS_FILE, "w", encoding="utf-8") as f:
        json.dump(jobs_list, f, ensure_ascii=False, indent=2)

def calculate_dday_cell(deadline_str):
    if deadline_str == "상시 채용" or not str(deadline_str).strip():
        return "상시"
    try:
        d = datetime.strptime(str(deadline_str), "%Y-%m-%d").date()
        today = date.today()
        diff = (d - today).days
        if diff < 0:
            return f"D+{abs(diff)}"
        elif diff == 0:
            return "D-Day"
        else:
            return f"D-{diff}"
    except:
        return "-"

def get_dday_sort_value(deadline_str):
    if deadline_str == "상시 채용" or not str(deadline_str).strip():
        return 99999
    try:
        d = datetime.strptime(str(deadline_str), "%Y-%m-%d").date()
        today = date.today()
        return (d - today).days
    except:
        return 99999

def main():
    st.title("🧬 BioJob Agent")
    st.markdown("바이오/제약 산업 채용공고 자동 수집 및 필터링 시스템")

    if "jobs" not in st.session_state:
        st.session_state.jobs = load_jobs()

    # Make sure every job has a status and migrate legacy
    changes_made_startup = False
    today = date.today()
    for job in st.session_state.jobs:
        if job.get("status") == "tracking":
            job["status"] = "Tracking"
            changes_made_startup = True
        elif job.get("status") == "trash":
            job["status"] = "Trash"
            changes_made_startup = True
        elif "status" not in job or job.get("status") not in ["Tracking", "Trash", "분류 대기 중"]:
            job["status"] = "분류 대기 중"
            changes_made_startup = True
            
        # Auto-Trash logic for D-day elapsed jobs
        if job.get("status") in ("Tracking", "분류 대기 중"):
            deadline_str = job.get("period", "")
            if deadline_str != "상시 채용" and str(deadline_str).strip():
                try:
                    d = datetime.strptime(str(deadline_str), "%Y-%m-%d").date()
                    if (d - today).days < 0:
                        job["status"] = "Trash"
                        changes_made_startup = True
                except:
                    pass

    if changes_made_startup:
        save_jobs(st.session_state.jobs)

    # Sort active jobs: 1. Tracking first, 2. Deadline short->long
    active_jobs = [j for j in st.session_state.jobs if j.get("status") in ("Tracking", "분류 대기 중")]
    active_jobs.sort(key=lambda j: (
        0 if j.get("status") == "Tracking" else 1, 
        get_dday_sort_value(j.get("period", ""))
    ))
    
    trashed_jobs = [j for j in st.session_state.jobs if j.get("status") == "Trash"]

    # --- Sidebar ---
    with st.sidebar:
        st.header("🛠️ Controls")
        
        if st.button("🚀 Run Scraper", use_container_width=True, type="primary"):
            with st.spinner("Scraping Saramin, JobKorea, and Catch..."):
                raw_scraping_results = run_full_scraping()
            
            st.info(f"Scraped {len(raw_scraping_results)} raw postings. Passing to Gemini for analysis...")
            
            with st.spinner("LLM Filtering & Information Extraction in progress..."):
                batch_size = 10
                new_jobs = []
                for i in range(0, len(raw_scraping_results), batch_size):
                    batch = raw_scraping_results[i:i+batch_size]
                    processed_batch = analyze_job_postings_batch(batch)
                    new_jobs.extend(processed_batch)
                    
            if new_jobs:
                existing_links = {j.get("link"): True for j in st.session_state.jobs}
                filtered_new_jobs = [j for j in new_jobs if j.get("link") not in existing_links]
                
                if filtered_new_jobs:
                    st.success(f"Added {len(filtered_new_jobs)} new relevant jobs!")
                    st.session_state.jobs = filtered_new_jobs + st.session_state.jobs
                    save_jobs(st.session_state.jobs)
                    st.rerun()
                else:
                    st.warning("All scraped jobs were duplicates.")
            else:
                st.warning("No new relevant jobs found.")
                
        st.divider()
        st.write(f"Active Jobs: **{len(active_jobs)}**")
        st.write(f"Trashed Jobs: **{len(trashed_jobs)}**")
        
        if trashed_jobs:
            if st.button("🗑️ Empty Trash"):
                st.session_state.jobs = [j for j in st.session_state.jobs if j.get("status") != "Trash"]
                save_jobs(st.session_state.jobs)
                st.rerun()
                
        if st.session_state.jobs:
            if st.button("⚠️ Clear All Data"):
                st.session_state.jobs = []
                save_jobs([])
                st.rerun()

    # --- Main Content ---
    if not st.session_state.jobs:
        st.info("No jobs to display. Click 'Run Scraper' on the sidebar to fetch data!")
        return

    # Tabs for Active Tracking vs Trash
    tab1, tab2 = st.tabs(["📌 Tracking Jobs", "🗑️ Trash Bin"])

    with tab1:
        if not active_jobs:
            st.warning("No active jobs currently tracking.")
        else:
            # Search Bar
            search_term = st.text_input("🔍 Search Company or Title:", "")
            
            # Prepare dataframe for Data Editor
            df_data = []
            for j in active_jobs:
                company = j.get("company", {})
                
                if search_term and search_term.lower() not in j.get("title", "").lower() and search_term.lower() not in company.get("name", "").lower():
                    continue
                    
                df_data.append({
                    "_id": j.get("id", ""), 
                    "Status": j.get("status", "분류 대기 중"),
                    "🏢 Company": company.get("name", ""),
                    "📝 Title": j.get("title", ""),
                    "⏳ D-Day": calculate_dday_cell(j.get("period", "")),
                    "⏱️ Deadline": j.get("period", ""),
                    "📍 Location": company.get("location", ""),
                    "👥 Employees": company.get("employeeCount", ""),
                    "🔗 Link": j.get("link", "")
                })
                
            if df_data:
                df = pd.DataFrame(df_data)
                
                def row_style(row):
                    styles = [''] * len(row)
                    is_tracking = row['Status'] == 'Tracking'
                    
                    # Highlight Tracking Rows
                    bg_color = 'background-color: rgba(144, 238, 144, 0.2);' if is_tracking else ''
                    for i in range(len(row)):
                        styles[i] = bg_color
                    
                    # Highlight Danger D-Day < 7
                    dday_str = str(row['⏳ D-Day'])
                    if dday_str.startswith("D-") and dday_str != "D-Day":
                        try:
                            days_left = int(dday_str.split('-')[1])
                            if days_left <= 7:
                                col_idx_dday = df.columns.get_loc('⏳ D-Day')
                                styles[col_idx_dday] += 'color: #ff4b4b; font-weight: bold;'
                        except: pass
                    elif dday_str == "D-Day" or dday_str.startswith("D+"):
                        col_idx_dday = df.columns.get_loc('⏳ D-Day')
                        styles[col_idx_dday] += 'color: #ff4b4b; font-weight: bold;'
                        
                    return styles
                
                styled_df = df.style.apply(row_style, axis=1)
                
                edited_df = st.data_editor(
                    styled_df,
                    column_config={
                        "_id": None, 
                        "Status": st.column_config.SelectboxColumn(
                            "Status",
                            help="상태를 변경하여 Tracking/Trash/분류 대기 중을 전환합니다.",
                            width="small",
                            options=["Tracking", "분류 대기 중", "Trash"],
                            required=True,
                        ),
                        "🏢 Company": st.column_config.TextColumn("Company", disabled=True),
                        "📝 Title": st.column_config.TextColumn("Title", disabled=True),
                        "⏳ D-Day": st.column_config.TextColumn("D-Day", disabled=True, width="small"),
                        "⏱️ Deadline": st.column_config.TextColumn("Deadline", width="small"),
                        "📍 Location": st.column_config.TextColumn("Location"),
                        "👥 Employees": st.column_config.TextColumn("Employees", width="small"),
                        "🔗 Link": st.column_config.LinkColumn("Apply Link", display_text="Link", disabled=True)
                    },
                    hide_index=True,
                    use_container_width=True,
                    key="active_editor"
                )

                changes_made = False
                if not edited_df.equals(df):
                    for index, row in edited_df.iterrows():
                        job_id = row["_id"]
                        
                        for session_job in st.session_state.jobs:
                            if session_job.get("id") == job_id:
                                if session_job.get("status") != row["Status"]:
                                    session_job["status"] = row["Status"]
                                    changes_made = True
                                
                                if session_job.get("period") != row["⏱️ Deadline"]:
                                    session_job["period"] = row["⏱️ Deadline"]
                                    changes_made = True
                                    
                                if session_job.get("company", {}).get("location") != row["📍 Location"]:
                                    if "company" not in session_job: session_job["company"] = {}
                                    session_job["company"]["location"] = row["📍 Location"]
                                    changes_made = True
                                    
                                if session_job.get("company", {}).get("employeeCount") != row["👥 Employees"]:
                                    if "company" not in session_job: session_job["company"] = {}
                                    session_job["company"]["employeeCount"] = row["👥 Employees"]
                                    changes_made = True

                    if changes_made:
                        save_jobs(st.session_state.jobs)
                        st.rerun()

    with tab2:
        if not trashed_jobs:
            st.info("Trash bin is empty.")
        else:
            df_trash = []
            for j in trashed_jobs:
                company = j.get("company", {})
                df_trash.append({
                    "_id": j.get("id", ""), 
                    "Status": j.get("status", "Trash"),
                    "🏢 Company": company.get("name", ""),
                    "📝 Title": j.get("title", ""),
                })
                
            df_t = pd.DataFrame(df_trash)
            
            edited_trash_df = st.data_editor(
                df_t,
                column_config={
                    "_id": None, 
                    "Status": st.column_config.SelectboxColumn(
                        "Status",
                        help="Restore job",
                        options=["Tracking", "분류 대기 중", "Trash"],
                        required=True,
                    ),
                    "🏢 Company": st.column_config.TextColumn("Company", disabled=True),
                    "📝 Title": st.column_config.TextColumn("Title", disabled=True),
                },
                hide_index=True,
                use_container_width=True,
                key="trash_editor"
            )
            
            if not edited_trash_df.equals(df_t):
                changes_made_trash = False
                for index, row in edited_trash_df.iterrows():
                    job_id = row["_id"]
                    
                    for session_job in st.session_state.jobs:
                        if session_job.get("id") == job_id:
                            new_status = row["Status"]
                            if session_job.get("status") != new_status:
                                session_job["status"] = new_status
                                changes_made_trash = True
                
                if changes_made_trash:
                    save_jobs(st.session_state.jobs)
                    st.rerun()

if __name__ == "__main__":
    main()
