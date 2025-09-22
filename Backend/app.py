import re
import time
import csv
from io import StringIO
from fastapi import FastAPI
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from fastapi.middleware.cors import CORSMiddleware
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support.ui import WebDriverWait
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.support import expected_conditions as EC

# ---------- FastAPI Setup ----------
app = FastAPI(title="Scrynk.io Backend", version="2.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # allow all for dev
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------- Request Schema ----------
class ExtractionRequest(BaseModel):
    email: str
    password: str
    post_url: str

# ---------- Global storage ----------
collected_emails = []

# ---------- Scraper Logic ----------
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
        # Click the filter button
        filter_button = WebDriverWait(driver, 10).until(
            EC.element_to_be_clickable((By.XPATH, "//button[contains(., 'Most relevant')]"))
        )
        filter_button.click()
        time.sleep(1)
        # Switch to "Most recent"
        most_recent = WebDriverWait(driver, 5).until(
            EC.element_to_be_clickable((By.XPATH, "//span[text()='Most recent']/ancestor::div[@role='button']"))
        )
        driver.execute_script("arguments[0].click();", most_recent)
        print("Switched to Most recent comments ✅")
        time.sleep(3)
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
        login(driver, email, password)
        load_post(driver, post_url)

        for _ in range(5):  # scroll & load comments
            driver.execute_script("window.scrollBy(0, 800);")
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
def download_emails(format: str = "csv"):
    if not collected_emails:
        return {"error": "No emails collected yet."}

    if format == "txt":
        content = "\n".join(collected_emails)
        file_name = "emails.txt"
        media_type = "text/plain"
    else:  # default CSV
        output = StringIO()
        writer = csv.writer(output)
        writer.writerow(["Email"])
        for email in collected_emails:
            writer.writerow([email])
        content = output.getvalue()
        file_name = "emails.csv"
        media_type = "text/csv"

    return StreamingResponse(
        iter([content]),
        media_type=media_type,
        headers={"Content-Disposition": f"attachment; filename={file_name}"}
    )
