from __future__ import annotations
from dataclasses import dataclass, field
from typing import List, Optional, Callable
import time
import random
import pandas as pd

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC


# =============== CONFIG & TYPES ===============

@dataclass
class MessengerConfig:
    email: str
    password: str

    input_csv_path: str             # קובץ עם לידים (Name, LinkedIn URL)
    output_csv_path: str            # לאן לשמור תוצאות (עם Result)

    messages: List[str] = field(default_factory=list)

    min_delay_sec: float = 2.0      # דיליי מינימלי בין הודעות
    max_delay_sec: float = 4.0      # דיליי מקסימלי

    headless: bool = False          # להריץ בלי חלון כרום פתוח
    verbose: bool = True            # להדפיס לוגים או לא


LogFn = Callable[[str], None]


# =============== MAIN CLASS ===============

class LinkedInMessenger:
    """
    מחלקה שאחראית על:
    - לוגין ללינקדאין
    - פתיחת הודעה לכל פרופיל
    - בחירת הודעה רנדומלית מתוך הרשימה
    - שליחה + כתיבת סטטוס
    """

    def __init__(self, config: MessengerConfig, logger: Optional[LogFn] = None):
        self.config = config
        self.driver: Optional[webdriver.Chrome] = None
        self.wait: Optional[WebDriverWait] = None

        if logger is None:
            self.log = print
        else:
            self.log = logger

        # נשתמש בזה כדי לשמור את הסטטוסים במקביל ל-DataFrame
        self._results: List[str] = []

    # ---------- DRIVER SETUP ----------

    def _create_driver(self) -> None:
        options = webdriver.ChromeOptions()
        options.add_argument("--start-maximized")
        if self.config.headless:
            options.add_argument("--headless=new")

        self.driver = webdriver.Chrome(options=options)
        self.wait = WebDriverWait(self.driver, 15)

    # ---------- LOGIN ----------

    def login(self) -> None:
        assert self.driver is not None and self.wait is not None, "Driver not initialized"

        self.log("🔐 Logging into LinkedIn (Messenger)...")
        self.driver.get("https://www.linkedin.com/login")

        self.wait.until(EC.presence_of_element_located((By.ID, "username"))).send_keys(
            self.config.email
        )
        self.driver.find_element(By.ID, "password").send_keys(self.config.password)
        self.driver.find_element(By.CSS_SELECTOR, "button[type='submit']").click()

        # מחכה ל-feed כדי לוודא שהלוגין הצליח
        self.wait.until(lambda d: "feed" in d.current_url)
        self.log("✅ Login successful (Messenger)")

    # ---------- SINGLE MESSAGE ----------

    def send_message_to_profile(self, profile_url: str, name: str) -> str:
        """
        נכנס לפרופיל, פותח חלון הודעה, בוחר הודעה רנדומלית ושולח.
        מחזיר סטטוס: 'Message Sent' / 'Failed'
        """
        assert self.driver is not None and self.wait is not None

        self.log(f"→ Processing {name} | {profile_url}")
        self.driver.get(profile_url)
        time.sleep(3)

        first = name.split()[0] if isinstance(name, str) and name.strip() else ""

        # 1) פותח חלון הודעה (Message)
        try:
            buttons = self.driver.find_elements(
                By.XPATH,
                "//button[.//span[text()='Message']]"
            )
            message_button_clicked = False
            for b in buttons:
                if b.is_displayed() and b.is_enabled():
                    b.click()
                    message_button_clicked = True
                    break

            if not message_button_clicked:
                self.log(f"⚠️ No visible 'Message' button for {name}")
                return "Failed"

        except Exception as e:
            self.log(f"⚠️ Error opening message for {name}: {e}")
            return "Failed"

        # 2) כותב את ההודעה
        try:
            input_box = self.wait.until(EC.presence_of_element_located((
                By.CSS_SELECTOR,
                "div.msg-form__contenteditable[contenteditable='true']"
            )))

            if not self.config.messages:
                self.log("⚠️ No messages configured – skipping")
                return "Failed"

            template = random.choice(self.config.messages)
            msg = template.format(first=first)

            input_box.clear()
            input_box.send_keys(msg)

        except Exception as e:
            self.log(f"⚠️ Error typing message for {name}: {e}")
            return "Failed"

        # 3) לוחץ Send ומוודא שנשלח
        try:
            send_btn = self.wait.until(EC.element_to_be_clickable((
                By.CSS_SELECTOR,
                "div.msg-form__right-actions button.msg-form__send-button"
            )))
            send_btn.click()

            # פונקציה פנימית שבודקת אם תיבת ההודעה התרוקנה
            def box_cleared(drv):
                try:
                    txt = drv.find_element(
                        By.CSS_SELECTOR,
                        "div.msg-form__contenteditable[contenteditable='true']"
                    ).text
                    return txt.strip() == ""
                except Exception:
                    # אם אין תיבה – גם סבבה, כנראה נסגר/נשלח
                    return True

            self.wait.until(box_cleared)
            self.log(f"✅ Message sent to {name}")
            return "Message Sent"

        except Exception as e:
            self.log(f"⚠️ Error sending message for {name}: {e}")
            return "Failed"

    # ---------- HIGH LEVEL RUNNER ----------

    def run(self) -> str:
        """
        1) מרים דרייבר
        2) לוגין ללינקדאין
        3) קורא CSV של לידים
        4) שולח הודעה לכל ליד
        5) שומר תוצאה ל-CSV ויחזיר את הנתיב של הקובץ
        """
        try:
            self._create_driver()
            self.login()

            # קורא את הקובץ עם הלידים
            df = pd.read_csv(self.config.input_csv_path)
            if "LinkedIn URL" not in df.columns or "Name" not in df.columns:
                raise ValueError("CSV must contain 'Name' and 'LinkedIn URL' columns")

            df = df.dropna(subset=["LinkedIn URL"])
            self._results = []

            # לולאה על כל ליד
            for _, row in df.iterrows():
                name = str(row["Name"])
                url = str(row["LinkedIn URL"])

                status = self.send_message_to_profile(url, name)
                self._results.append(status)

                # דיליי רנדומלי
                delay = random.uniform(self.config.min_delay_sec, self.config.max_delay_sec)
                self.log(f"⏱ Sleeping {delay:.1f}s before next lead...")
                time.sleep(delay)

            # מוסיף עמודת Result ושומר לקובץ חדש
            df["Result"] = self._results
            df.to_csv(self.config.output_csv_path, index=False)
            self.log(f"💾 Results saved to {self.config.output_csv_path}")

            return self.config.output_csv_path

        finally:
            try:
                if self.driver is not None:
                    self.driver.quit()
            except Exception as e:
                self.log(f"⚠️ Error quitting driver: {e}")


# =============== DIRECT RUN EXAMPLE (לא חובה) ===============

if __name__ == "__main__":
    cfg = MessengerConfig(
        email="INSERT YOUR LINKEDIN EMAIL",
        password="INSERT YOUR PASSWORD",
        input_csv_path=r"linkedin_leads24.csv",
        output_csv_path=r"linkedin_leads24_with_results.csv",
        messages=[
            "Hi {first}, 1",
            "Hey {first}, 2",
            "Hi {first}, 3",
            "Hello {first}, 4",
        ],
        min_delay_sec=2,
        max_delay_sec=4,
        headless=False,
        verbose=True,
    )

    messenger = LinkedInMessenger(cfg)
    messenger.run()
