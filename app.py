import streamlit as st
import pandas as pd
import json
import os
from datetime import datetime, date
import time
from dotenv import load_dotenv

# Load env variables (GEMINI_API_KEY)
load_dotenv()

# Import our custom modules
from scraper import run_full_scraping, get_unique_job_key
from gemini import analyze_job_postings_batch
from github_db import (
    load_jobs_from_github as load_jobs, 
    save_jobs_to_github as save_jobs,
    load_metadata_from_github as load_metadata,
    save_metadata_to_github as save_metadata
)

st.set_page_config(page_title="BioJob Agent", page_icon="🧬", layout="wide")

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
        
    if "metadata" not in st.session_state:
        st.session_state.metadata = load_metadata()

    # Make sure every job has a status and migrate legacy
    changes_made_startup = False
    today = date.today()
    
    # 1) Runtime Deduplication immediately on startup
    deduped_jobs = []
    seen_keys = set()
    for job in st.session_state.jobs:
        uid = get_unique_job_key(job.get("title", ""), job.get("company", {}).get("name", ""))
        if uid in seen_keys:
            changes_made_startup = True
            continue
        seen_keys.add(uid)
        deduped_jobs.append(job)
        
    st.session_state.jobs = deduped_jobs

    for job in st.session_state.jobs:
        if job.get("status") == "tracking":
            job["status"] = "Tracking"
            changes_made_startup = True
        elif job.get("status") == "trash":
            job["status"] = "Trash"
            changes_made_startup = True
        elif "status" not in job or job.get("status") not in ["Tracking", "Trash", "auto_trash", "분류 대기 중"]:
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
    
    trashed_jobs = [j for j in st.session_state.jobs if j.get("status") in ("Trash", "auto_trash")]

    # --- Sidebar ---
    with st.sidebar:
        st.header("🛠️ Controls")
        
        last_scraped = st.session_state.metadata.get("last_scraped", "기록 없음")
        st.write(f"🕒 마지막 수집: **{last_scraped}**")
        st.divider()
        
        if st.button("🚀 Run Scraper", use_container_width=True, type="primary"):
            with st.spinner("Scraping Saramin, JobKorea, and Catch..."):
                raw_scraping_results = run_full_scraping()
            
            # 1. API에 보내기 전, 이미 Tracking/Trash에 있는 공고(중복) 필터링
            # 제목과 회사명을 조합한 고유 키를 사용하여 재공고/타 플랫폼 중복 완벽 차단
            existing_keys = {get_unique_job_key(j.get("title", ""), j.get("company", {}).get("name", "")): True for j in st.session_state.jobs}
            new_scraping_results = [r for r in raw_scraping_results if get_unique_job_key(r.get("title", ""), r.get("companyName", "")) not in existing_keys]
            
            if not new_scraping_results:
                st.warning("All scraped jobs are already in your list. No new jobs to analyze.")
            else:
                st.info(f"Scraped {len(raw_scraping_results)} total postings. Found {len(new_scraping_results)} new ones. Passing to Gemini for analysis...")
                
                with st.spinner("LLM Filtering & Information Extraction in progress..."):
                    batch_size = 10
                    new_jobs = []
                    for i in range(0, len(new_scraping_results), batch_size):
                        batch = new_scraping_results[i:i+batch_size]
                        processed_batch = analyze_job_postings_batch(batch)
                        new_jobs.extend(processed_batch)
                        
                        # API 호출량 제한(RPM) 방지를 위한 대기 시간 (무료 버전은 분당 15회 제한)
                        if i + batch_size < len(new_scraping_results):
                            time.sleep(4)
                            
                if new_jobs:
                    # new_jobs에는 이미 중복이 제거된 데이터만 들어옴
                    st.success(f"Processed {len(new_jobs)} new jobs (including auto-trashed)!")
                    st.session_state.jobs = new_jobs + st.session_state.jobs
                    save_jobs(st.session_state.jobs)
                    
                    # Update metadata with current time
                    st.session_state.metadata["last_scraped"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    save_metadata(st.session_state.metadata)
                    st.rerun()
                else:
                    st.warning("No new relevant jobs found after AI filtering.")
                    # Even if no new jobs, the scraping itself was successful
                    st.session_state.metadata["last_scraped"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    save_metadata(st.session_state.metadata)
                    st.rerun()
                
        st.divider()
        st.write(f"Active Jobs: **{len(active_jobs)}**")
        st.write(f"Trashed Jobs: **{len(trashed_jobs)}**")
        
        if trashed_jobs:
            if st.button("🗑️ Empty Trash"):
                st.session_state.jobs = [j for j in st.session_state.jobs if j.get("status") not in ("Trash", "auto_trash")]
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
                            help="상태를 변경하여 Tracking/Trash/auto_trash/분류 대기 중을 전환합니다.",
                            width="small",
                            options=["Tracking", "분류 대기 중", "Trash", "auto_trash"],
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
                        options=["Tracking", "분류 대기 중", "Trash", "auto_trash"],
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
