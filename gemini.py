import os
import json
import uuid
import datetime
import google.generativeai as genai

def get_genai_client():
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        print("Warning: GEMINI_API_KEY is not defined in the environment variables.")
    else:
        genai.configure(api_key=api_key)
    return genai

def analyze_job_postings_batch(scraping_data_batch):
    if not scraping_data_batch:
        return []

    context_list = []
    for index, data in enumerate(scraping_data_batch):
        context = f"""[Job ID: {index}]
Job Title: {data.get('title', '')}
Company Name: {data.get('companyName', '')}
Original Link: {data.get('link', '')}
Deadline String: {data.get('deadline') or '알 수 없음'}"""
        context_list.append(context)

    batch_context = "\n\n".join(context_list)
    today = datetime.datetime.now().strftime("%Y-%m-%d")

    prompt = f"""
Analyze the following batch of job postings and extract details into a structured JSON array format.

{batch_context}

Your task for EACH job posting:
1. Verify Relevance ("isRelevant"): Strictly evaluate if this role and company are relevant to the fields of "Bio, Diagnostics (진단/진단키트), Pharmaceuticals (제약/항체)". If the role is clearly not related (e.g., IT backend for unrelated field, civil engineering, generic management not in a bio company), or if the job title suggests a completely irrelevant industry like tunnel engineering, set this to false. If relevant, set to true.
2. "jobId": You MUST EXACTLY return the "Job ID" number (as an integer) provided in the text block.
3. "summary": Summarize the job role/responsibilities based on the job title into 1-2 concise Korean sentences.
4. "role": Identify the core position or role being hired for.
5. "period": Identify the application deadline and formatting it STRICTLY as "YYYY-MM-DD". Note that today is {today}, so infer the year based on that if the string only has MM/DD. If it is always open, output "상시 채용".
6. "company_location": Estimate or extract the company location (e.g., "서울", "경기", "인천" or "미상").
7. "company_employeeCount": If obvious, provide it; otherwise output "미상".
8. "company_startingSalary": If obvious, provide it; otherwise output "회사 내규에 따름".
9. "company_reviews": Briefly generate what an employee might review based on the company name and bio industry, or output "해당 없음".
10. Do NOT skip any job; you must return an array of JSON objects matching EACH input, even if isRelevant is false.

The output MUST be a valid JSON array of objects. Do not include markdown formatting or backticks around the JSON.
"""

    try:
        client = get_genai_client()
        model = client.GenerativeModel('gemini-2.5-flash', generation_config={"response_mime_type": "application/json"})
        response = model.generate_content(prompt)

        output_text = response.text
        if not output_text:
            raise Exception("No response text from Gemini")

        parsed_data_batch = json.loads(output_text)
        valid_jobs = []

        for parsed_data in parsed_data_batch:
            original_index = parsed_data.get("jobId")
            if not isinstance(original_index, int) or original_index < 0 or original_index >= len(scraping_data_batch):
                print(f"Unknown or missing jobId from Gemini response: {parsed_data}")
                continue

            scraping_data = scraping_data_batch[original_index]

            if parsed_data.get("isRelevant") is False:
                print(f"Skipping irrelevant job (ID: {original_index}): {scraping_data.get('title')} at {scraping_data.get('companyName')}")
                continue

            job = {
                "id": str(uuid.uuid4()),
                "title": parsed_data.get("title") or scraping_data.get("title"),
                "company": {
                    "name": parsed_data.get("company_name") or scraping_data.get("companyName"),
                    "location": parsed_data.get("company_location") or "미상",
                    "employeeCount": parsed_data.get("company_employeeCount") or "미상",
                    "startingSalary": parsed_data.get("company_startingSalary") or "회사 내규에 따름",
                    "reviews": parsed_data.get("company_reviews") or "해당 없음"
                },
                "summary": parsed_data.get("summary") or "요약 정보 없음",
                "role": parsed_data.get("role") or "미상",
                "period": parsed_data.get("period") or "상시 채용",
                "link": scraping_data.get("link"),
                "postedDate": today,
                "status": "분류 대기 중"
            }
            valid_jobs.append(job)

        return valid_jobs

    except Exception as e:
        print(f"Error analyzing job postings batch with Gemini: {e}")
        return []
