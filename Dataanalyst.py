import requests
from bs4 import BeautifulSoup
import pandas as pd
from datetime import datetime, timedelta
import pytz
import re
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

# =========================
# TIME
# =========================
TZ = pytz.timezone("Europe/Stockholm")
NOW = datetime.now(TZ)
LAST_24H = NOW - timedelta(hours=24)

# =========================
# USER PROFILE
# =========================
RESUME_TEXT = """
Business Intelligence Analyst SQL Power BI SSRS Tableau KPI dashboards
ETL SSIS Data Warehouse Reporting Stakeholder collaboration
"""

SKILLS = [
    "sql","power bi","ssrs","tableau","kpi",
    "etl","ssis","data warehouse","reporting"
]

LEVEL_KEYWORDS = ["entry","junior","associate","trainee","graduate","intern"]
EXCLUDE = ["senior","lead","principal","manager","head"]

VISA_KEYWORDS = [
    "visa sponsorship","work permit","relocation",
    "international candidates","global applicants"
]

HEADERS = {"User-Agent": "Mozilla/5.0"}

# =========================
# EMAIL CONFIG
# =========================
EMAIL_CONFIG = {
    "smtp_server": "smtp.gmail.com",
    "smtp_port": 587,
    "sender": "togetran@gmail.com",
    "password": "APP_PASSWORD",
    "recipient": "togetran@gmail.com"
}

# =========================
# HELPERS
# =========================
def clean(t): return re.sub(r"\s+", " ", t.lower()).strip()

def entry_level(title):
    t = clean(title)
    if any(x in t for x in EXCLUDE): return False
    return any(x in t for x in LEVEL_KEYWORDS) or "data analyst" in t

def recent(posted):
    if not posted: return False
    p = clean(posted)
    if "hour" in p or "today" in p or "just" in p: return True
    if "day" in p:
        try: return int(re.search(r"\d+", p).group()) <= 1
        except: return False
    return False

def skill_score(text):
    t = clean(text)
    return sum(1 for s in SKILLS if s in t)

def visa_score(text):
    t = clean(text)
    return sum(2 for v in VISA_KEYWORDS if v in t)

def similarity(job_text):
    tfidf = TfidfVectorizer(stop_words="english")
    mat = tfidf.fit_transform([RESUME_TEXT, job_text])
    return cosine_similarity(mat[0:1], mat[1:2])[0][0]

# =========================
# SCRAPERS
# =========================

def scrape_indeed():
    url = "https://se.indeed.com/jobs?q=data+analyst&l=Sweden&fromage=1"
    soup = BeautifulSoup(requests.get(url, headers=HEADERS).text, "html.parser")
    jobs = []

    for card in soup.select("div.job_seen_beacon"):
        title = card.select_one("h2.jobTitle")
        company = card.select_one("span.companyName")
        location = card.select_one("div.companyLocation")
        posted = card.select_one("span.date")
        link = card.select_one("a")

        if not title or not link: continue
        if not entry_level(title.text): continue
        if not recent(posted.text if posted else ""): continue

        desc = card.text
        jobs.append({
            "role": title.text.strip(),
            "company": company.text.strip() if company else "",
            "location": location.text.strip() if location else "",
            "posted": posted.text.strip(),
            "link": "https://se.indeed.com" + link["href"],
            "skill": skill_score(desc),
            "visa": visa_score(desc),
            "sim": similarity(desc),
            "source": "Indeed"
        })
    return jobs

def scrape_arbetsformedlingen():
    url = "https://arbetsformedlingen.se/platsbanken/annonser?q=Dataanalytiker&l=Sweden"
    soup = BeautifulSoup(requests.get(url, headers=HEADERS).text, "html.parser")
    jobs = []

    for ad in soup.select("article"):
        title = ad.select_one("h3")
        company = ad.select_one("span")
        posted = ad.text

        if not title: continue
        if not entry_level(title.text): continue
        if not recent(posted): continue

        text = ad.text
        link = ad.find("a")["href"] if ad.find("a") else url

        jobs.append({
            "role": title.text.strip(),
            "company": company.text.strip() if company else "",
            "location": "Sweden",
            "posted": "Recent (AF)",
            "link": link if link.startswith("http") else "https://arbetsformedlingen.se" + link,
            "skill": skill_score(text),
            "visa": visa_score(text),
            "sim": similarity(text),
            "source": "Arbetsförmedlingen"
        })
    return jobs

# =========================
# MAIN LOGIC
# =========================
def run_scan():
    jobs = []
    jobs += scrape_indeed()
    jobs += scrape_arbetsformedlingen()

    df = pd.DataFrame(jobs)
    if df.empty: return df

    df.drop_duplicates(subset=["role","company"], inplace=True)
    df["rank"] = df["skill"]*2 + df["visa"] + df["sim"]*5
    df.sort_values("rank", ascending=False, inplace=True)
    return df.head(20)

# =========================
# EMAIL
# =========================
from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail

SENDGRID_API_KEY = "YOUR_SENDGRID_API_KEY"
RECIPIENT = "your_email@example.com"  # where you want the daily jobs sent
SENDER = "noreply@example.com"        # must be verified in SendGrid

def send_email_sendgrid(df):
    if df.empty:
        content = "No strong matches found in last 24 hours."
    else:
        content = f"Run time: {NOW.strftime('%Y-%m-%d %H:%M')} CET\n\n"
        content += df[["role","company","location","posted","link"]].to_string(index=False)

    message = Mail(
        from_email=SENDER,
        to_emails=RECIPIENT,
        subject=f"Daily Data Analyst Jobs – {NOW.strftime('%Y-%m-%d')}",
        plain_text_content=content
    )
    
    try:
        sg = SendGridAPIClient(SENDGRID_API_KEY)
        response = sg.send(message)
        print(f"Email sent! Status code: {response.status_code}")
    except Exception as e:
        print(f"Error sending email: {e}")

# =========================
# RUN
# =========================
if __name__ == "__main__":
    df = run_scan()
    if not df.empty:
        send_email_sendgrid(df)
