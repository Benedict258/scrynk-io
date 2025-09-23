# app.py
import re
import time
import io
import csv
import traceback
from typing import List, Dict, Optional
from fastapi import FastAPI, Query
from fastapi.responses import StreamingResponse, JSONResponse
from pydantic import BaseModel
from fastapi.middleware.cors import CORSMiddleware
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError, Error as PlaywrightError

# ---------- FastAPI Setup ----------
app = FastAPI(title="Scrynk.io Backend (Playwright)", version="3.2.1")

# NOTE: In production restrict origins to your frontend host(s).
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://scrnk-io-5wyj.onrender.com",  # Add your frontend deployed URL(s)
        "https://scrnk-io.onrender.com",        # another frontend domain if needed
        "http://localhost:3000",                # local dev
        "http://127.0.0.1:3000",
        "*"  # temporary — narrow this in production
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------- Request Schema ----------
class ExtractionRequest(BaseModel):
    email: Optional[str] = None
    password: Optional[str] = None
    post_url: str

# ---------- In-memory storage ----------
collected_data: List[Dict[str, str]] = []  # [{"name": "...", "email": "..."}]
EMAIL_RE = re.compile(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}')

# ---------- Helpers: set comments sort to "Most recent" ----------
def set_sort_to_most_recent(page) -> bool:
    """
    Attempts several strategies to set

    Returns True if verification indicates 'recent' present in UI text,
    else False.
    """
    try:
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
                try:
                    # JS fallback click
                    page.evaluate("(el) => el.click()", dropdown)
                except Exception:
                    pass
            page.wait_for_timeout(400)

        # Try direct "Most recent" click (case variants)
        option = None
        for txt in ("Most recent", "Most Recent"):
            try:
                loc = page.locator(f"text=\"{txt}\"")
                if loc.count() > 0:
                    option = loc.first
                    break
            except Exception:
                continue

        if option:
            option.scroll_into_view_if_needed()
            try:
                option.click(timeout=2000)
            except Exception:
                try:
                    page.evaluate("(el) => el.click()", option)
                except Exception:
                    pass
            page.wait_for_timeout(600)

        # Keyboard fallback: tab/enter loop
        try:
            body = page.locator("body")
            if body.count():
                max_tabs = 12
                for _ in range(max_tabs):
                    body.press("Tab")
                    page.wait_for_timeout(200)
                    active_text = page.evaluate("return document.activeElement ? (document.activeElement.innerText || '') : ''")
                    if active_text and ("most recent" in active_text.lower() or active_text.strip().lower() == "recent"):
                        page.keyboard.press("Enter")
                        page.wait_for_timeout(400)
                        break
                else:
                    # final JS search & click exact matches in spans/divs/links
                    js = """
                    const elems = Array.from(document.querySelectorAll('span,div,a,button'));
                    for (const e of elems) {
                      if (e.innerText && e.innerText.trim().toLowerCase() === 'most recent') {
                        e.click();
                        return true;
                      }
                    }
                    return false;
                    """
                    clicked = False
                    try:
                        clicked = page.evaluate(js)
                    except Exception:
                        clicked = False
                    if clicked:
                        page.wait_for_timeout(400)
        except Exception:
            pass

        # Verify filter changed (heuristic)
        try:
            cand = page.locator("button[aria-label*='Sort comments by'], button:has-text('Most recent'), button:has-text('Most relevant')").first
            if cand and cand.count():
                txt = cand.inner_text().strip().lower()
                if "recent" in txt:
                    return True
        except Exception:
            pass

        # Final heuristic: presence of text node listing Most recent
        try:
            if page.locator("text='Most recent'").count() > 0:
                return True
        except Exception:
            pass

        return False
    except Exception as e:
        print("[set_sort_to_most_recent] exception:", e)
        traceback.print_exc()
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

    # if none matched, try some larger scan fallback (but that's expensive)
    if not containers:
        try:
            containers = page.locator("li, div").all()[:0]
        except Exception:
            containers = []

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
                    ".comments-comment-item__main-content, .comment-body, .feed-shared-update-v2__description"
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

    # page-wide fallback search for emails
    if not results:
        try:
            html = page.content()
            found = list(set(EMAIL_RE.findall(html)))
            for em in found:
                results.append({"name": "(unknown)", "email": em})
        except Exception:
            pass

    return results

def run_extraction_playwright(email: Optional[str], password: Optional[str], post_url: str) -> List[Dict[str, str]]:
    """
    Main synchronous runner using sync_playwright. Returns collected_data list.
    """
    global collected_data
    collected_data = []
    results: List[Dict[str, str]] = []

    try:
        with sync_playwright() as p:
            # Launch - if this fails due to missing browser, it will throw an informative PlaywrightError
            try:
                browser = p.chromium.launch(headless=True, args=["--no-sandbox", "--disable-setuid-sandbox"])
            except PlaywrightError as e:
                # Bubble a clear error up so API returns a helpful message
                raise RuntimeError(f"Playwright failed to launch browser: {e}")

            context = browser.new_context()
            page = context.new_page()
            page.set_default_timeout(20000)

            try:
                if email and password:
                    try:
                        page.goto("https://www.linkedin.com/login", wait_until="networkidle")
                        # attempt common login fields
                        try:
                            page.fill("#username", email)
                            page.fill("#password", password)
                        except Exception:
                            # alternative input names
                            try:
                                page.fill("input[name='session_key']", email)
                                page.fill("input[name='session_password']", password)
                            except Exception:
                                pass
                        page.keyboard.press("Enter")
                        page.wait_for_load_state("networkidle")
                        time.sleep(1.2)
                    except Exception:
                        # don't fail hard if login flow changes; we try to proceed to the post
                        pass

                # Navigate to post URL
                page.goto(post_url, wait_until="networkidle")
                time.sleep(1.0)

                ok = set_sort_to_most_recent(page)
                if not ok:
                    print("[warn] Could not confirm 'Most recent' sort. Continuing anyway.")

                # Scroll/extract loop
                iterations = 6
                for _ in range(iterations):
                    page.evaluate("window.scrollBy(0, 700)")
                    page.wait_for_timeout(1200)
                    batch = extract_from_page(page)
                    for r in batch:
                        if r not in collected_data:
                            collected_data.append(r)
                            results.append(r)

                # final pass
                page.wait_for_timeout(700)
                final_batch = extract_from_page(page)
                for r in final_batch:
                    if r not in collected_data:
                        collected_data.append(r)
                        results.append(r)

            finally:
                try:
                    context.close()
                    browser.close()
                except Exception:
                    pass

    except PlaywrightTimeoutError as e:
        print("Playwright timeout:", e)
    except RuntimeError as e:
        # Re-raise runtime error with clear context
        print("Runtime error during Playwright run:", e)
        raise
    except Exception as e:
        print("Unexpected extraction error:", e)
        traceback.print_exc()

    return collected_data

# ---------- API Endpoints ----------
@app.post("/extract/")
def extract_emails_api(request: ExtractionRequest):
    """
    Triggers a synchronous Playwright extraction.
    Note: this blocks the worker thread while Playwright runs.
    """
    try:
        data = run_extraction_playwright(request.email, request.password, request.post_url)
        return {
            "status": "success" if data else "no data found",
            "results": data,
            "post_url": request.post_url,
        }
    except RuntimeError as e:
        # Likely Playwright couldn't launch browser (missing binary). Return helpful JSON.
        return JSONResponse(
            status_code=500,
            content={
                "status": "error",
                "message": str(e),
                "hint": "Ensure Playwright browsers are installed on the host (run `playwright install chromium`) and that the process can spawn subprocesses."
            },
        )
    except Exception as e:
        print("extract_emails_api unexpected:", e)
        traceback.print_exc()
        return JSONResponse(status_code=500, content={"status": "error", "message": "Unexpected server error"})

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
