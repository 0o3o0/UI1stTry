from __future__ import annotations
from dataclasses import dataclass, asdict
from typing import List, Dict, Optional, Callable
import time
import random
import pandas as pd

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import (
    TimeoutException,
    NoSuchElementException,
    StaleElementReferenceException,
)


# =========================
# CONFIG & TYPES
# =========================

@dataclass
class ScraperConfig:
    email: str
    password: str
    base_search_url: str
    start_page: int = 1
    end_page: int = 1
    scroll_pause: float = 2.0
    page_load_sleep: float = 3.0
    output_csv_path: Optional[str] = "linkedin_leads.csv"
    headless: bool = False

    # כמה לוגים להדפיס (false אם נחבר ל-UI ונרצה שקט)
    verbose: bool = True


Profile = Dict[str, str]
Result = Dict[str, str]
LogFn = Callable[[str], None]


# =========================
# MAIN SCRAPER CLASS
# =========================

class LinkedInScraper:
    """
    LinkedIn scraper + connection requester.
    מיועד לשימוש כתשתית מאחורי UI / API – בלי לגעת בלוגיקה העסקית.
    """

    def __init__(self, config: ScraperConfig, logger: Optional[LogFn] = None):
        self.config = config
        self.driver: Optional[webdriver.Chrome] = None
        self.wait: Optional[WebDriverWait] = None

        # לוגger – אפשר לחבר ל-UI, לקובץ, או רק print
        if logger is None:
            self.log = print
        else:
            self.log = logger

        self.profiles: List[Profile] = []
        self.results: List[Result] = []

    # ---------- DRIVER SETUP ----------

    def _create_driver(self) -> None:
        options = webdriver.ChromeOptions()
        options.add_argument("--start-maximized")
        if self.config.headless:
            options.add_argument("--headless=new")
        # אפשר להוסיף user-agent / פרופיל כרום וכו'

        self.driver = webdriver.Chrome(options=options)
        self.wait = WebDriverWait(self.driver, 15)

    # ---------- LOGIN ----------

    def login(self) -> None:
        assert self.driver is not None and self.wait is not None, "Driver not initialized"
        self.log("🔐 Logging into LinkedIn...")
        self.driver.get("https://www.linkedin.com/login")

        self.wait.until(EC.presence_of_element_located((By.ID, "username"))).send_keys(
            self.config.email
        )
        self.driver.find_element(By.ID, "password").send_keys(self.config.password)
        self.driver.find_element(By.CSS_SELECTOR, "button[type='submit']").click()

        try:
            self.wait.until(lambda d: "feed" in d.current_url)
            self.log("✅ Login successful")
        except TimeoutException:
            self.log("⚠️ Login may have failed; proceeding anyway...")

    # ---------- PHASE 1: SCRAPE PROFILES ----------

    def scrape_search_pages(self) -> List[Profile]:
        """
        עובר על עמודי החיפוש ומוציא:
        Name, Title, LinkedIn URL
        """
        assert self.driver is not None, "Driver not initialized"

        self.profiles = []  # reset

        for page in range(self.config.start_page, self.config.end_page + 1):
            url = f"{self.config.base_search_url}&page={page}"
            self.log(f"📄 Loading search page {page}: {url}")

            self.driver.get(url)
            # scroll to bottom to load all cards
            self.driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            time.sleep(self.config.scroll_pause + random.random())

            cards = self.driver.find_elements(
                By.CSS_SELECTOR,
                "div[data-view-name='search-entity-result-universal-template']",
            )
            self.log(f"🔎 Found {len(cards)} profile cards on page {page}")

            for card in cards:
                try:
                    link_elem = card.find_element(
                        By.CSS_SELECTOR, "a[data-test-app-aware-link]"
                    )
                    link = link_elem.get_attribute("href").split("?")[0]

                    name = card.find_element(
                        By.CSS_SELECTOR, "span.t-16 span[aria-hidden='true']"
                    ).text.strip()

                    # title / subtitle
                    try:
                        title = card.find_element(
                            By.CSS_SELECTOR, "div.entity-result__primary-subtitle"
                        ).text.strip()
                    except NoSuchElementException:
                        try:
                            title = card.find_element(
                                By.CSS_SELECTOR, "div.t-black--light"
                            ).text.strip()
                        except NoSuchElementException:
                            title = "N/A"

                    profile = {"Name": name, "Title": title, "LinkedIn URL": link}
                    self.profiles.append(profile)
                    if self.config.verbose:
                        self.log(f"▶️ Scraped: {name} | {title} | {link}")
                except Exception as e:
                    self.log(f"❌ Error scraping card: {e}")

        return self.profiles

    # ---------- DEBUG: PRINT BUTTONS (OPTIONAL) ----------

    def _debug_print_buttons(self) -> None:
        """Optionally print all buttons on current page – טוב לטסטים/דיבאג."""
        assert self.driver is not None
        try:
            buttons = self.driver.find_elements(By.TAG_NAME, "button")
            for i in range(len(buttons)):
                try:
                    btn = self.driver.find_elements(By.TAG_NAME, "button")[i]
                    txt = btn.text.strip()
                    aria = btn.get_attribute("aria-label") or ""
                    if txt or aria:
                        self.log(f"    ▶️ text={txt!r}, aria_label={aria!r}")
                except StaleElementReferenceException:
                    self.log("    ⚠️ Skipped stale button.")
                except Exception as e:
                    self.log(f"    ⚠️ Unexpected button error: {e}")
        except Exception as e:
            self.log(f"    ⚠️ Could not list buttons: {e}")

    # ---------- PHASE 2: SEND CONNECTION REQUESTS ----------

    def send_connection_requests(self, debug_buttons: bool = False) -> List[Result]:
        """
        עבור כל פרופיל שנסרק:
        - נכנס לפרופיל
        - מנסה לשלוח בקשת חברות
        - קובע status בהתאם למצב
        """
        assert self.driver is not None
        assert self.wait is not None

        self.results = []  # reset

        for entry in self.profiles:
            name = entry["Name"]
            title = entry["Title"]
            link = entry["LinkedIn URL"]

            self.log(f"\n🔗 Visiting {name}: {link}")
            self.driver.get(link)
            time.sleep(self.config.page_load_sleep)

            if debug_buttons:
                self._debug_print_buttons()

            status = ""
            try:
                invite_buttons = self.driver.find_elements(
                    By.XPATH,
                    "//button[contains(@aria-label,'Invite') and contains(@aria-label,'to connect')]",
                )

                selected = next(
                    (
                        btn
                        for btn in invite_buttons
                        if name in (btn.get_attribute("aria-label") or "")
                    ),
                    None,
                )

                if selected:
                    self.driver.execute_script(
                        "arguments[0].scrollIntoView({block:'center'});", selected
                    )
                    time.sleep(0.5)
                    self.driver.execute_script("arguments[0].click();", selected)
                    self.log(f"🎯 Clicked Invite for {name}")

                    self.wait.until(
                        EC.presence_of_element_located(
                            (By.CSS_SELECTOR, "div[role='dialog']")
                        )
                    )
                    send_btn = self.wait.until(
                        EC.element_to_be_clickable(
                            (
                                By.XPATH,
                                "//button[.//span[text()='Send without a note']]",
                            )
                        )
                    )
                    self.driver.execute_script(
                        "arguments[0].scrollIntoView({block:'center'});", send_btn
                    )
                    time.sleep(0.5)
                    self.driver.execute_script("arguments[0].click();", send_btn)
                    self.log("🎯 Clicked 'Send without a note'")
                    status = "Connection request sent"
                    time.sleep(1)
                else:
                    raise TimeoutException("No matching Invite button for user")

            except TimeoutException as e:
                self.log(f"⚠️ Invite flow unavailable: {e}")
                if self.driver.find_elements(
                    By.XPATH, "//button[.//span[text()='Pending']]"
                ):
                    status = "Request Sent"
                elif self.driver.find_elements(
                    By.XPATH, "//button[.//span[text()='Follow']]"
                ):
                    status = "Not connected - follow only"
                else:
                    status = "No invite option"
            except NoSuchElementException as e:
                self.log(f"⚠️ Element missing: {e}")
                status = "Error - element missing"
            except Exception as e:
                self.log(f"⚠️ Unexpected error: {e}")
                status = "Error - unexpected"

            self.log(f"✅ {name} -> {status}")
            self.results.append(
                {
                    "Name": name,
                    "Title": title,
                    "LinkedIn URL": link,
                    "Connection": status,
                }
            )

        return self.results

    # ---------- SAVE RESULTS ----------

    def save_results_to_csv(self, path: Optional[str] = None) -> str:
        """
        שומר את self.results ל-CSV, מוריד כפילויות.
        מחזיר את הנתיב הסופי.
        """
        if path is None:
            path = self.config.output_csv_path or "linkedin_leads.csv"

        df = pd.DataFrame(self.results, columns=["Name", "Title", "LinkedIn URL", "Connection"])
        df.drop_duplicates(subset=["LinkedIn URL"], inplace=True)
        df.to_csv(path, index=False)
        self.log(f"💾 Saved results to {path}")
        return path

    # ---------- HIGH LEVEL RUNNER ----------

    def run(self, debug_buttons: bool = False) -> List[Result]:
        """
        פונקציה אחת שמבצעת:
        1) יצירת דרייבר
        2) לוגין
        3) סקרייפ
        4) שליחת הזמנות
        5) שמירה ל-CSV (אם הוגדר ב-config)
        מחזירה self.results
        """
        try:
            self._create_driver()
            self.login()
            self.scrape_search_pages()
            self.send_connection_requests(debug_buttons=debug_buttons)

            if self.config.output_csv_path:
                self.save_results_to_csv(self.config.output_csv_path)

            return self.results

        finally:
            try:
                if self.driver is not None:
                    self.driver.quit()
            except Exception as e:
                self.log(f"⚠️ Error quitting driver: {e}")


# =========================
# CLI / DIRECT RUN (לא חובה)
# =========================

if __name__ == "__main__":
    # דוגמה להפעלה ישירה – אפשר למחוק/לעדכן אחרי שתחבר ל-UI או ל-API
    cfg = ScraperConfig(
        email="Insert_your_LinkedIn_email_here",
        password="Insert_your_password_here",
        base_search_url=(
            "https://www.linkedin.com/search/results/people/"
            "?geoUrn=%5B%22101620260%22%5D&keywords=finance&origin=FACETED_SEARCH"
        ),
        start_page=16,
        end_page=22,
        output_csv_path="linkedin_leads24_refactored.csv",
        headless=False,
        verbose=True,
    )

    scraper = LinkedInScraper(cfg)
    results = scraper.run(debug_buttons=False)
    print(f"✅ Finished. Total results: {len(results)}")
