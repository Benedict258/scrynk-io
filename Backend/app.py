# app.py
import re
import time
import io
import csv
from typing import List, Dict
from fastapi import FastAPI, Query
from fastapi.responses import StreamingResponse, JSONResponse
from pydantic import BaseModel
from fastapi.middleware.cors import CORSMiddleware
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError

# ---------- FastAPI Setup ----------
app = FastAPI(title="Scrynk.io Backend (Playwright)", version="3.2.0")

from fastapi.middleware.cors import CORSMiddleware

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://scrnk-io-5wyj.onrender.com",  # your frontend URL
        "http://localhost:3000"  # optional, for local dev
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

# ---------- In-memory storage ----------
collected_data: List[Dict[str, str]] = []  # [{"name": "...", "email": "..."}]
EMAIL_RE = re.compile(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}')

# ---------- Helpers: set comments sort to "Most recent" ----------
def set_sort_to_most_recent(page) -> bool:
    try:
        # Try common dropdown selectors
        dropdown_selectors = [
            "button:has-text('Most relevant')",
            "button[aria-label*='Sort comments by']",
            "button:has-text('Sort comments')",
            "button:has-text('Relevance')",
        ]
        dropdown = None
        for sel in dropdown_selectors:
            try:
                if page.locator(sel).count() > 0:
                    dropdown = page.locator(sel).first
                    break
            except Exception:
                continue

        if dropdown:
            try:
                dropdown.scroll_into_view_if_needed()
                dropdown.click(timeout=3000)
            except Exception:
                page.evaluate("(el) => el.click()", dropdown)
            page.wait_for_timeout(400)

        # Click “Most recent” if visible
        option = None
        for txt in ("Most recent", "Most Recent"):
            loc = page.locator(f"text=\"{txt}\"")
            if loc.count() > 0:
                option = loc.first
                break
        if option:
            option.scroll_into_view_if_needed()
            try:
                option.click(timeout=2000)
            except Exception:
                page.evaluate("(el) => el.click()", option)
            page.wait_for_timeout(600)

        # Verify
        cand = page.locator(
            "button[aria-label*='Sort comments by'], "
            "button:has-text('Most recent'), "
            "button:has-text('Most relevant')"
        ).first
        if cand and cand.count():
            txt = cand.inner_text().strip().lower()
            if "recent" in txt:
                return True

        return page.locator("text='Most recent'").count() > 0
    except Exception as e:
        print("[set_sort_to_most_recent] exception:", e)
        return False

# ---------- Extraction ----------
def extract_from_page(page) -> List[Dict[str, str]]:
    results: List[Dict[str, str]] = []
    container_selectors = [
        ".comments-comment-item",
        "li.comments-comment-item",
        ".comment",
        ".comments-comment-item__main-content"
    ]
    containers = []
    for sel in container_selectors:
        try:
            locs = page.locator(sel).all()
            if locs:
                containers = locs
                break
        except Exception:
            continue

    for c in containers:
        try:
            name = ""
            try:
                name_loc = c.locator(
                    ".comments-post-meta__name-text, "
                    ".feed-shared-actor__name, "
                    "a[href*='/in/'], "
                    ".commenter-name"
                ).first
                if name_loc and name_loc.count():
                    name = name_loc.inner_text().strip()
            except Exception:
                pass

            content = ""
            try:
                content_loc = c.locator(
                    ".comments-comment-item__main-content, "
                    ".comment-body, "
                    ".feed-shared-update-v2__description"
                ).first
                if content_loc and content_loc.count():
                    content = content_loc.inner_text().strip()
            except Exception:
                try:
                    content = c.inner_text().strip()
                except Exception:
                    pass

            if not content:
                continue

            found_emails = EMAIL_RE.findall(content)
            for em in found_emails:
                rec = {"name": name or "(unknown)", "email": em}
                if rec not in results:
                    results.append(rec)
        except Exception:
            continue

    if not results:  # fallback search
        try:
            html = page.content()
            found = list(set(EMAIL_RE.findall(html)))
            for em in found:
                results.append({"name": "(unknown)", "email": em})
        except Exception:
            pass

    return results

def run_extraction_playwright(email: str | None, password: str | None, post_url: str) -> List[Dict[str, str]]:
    global collected_data
    collected_data = []
    results: List[Dict[str, str]] = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=["--no-sandbox", "--disable-setuid-sandbox"])
        context = browser.new_context()
        page = context.new_page()
        page.set_default_timeout(20000)

        try:
            # Optional login
            if email and password:
                try:
                    page.goto("https://www.linkedin.com/login", wait_until="networkidle")
                    page.fill("#username", email)
                    page.fill("#password", password)
                    page.keyboard.press("Enter")
                    page.wait_for_load_state("networkidle")
                    time.sleep(2)
                except Exception:
                    pass

            # Open post
            page.goto(post_url, wait_until="networkidle")
            time.sleep(1.2)

            ok = set_sort_to_most_recent(page)
            if not ok:
                print("[warn] Could not confirm 'Most recent'")

            # Scroll and extract
            for _ in range(6):
                page.evaluate("window.scrollBy(0, 700)")
                page.wait_for_timeout(1200)
                batch = extract_from_page(page)
                for r in batch:
                    if r not in collected_data:
                        collected_data.append(r)
                        results.append(r)

            final_batch = extract_from_page(page)
            for r in final_batch:
                if r not in collected_data:
                    collected_data.append(r)
                    results.append(r)

        except PlaywrightTimeoutError as e:
            print("Playwright timeout:", e)
        except Exception as e:
            print("Unexpected extraction error:", e)
        finally:
            try:
                context.close()
                browser.close()
            except Exception:
                pass

    return collected_data

# ---------- API Endpoints ----------
@app.post("/extract/")
def extract_emails_api(request: ExtractionRequest):
    data = run_extraction_playwright(request.email, request.password, request.post_url)
    return {
        "status": "success" if data else "no data found",
        "results": data,
        "post_url": request.post_url,
    }

@app.get("/download/")
def download_emails(format: str = Query("csv", enum=["csv", "txt"])):
    if not collected_data:
        return JSONResponse(content={"error": "No data to download"}, status_code=400)

    if format == "csv":
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(["Name", "Email"])
        for row in collected_data:
            writer.writerow([row.get("name", ""), row.get("email", "")])
        output.seek(0)
        return StreamingResponse(
            iter([output.getvalue()]),
            media_type="text/csv",
            headers={"Content-Disposition": "attachment; filename=contacts.csv"},
        )
    else:
        content = "\n".join([f"{row.get('name','')} - {row.get('email','')}" for row in collected_data])
        return StreamingResponse(
            iter([content]),
            media_type="text/plain",
            headers={"Content-Disposition": "attachment; filename=contacts.txt"},
        )
