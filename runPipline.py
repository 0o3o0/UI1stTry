from linkedin_scraper_module import LinkedInScraper, ScraperConfig
from linkedin_messenger_module import LinkedInMessenger, MessengerConfig


def run_scraper_stage():
    """
    שלב 1: מריץ סקרפר – מחפש לידים + שולח בקשות חברות + שומר CSV
    את הנתיב לקובץ ה-CSV נחזיר לשימוש בשלב הבא.
    """
    cfg = ScraperConfig(
        email="YOUR_LINKEDIN_EMAIL_HERE",
        password="YOUR_LINKEDIN_PASSWORD_HERE",
        base_search_url=(
            "https://www.linkedin.com/search/results/people/"
            "?geoUrn=%5B%22101620260%22%5D&keywords=finance&origin=FACETED_SEARCH"
        ),
        start_page=16,
        end_page=22,
        output_csv_path="linkedin_leads24.csv",
        headless=False,   # אפשר True אם תרצה להריץ בלי חלון דפדפן
        verbose=True,
    )

    scraper = LinkedInScraper(cfg)
    results = scraper.run(debug_buttons=False)

    print(f"\n✅ SCRAPER DONE – scraped {len(results)} profiles")
    print(f"📄 CSV saved to: {cfg.output_csv_path}")
    return cfg.output_csv_path


def run_messenger_stage(input_csv: str):
    """
    שלב 2: מריץ שליחת הודעות על ה-CSV שיצא מהסקרפר.
    """
    cfg = MessengerConfig(
        email="YOUR_LINKEDIN_EMAIL_HERE",
        password="YOUR_LINKEDIN_PASSWORD_HERE",
        input_csv_path=input_csv,
        output_csv_path="linkedin_leads24_with_results.csv",
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
    output_csv = messenger.run()

    print(f"\n✅ MESSENGER DONE")
    print(f"📄 Output CSV with results: {output_csv}")


def main():
    # 1) סקרפר – מביא לידים ושומר קובץ
    csv_path = run_scraper_stage()

    # 2) שליחת הודעות – עובד על אותו קובץ
    run_messenger_stage(csv_path)


if __name__ == "__main__":
    main()
