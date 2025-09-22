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
app = FastAPI(title="Scrynk.io Backend (Playwright)", version="3.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:8080",
        "http://127.0.0.1:8080",
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "*"  # Narrow this in production (use your real frontend origin)
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

# ---------- In-memory storage for last run ----------
collected_data: List[Dict[str, str]] = []  # [{"name": "...", "email": "..."}]

EMAIL_RE = re.compile(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}')

# ---------- Helpers: set comments sort to "Most recent" ----------
def set_sort_to_most_recent(page) -> bool:
    """
    Attempts multiple strategies to set comment sort to 'Most recent'.
    Returns True if verification indicates 'recent' present in UI text.
    """
    try:
        # 1) Try common dropdown/button selectors and click
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
                # fallback: try JS click
                page.evaluate("(el) => el.click()", dropdown)

            page.wait_for_timeout(400)  # allow hover/menu to appear

        # 2) Direct click on the 'Most recent' text
        try:
            # case-insensitive: try both lowercase and title-case
            option = None
            for txt in ("Most recent", "Most Recent", "Most recent"):
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
        except Exception:
            pass

        # 3) Keyboard fallback (TAB until active element contains 'Most recent', press Enter)
        try:
            body = page.locator("body")
            if body.count():
                max_tabs = 12
                found = False
                for _ in range(max_tabs):
                    body.press("Tab")
                    page.wait_for_timeout(200)
                    active_text = page.evaluate("return document.activeElement ? document.activeElement.innerText || '' : ''")
                    if active_text and ("most recent" in active_text.lower() or "recent" == active_text.strip().lower()):
                        page.keyboard.press("Enter")
                        page.wait_for_timeout(500)
                        found = True
                        break
                if not found:
                    # JS fallback: find span elements and click one exactly matching 'most recent'
                    js = """
                    const spans = Array.from(document.querySelectorAll('span,div,a'));
                    for (const s of spans) {
                        if (s.innerText && s.innerText.trim().toLowerCase() === 'most recent') {
                            s.click();
                            return true;
                        }
                    }
                    return false;
                    """
                    clicked = page.evaluate(js)
                    if clicked:
                        page.wait_for_timeout(500)
        except Exception:
            pass

        # 4) Verify filter contains 'recent'
        try:
            cand = page.locator("button[aria-label*='Sort comments by'], button:has-text('Most recent'), button:has-text('Most relevant')").first
            if cand and cand.count():
                txt = cand.inner_text().strip().lower()
                if "recent" in txt:
                    return True
        except Exception:
            pass

        # Final heuristic: existence of a selected option text 'Most recent'
        try:
            if page.locator("text='Most recent'").count() > 0:
                return True
        except Exception:
            pass

        return False
    except Exception as e:
        print("[set_sort_to_most_recent] exception:", e)
        return False


# ---------- Extraction logic ----------
def extract_from_page(page) -> List[Dict[str, str]]:
    results: List[Dict[str, str]] = []
    # Try comment containers common to LinkedIn
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

    # If none found, fallback to scanning sections of the page
    if not containers:
        try:
            containers = page.locator("li, div").all()[:0]
        except Exception:
            containers = []

    for c in containers:
        try:
            name = ""
            # attempt a few name selectors
            try:
                name_loc = c.locator(".comments-post-meta__name-text, .feed-shared-actor__name, a[href*='/in/'], .commenter-name").first
                if name_loc and name_loc.count():
                    name = name_loc.inner_text().strip()
            except Exception:
                name = ""

            # comment text
            content = ""
            try:
                content_loc = c.locator(".comments-comment-item__main-content, .comment-body, .feed-shared-update-v2__description").first
                if content_loc and content_loc.count():
                    content = content_loc.inner_text().strip()
            except Exception:
                # fallback use container text
                try:
                    content = c.inner_text().strip()
                except Exception:
                    content = ""

            if not content:
                continue

            found_emails = EMAIL_RE.findall(content)
            for em in found_emails:
                rec = {"name": name or "(unknown)", "email": em}
                if rec not in results:
                    results.append(rec)
        except Exception:
            continue

    # Extra fallback: search entire page for emails
    if not results:
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
    collected_data = []  # reset for each run
    results: List[Dict[str, str]] = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=["--no-sandbox", "--disable-setuid-sandbox"])
        context = browser.new_context()
        page = context.new_page()
        page.set_default_timeout(20000)

        try:
            # Optionally login
            if email and password:
                try:
                    page.goto("https://www.linkedin.com/login", wait_until="networkidle")
                    page.fill("#username", email)
                    page.fill("#password", password)
                    page.keyboard.press("Enter")
                    page.wait_for_load_state("networkidle")
                    time.sleep(2)
                except Exception:
                    # alternative selectors
                    try:
                        page.fill("input[name='session_key']", email)
                        page.fill("input[name='session_password']", password)
                        page.keyboard.press("Enter")
                        page.wait_for_load_state("networkidle")
                        time.sleep(2)
                    except Exception:
                        pass

            # Go to post URL
            page.goto(post_url, wait_until="networkidle")
            time.sleep(1.2)

            ok = set_sort_to_most_recent(page)
            if not ok:
                print("[run_extraction_playwright] could not confirm 'Most recent' — continuing anyway")

            # Scroll and extract multiple times
            iterations = 6
            for i in range(iterations):
                page.evaluate("window.scrollBy(0, 700)")
                page.wait_for_timeout(1200)
                batch = extract_from_page(page)
                if batch:
                    for r in batch:
                        if r not in collected_data:
                            collected_data.append(r)
                            results.append(r)

            # one final pass
            page.wait_for_timeout(700)
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
    else:  # txt
        content = "\n".join([f"{row.get('name','')} - {row.get('email','')}" for row in collected_data])
        return StreamingResponse(
            iter([content]),
            media_type="text/plain",
            headers={"Content-Disposition": "attachment; filename=contacts.txt"},
        )
