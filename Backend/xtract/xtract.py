# xtract/xtract.py
import re
import time
import os
import logging
from typing import Optional
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

EMAIL_RE = re.compile(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}')

class Xtract:
    """
    Xtract: lightweight scraper that extracts emails from LinkedIn post comments.
    Uses Playwright (Chromium) so no chromedriver required.
    """

    def __init__(self, headless: bool = True, timeout: int = 30000):
        self.headless = headless
        self.timeout = timeout  # ms

    def _extract_emails_from_text(self, text: str):
        return set(EMAIL_RE.findall(text or ""))

    def _save_results(self, path: str, emails: set):
        if not emails:
            return
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "a", encoding="utf-8") as f:
            for e in sorted(emails):
                f.write(e + "\n")
        logging.info("Saved %d emails to %s", len(emails), path)

    def _login(self, page, email: str, password: str):
        page.goto("https://www.linkedin.com/login", timeout=self.timeout)
        try:
            page.fill('input#username', email)
            page.fill('input#password', password)
            page.keyboard.press("Enter")
            # wait briefly for post-login indicator
            page.wait_for_selector("header", timeout=10000)
            logging.info("Login step completed (header found).")
        except PlaywrightTimeoutError:
            logging.warning("Login may have failed or took too long.")

    def run(self,
            run_id: str,
            post_url: str,
            username: Optional[str] = None,
            password: Optional[str] = None,
            max_duration: int = 300):
        """
        Runs scraping and writes results to results/{run_id}.txt.
        Returns metadata dict.
        """
        start_ts = time.time()
        collected = set()
        out_path = os.path.join("results", f"{run_id}.txt")

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=self.headless, args=["--no-sandbox"])
            context = browser.new_context()
            page = context.new_page()
            page.set_default_timeout(self.timeout)

            # If provided, attempt login
            if username and password:
                logging.info("Attempting login with provided credentials.")
                self._login(page, username, password)
            else:
                logging.info("No credentials provided; proceeding anonymously.")

            logging.info("Opening post URL: %s", post_url)
            try:
                page.goto(post_url, timeout=self.timeout)
            except Exception as e:
                logging.error("Failed to open URL: %s", e)
                browser.close()
                return {"run_id": run_id, "emails_found": 0, "elapsed_seconds": 0.0, "result_file": out_path, "error": str(e)}

            time.sleep(2)  # let page settle

            # try to switch comment filter to "Most recent" (best-effort)
            try:
                mr = page.locator("div[role='button']:has-text('Most recent')").first
                if mr:
                    try:
                        page.evaluate("arguments[0].click();", mr)
                        logging.info("Tried to set comments to 'Most recent'.")
                        time.sleep(1)
                    except Exception:
                        pass
            except Exception:
                pass

            last_activity = time.time()
            while time.time() - start_ts < max_duration:
                # scroll
                try:
                    page.evaluate("window.scrollBy(0, 800);")
                except Exception:
                    pass
                time.sleep(1.0)

                # click load-more-like buttons (best-effort)
                try:
                    buttons = page.locator("button").all()
                    for b in buttons:
                        try:
                            txt = b.inner_text().lower()
                        except Exception:
                            continue
                        if "more" in txt and "comment" in txt:
                            try:
                                b.click()
                                logging.info("Clicked a 'load more comments' button.")
                                last_activity = time.time()
                                time.sleep(1.2)
                            except Exception:
                                continue
                except Exception:
                    pass

                found = set()
                selectors = [
                    "div.comments-comment-item__main-content",
                    "div.commentary, div.comments-comment-item",
                    "div.feed-shared-comments-list",
                    "article",
                ]
                for sel in selectors:
                    try:
                        nodes = page.locator(sel).all()
                        for n in nodes:
                            try:
                                text = n.inner_text()
                                found.update(self._extract_emails_from_text(text))
                            except Exception:
                                continue
                        if found:
                            break
                    except Exception:
                        continue

                if not found:
                    try:
                        body_text = page.inner_text("body")
                        found.update(self._extract_emails_from_text(body_text))
                    except Exception:
                        pass

                new = found - collected
                if new:
                    collected.update(new)
                    self._save_results(out_path, new)
                    last_activity = time.time()
                    logging.info("New emails found: %s", new)

                if time.time() - last_activity > 90:
                    logging.info("No new activity for 90s — ending extract loop.")
                    break

            # final save in case
            self._save_results(out_path, collected)

            try:
                browser.close()
            except Exception:
                pass

        elapsed = time.time() - start_ts
        return {"run_id": run_id, "emails_found": len(collected), "elapsed_seconds": round(elapsed,2), "result_file": out_path}
