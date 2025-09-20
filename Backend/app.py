import re
import time
from fastapi import FastAPI, Query
from fastapi.responses import StreamingResponse, JSONResponse
from pydantic import BaseModel
from fastapi.middleware.cors import CORSMiddleware
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager
import io
import csv

# ---------- FastAPI Setup ----------
app = FastAPI(title="Scrynk.io Backend", version="2.2.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:8080",
        "http://127.0.0.1:8080",
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "*"  # allow all for now
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------- Request Schema ----------
class ExtractionRequest(BaseModel):
    email: str | None = None
    password: str | None = None
    post_url: str

# ---------- Scraper Logic ----------
collected_emails: list[str] = []

def login(driver, email, password):
    driver.get("https://www.linkedin.com/login")
    time.sleep(2)
    driver.find_element(By.ID, "username").send_keys(email)
    driver.find_element(By.ID, "password").send_keys(password + Keys.RETURN)
    time.sleep(5)

def load_post(driver, post_url):
    driver.get(post_url)
    time.sleep(5)
    try:
        # Step 1: Click "Most relevant" dropdown
        dropdown_button = WebDriverWait(driver, 10).until(
            EC.element_to_be_clickable((By.XPATH, "//button[contains(., 'Most relevant')]"))
        )
        driver.execute_script("arguments[0].scrollIntoView(true);", dropdown_button)
        dropdown_button.click()
        time.sleep(2)

        # Step 2: Wait for hover menu and select "Most recent"
        most_recent_option = WebDriverWait(driver, 10).until(
            EC.element_to_be_clickable((By.XPATH, "//span[text()='Most recent']"))
        )
        driver.execute_script("arguments[0].scrollIntoView(true);", most_recent_option)
        most_recent_option.click()
        time.sleep(3)

        # ✅ Debug: confirm which filter is active
        current_filter = driver.find_element(
            By.XPATH, "//button[contains(@aria-label,'Sort comments by')]"
        ).text
        print("Current filter:", current_filter)

    except Exception as e:
        print("Could not switch filter:", e)


def extract_emails(driver):
    emails = []
    comments = driver.find_elements(By.CLASS_NAME, "comments-comment-item__main-content")
    for comment in comments:
        text = comment.text
        found = re.findall(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}', text)
        for email in found:
            if email not in collected_emails:
                collected_emails.append(email)
                emails.append(email)
    return emails

def run_extraction(email, password, post_url):
    driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()))
    try:
        if email and password:
            login(driver, email, password)

        load_post(driver, post_url)

        for _ in range(5):  # scroll a few times
            driver.execute_script("window.scrollBy(0, 600);")
            time.sleep(2)
            new_emails = extract_emails(driver)
            if new_emails:
                print("Found:", new_emails)

        return collected_emails
    except Exception as e:
        print("Error:", e)
        return []
    finally:
        driver.quit()

# ---------- API Endpoints ----------
@app.post("/extract/")
def extract_emails_api(request: ExtractionRequest):
    emails = run_extraction(request.email, request.password, request.post_url)
    return {
        "status": "success" if emails else "no emails found",
        "emails": emails,
        "post_url": request.post_url,
    }

@app.get("/download/")
def download_emails(format: str = Query("csv", enum=["csv", "txt"])):
    if not collected_emails:
        return JSONResponse(content={"error": "No emails to download"}, status_code=400)

    if format == "csv":
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(["Email"])
        for email in collected_emails:
            writer.writerow([email])
        output.seek(0)
        return StreamingResponse(
            iter([output.getvalue()]),
            media_type="text/csv",
            headers={"Content-Disposition": "attachment; filename=emails.csv"},
        )
    else:  # txt
        content = "\n".join(collected_emails)
        return StreamingResponse(
            iter([content]),
            media_type="text/plain",
            headers={"Content-Disposition": "attachment; filename=emails.txt"},
        )
