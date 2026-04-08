import os
import re
import json
import time
import asyncio
import requests
import pandas as pd
from urllib.parse import urljoin, urlparse, unquote
from bs4 import BeautifulSoup
from crawl4ai import AsyncWebCrawler, BrowserConfig, CrawlerRunConfig, CacheMode
from rich.console import Console
import itertools, threading, sys, random

console = Console()

# ─────────────────────────────────────────────
#  CONFIG
# ─────────────────────────────────────────────
BATCH_SIZE       = 5     # Max links to crawl per loop iteration
MODEL            = "Qwen 3 4B Thinking (Local)"
MAX_RETRIES      = 6
COOLDOWN_EXTRA   = 3

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
}

BLOCKED_DOMAINS = {
    "upwork.com",
    "fiverr.com",
    "freelancer.com",
    "peopleperhour.com",
    "guru.com",
    "truelancer.com",
    "reddit.com",
}

OUTPUT_COLUMNS = [
    "title",
    "website",
    "url",
    "budget",
    "posted",
    "match_score",
    "match_reason",
    "apply_method",
    "share_items",
    "email",
    "phone",
]


# ─────────────────────────────────────────────
#  LOCAL AI CALL
# ─────────────────────────────────────────────
class DummyResponse:
    def __init__(self, text):
        self.text = text

def call_local_ai(prompt):
    url = "http://127.0.0.1:11434/v1/chat/completions"
    
    model_name = "qwen3:4b-thinking"
    try:
        mods = requests.get("http://127.0.0.1:11434/v1/models", timeout=5).json()
        if "data" in mods and len(mods["data"]) > 0:
            model_name = mods["data"][0]["id"]
    except Exception:
        pass
        
    data = {
        "model": model_name, 
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.2
    }
    try:
        resp = requests.post(url, json=data, timeout=600)
        if resp.status_code == 200:
            text = resp.json()["choices"][0]["message"]["content"]
            print(f"        [OK] Local AI ({model_name}) responded!")
            return DummyResponse(text)
        else:
            print(f"        [ERR] Local AI HTTP {resp.status_code} - {resp.text}")
    except requests.exceptions.ConnectionError:
        print("        [API ERROR] Could not connect to Local AI. Is Ollama open and API enabled on port 11434?")
    except Exception as e:
        print(f"        [API ERROR] {e}")
    return None


# ─────────────────────────────────────────────
#  HELPERS
# ─────────────────────────────────────────────
def load_resume():
    if not os.path.exists("resume.txt"):
        raise FileNotFoundError("resume.txt not found in project folder.")
    with open("resume.txt", "r", encoding="utf-8") as f:
        return f.read()


def domain_of(url):
    try:
        return urlparse(url).netloc.lower().replace("www.", "")
    except Exception:
        return ""


def is_blocked(url):
    d = domain_of(url)
    return any(d == b or d.endswith("." + b) for b in BLOCKED_DOMAINS)


def clean_text(x):
    if not x:
        return ""
    return re.sub(r"\s+", " ", str(x)).strip()


def extract_emails(text):
    return list(set(re.findall(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", text or "")))


def extract_phones(text):
    pattern = r"(?:(?:\+?\d{1,3}[\s\-]?)?(?:\(?\d{2,4}\)?[\s\-]?)?\d{3,5}[\s\-]?\d{4,6})"
    vals = re.findall(pattern, text or "")
    cleaned = []
    for v in vals:
        t = re.sub(r"\s+", " ", v).strip()
        if len(re.sub(r"\D", "", t)) >= 8:
            cleaned.append(t)
    return list(dict.fromkeys(cleaned))


def detect_apply_method(text, url):
    t = (text or "").lower()
    u = (url or "").lower()
    if "linkedin.com" in u:
        return "LinkedIn Apply"
    if "instagram.com" in u:
        return "Instagram DM"
    if "mailto:" in u or "send your resume to" in t or "email" in t:
        return "Email"
    if "call us" in t or "phone" in t or "contact number" in t:
        return "Phone Call"
    if "apply now" in t or "apply here" in t or "application form" in t or "careers" in u or "job" in u:
        return "Website Form"
    return "Website Form"


def detect_share_items(text):
    t = (text or "").lower()
    items = []
    if "resume" in t or "cv" in t:
        items.append("CV")
    if "portfolio" in t:
        items.append("Portfolio")
    if "reel" in t or "showreel" in t or "demo reel" in t:
        items.append("Reel")
    if "cover letter" in t:
        items.append("Cover Letter")
    if not items:
        return "CV + Portfolio"
    return " + ".join(dict.fromkeys(items))


def find_budget(text):
    lines = (text or "").splitlines()
    hits = []
    money_pattern = re.compile(
        r"(\$|usd|₹|inr|eur|€|£).{0,25}(\d[\d,]*(?:\.\d+)?)|(\d[\d,]*(?:\.\d+)?\s?(?:usd|inr|eur|€|£|/hr|per hour|hourly))",
        re.I,
    )
    for line in lines[:250]:
        if money_pattern.search(line):
            hits.append(clean_text(line))
        if len(hits) >= 2:
            break
    return " | ".join(hits) if hits else "Unknown"


def find_posted(text):
    patterns = [
        r"\b\d+\s+(?:minute|minutes|hour|hours|day|days|week|weeks|month|months)\s+ago\b",
        r"\bposted\s+\d+\s+(?:minute|minutes|hour|hours|day|days|week|weeks|month|months)\s+ago\b",
        r"\b(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\s+\d{1,2},?\s+\d{4}\b",
    ]
    t = text or ""
    for p in patterns:
        m = re.search(p, t, re.I)
        if m:
            return clean_text(m.group(0))
    return "Unknown"


def looks_like_job_link(href, text):
    h = (href or "").lower()
    t = (text or "").lower()
    bad = [
        "login", "signup", "register", "privacy", "terms", "about",
        "contact", "share", "facebook", "twitter", "linkedin.com/company",
    ]
    if any(b in h for b in bad):
        return False
    # If the URL is just a domain with no path (e.g. ytjobs.co/), it's usually a landing page.
    parsed = urlparse(href)
    if not parsed.path or parsed.path == "/":
        return False
        
    job_words = ["job", "jobs", "career", "careers", "opening", "openings", "apply", "position", "vacancy", "role"]
    editor_words = ["video editor", "editor", "motion graphics", "post production", "youtube editor", "reels"]
    return any(w in h for w in job_words) or any(w in t for w in job_words + editor_words)


def page_title_from_html(html):
    soup = BeautifulSoup(html, "html.parser")
    if soup.title and soup.title.text:
        return clean_text(soup.title.text)
    h1 = soup.find("h1")
    return clean_text(h1.get_text(" ", strip=True)) if h1 else ""


# ─────────────────────────────────────────────
#  LOCAL AI: GENERATE SEARCH QUERIES
# ─────────────────────────────────────────────
def generate_search_queries(resume_text, n_queries=3):
    prompt = f"""
You are helping a freelance video editor find matching remote jobs.
Review the candidate's resume keywords to understand their niche:
{resume_text}

Task:
Generate EXACTLY {n_queries} highly optimized Google Search queries to find live job boards or company hiring pages looking for freelance video editors right now.
For example: "freelance video editor remote jobs 2026", "hiring youtube video editor part time remote".

Requirements:
- Output JSON only! NO other text.
- JSON must be a raw list of strings.

JSON schema:
[
  "query 1",
  "query 2",
  "query 3"
]
"""
    response = call_local_ai(prompt)
    if not response:
        raise RuntimeError("Local AI failed to respond for Step 1.")
        
    text = response.text.strip()
    # Strip <think> tags if present
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()
    
    m = re.search(r"\[\s*.*?\s*\]", text, re.S)
    if not m:
        raise ValueError("AI did not return parseable JSON list.")
    
    try:
        queries = json.loads(m.group(0))
        return queries[:n_queries]
    except Exception as e:
        raise ValueError(f"JSON Parse Error: {e}")


# ─────────────────────────────────────────────
#  GOOGLE SEARCH RESULT PARSING
# ─────────────────────────────────────────────
def extract_google_search_links(html):
    soup = BeautifulSoup(html, "html.parser")
    links = []
    for a in soup.find_all("a", href=True):
        href = a["href"]
        # Google search often masks direct links inside `/url?q=`
        if href.startswith("/url?q="):
            actual_url = href.split("/url?q=")[1].split("&")[0]
            actual_url = unquote(actual_url)
        elif href.startswith("http"):
            actual_url = href
        else:
            continue
            
        if "google.com" in actual_url:
            continue
            
        if is_blocked(actual_url):
            continue
            
        # NEW: Skip root domains or shallow paths for known job boards
        p = urlparse(actual_url)
        path = p.path.strip("/")
        if not path or len(path.split("/")) < 1:
            # If it's a known job board but just the home page, skip it
            board_domains = ["ytjobs.co", "onlinejobs.ph", "upwork.com", "fiverr.com", "guru.com"]
            if any(bd in actual_url.lower() for bd in board_domains):
                continue

        links.append(actual_url)
        
    # Deduplicate while preserving order
    uniq = []
    seen = set()
    for u in links:
        if u not in seen:
            seen.add(u)
            uniq.append(u)
    return uniq


# ─────────────────────────────────────────────
#  CRAWL4AI: BROWSER-BASED CRAWL
# ─────────────────────────────────────────────
async def crawl_pages(urls):
    browser_cfg = BrowserConfig(headless=True, verbose=False)
    run_cfg     = CrawlerRunConfig(cache_mode=CacheMode.BYPASS)
    results     = []
    async with AsyncWebCrawler(config=browser_cfg) as crawler:
        crawl_results = await crawler.arun_many(urls, config=run_cfg)
        for r in crawl_results:
            results.append(r)
    return results


# ─────────────────────────────────────────────
#  LOCAL AI: VERIFY AND MATCH JOB TO RESUME
# ─────────────────────────────────────────────
def ask_local_ai_to_match(resume_text, page_title, page_text, page_url, strictness="aggressive"):
    prompt = f"""
You are judging whether this page is a good fit for a freelance video editor.

Candidate:
{resume_text}

Page URL: {page_url}
Page title: {page_title}

Page content excerpt:
{page_text[:12000]}

Return JSON only:
{{
  "is_relevant": true or false,
  "job_title": "best extracted job title",
  "website": "site/company/job board name",
  "budget": "budget/pay if found, else Unknown",
  "posted": "posted date if found, else Unknown",
  "match_score": "High or Medium or Low",
  "match_reason": "max 2 short sentences",
  "apply_method": "Website Form or Email or LinkedIn Apply or Instagram DM or Direct Message or Phone Call",
  "share_items": "CV + Portfolio / Portfolio + Reel / CV only / Portfolio only",
  "email": "email if found else blank",
  "phone": "phone if found else blank"
}}
"""
    if strictness == "aggressive":
        prompt += """
Rules:
- Mark is_relevant=false if this is NOT a specific, single job/opportunity page.
- IMPORTANT: If the page is a list of MANY jobs, a homepage, or a generic search result page, return is_relevant=false.
- If you reject a page (is_relevant=false), you MUST still provide a clear "match_reason" explaining exactly why it was rejected.
- Only keep remote or realistically remote-friendly opportunities.
- Be conservative. If unsure, set is_relevant=false.
"""
    else:
        prompt += """
Rules:
- Mark is_relevant=false if this is NOT a specific, single job/opportunity page.
- If you reject a page (is_relevant=false), you MUST still provide a clear "match_reason".
- Accept video editing opportunities even if they are not fully remote or a perfect match.
- Be extremely lenient. If it barely looks like a related job post, set is_relevant=true.
"""
    try:
        resp = call_local_ai(prompt)
        if not resp: return None
        text = resp.text.strip()
        
        # Mute <think> blocks natively for Qwen 3 Thinking models
        text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()
        
        m = re.search(r"{.*}", text, re.S)
        if not m:
            print(f"      [!] AI failed to output JSON block. Raw text: {text[:200]}...")
            return None
        
        parsed = json.loads(m.group(0))
        if not parsed.get("is_relevant"):
            print(f"      [-] Job rejected by AI as irrelevant.")
        return parsed
    except Exception as e:
        print(f"      [!] JSON Parse Error: {e} | Text: {text[:200]}...")
        return None


# ─────────────────────────────────────────────
#  SPINNING TIMER HELPER
# ─────────────────────────────────────────────
class Spinner:
    """Shows a spinning timer with elapsed seconds while AI thinks."""
    def __init__(self, label):
        self.label = label
        self._stop = threading.Event()
        self._thread = None
        self.elapsed = 0

    def _spin(self):
        chars = itertools.cycle(['/', '-', '\\', '|'])
        start = time.time()
        while not self._stop.is_set():
            self.elapsed = time.time() - start
            sys.stdout.write(f"\r  {next(chars)} {self.label}... {self.elapsed:.0f}s ")
            sys.stdout.flush()
            self._stop.wait(0.15)
        self.elapsed = time.time() - start

    def __enter__(self):
        self._thread = threading.Thread(target=self._spin, daemon=True)
        self._thread.start()
        return self

    def __exit__(self, *args):
        self._stop.set()
        self._thread.join()


# ─────────────────────────────────────────────
#  MAIN PIPELINE
# ─────────────────────────────────────────────
async def main():
    os.makedirs("output", exist_ok=True)
    resume_text = load_resume()

    # ── Interactive Startup ──
    print("\n" + "=" * 60)
    print("  Job Discovery Pipeline")
    print("=" * 60)

    while True:
        answer = input("\n  How many verified leads do you want? (or press 'n' to randomize) ").strip().lower()
        if answer == 'n':
            target = random.randint(2, 10)
            print(f"  🎲 Randomly selected: {target} leads")
            break
        try:
            target = int(answer)
            if target < 1:
                print("  Please enter a positive number.")
                continue
            break
        except ValueError:
            print("  Please enter a valid number or 'n'.")

    while True:
        answer = input("  How many search terms should AI generate? (or press 'n' to randomize) ").strip().lower()
        if answer == 'n':
            n_queries = random.randint(2, 6)
            print(f"  🎲 Randomly selected: {n_queries} search terms")
            break
        try:
            n_queries = int(answer)
            if n_queries < 1:
                print("  Please enter a positive number.")
                continue
            break
        except ValueError:
            print("  Please enter a valid number or 'n'.")

    while True:
        print("\n  Select AI Sorting Strictness:")
        print("  [1] Loose (Lenient filtering, accepts more jobs)")
        print("  [2] Aggressive (Strict remote-only filtering)")
        answer = input("  Choice (1 or 2): ").strip()
        if answer == '1':
            strictness = "loose"
            break
        elif answer == '2':
            strictness = "aggressive"
            break
        else:
            print("  Please enter 1 or 2.")

    # ── Step 1: Connect to Local AI ──
    print(f"\n[1] Starting up...")
    print(f"[2] Connecting to Local AI...", end=" ")
    model_name = "qwen3:4b"
    try:
        mods = requests.get("http://127.0.0.1:11434/v1/models", timeout=5).json()
        if "data" in mods and len(mods["data"]) > 0:
            model_name = mods["data"][0]["id"]
        print(f"✓ Connected to {model_name}")
    except Exception:
        print(f"✗ Could not reach Ollama on port 11434!")
        return

    # ── Load known URLs from spreadsheet history ──
    out_v = os.path.join("output", "Jobs-Verified.xlsx")
    out_r = os.path.join("output", "Jobs-Rejected.xlsx")
    known_urls = set()
    for file_path in [out_v, out_r]:
        if os.path.exists(file_path):
            try:
                df_temp = pd.read_excel(file_path)
                if "url" in df_temp.columns:
                    known_urls.update(df_temp["url"].dropna().tolist())
            except Exception:
                pass
    if known_urls:
        print(f"    Loaded {len(known_urls)} URLs from history (will skip duplicates)")

    # ── Loop-Back Engine ──
    verified_rows = []
    rejected_rows = []
    used_domains  = set()
    all_seen_urls = set(known_urls)  # Track everything we've processed across loops
    loop_round    = 0
    MAX_ROUNDS    = 10  # Safety net to prevent infinite loops
    prev_queries  = []  # Track previous queries so AI generates different ones

    while len(verified_rows) < target and loop_round < MAX_ROUNDS:
        loop_round += 1
        remaining = target - len(verified_rows)

        if loop_round > 1:
            print(f"\n{'─'*60}")
            print(f"  ↻ Loop {loop_round}: Need {remaining} more verified lead(s)...")
            print(f"{'─'*60}")

        # ── Step A: Generate Search Queries ──
        print(f"\n[3] Asking AI to generate search terms...")

        # Build a prompt that avoids repeating old queries
        avoid_text = ""
        if prev_queries:
            avoid_text = f"\nDo NOT repeat these previously used queries:\n" + "\n".join(f'- "{q}"' for q in prev_queries)

        prompt_override = f"""
You are helping a freelance video editor find matching remote jobs.
Review the candidate's resume keywords to understand their niche:
{resume_text}

Task:
Generate EXACTLY {n_queries} highly optimized Google Search queries to find live job boards or company hiring pages looking for freelance video editors right now.
For example: "freelance video editor remote jobs 2026", "hiring youtube video editor part time remote".
{avoid_text}
Requirements:
- Output JSON only! NO other text.
- JSON must be a raw list of strings.

JSON schema:
[
  "query 1",
  "query 2"
]
"""
        resp = call_local_ai(prompt_override)
        if not resp:
            print("  ✗ AI failed to respond. Stopping.")
            break

        text = resp.text.strip()
        text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()
        m = re.search(r"\[\s*.*?\s*\]", text, re.S)
        if not m:
            print("  ✗ AI did not return parseable search queries. Stopping.")
            break

        queries = json.loads(m.group(0))[:n_queries]
        prev_queries.extend(queries)

        print(f"[4] AI generated {len(queries)} search terms:")
        for i, q in enumerate(queries, 1):
            print(f"    → \"{q}\"")

        # ── Step B: Google Search ──
        google_urls = [f"https://www.google.com/search?q={str(q).replace(' ', '+')}" for q in queries]

        print(f"\n[5] Pulling links from Google using Headless Crawler...")
        with console.status("[bold yellow]    Scraping Google...") as status:
            search_results = await crawl_pages(google_urls)

        candidate_urls = []
        for r in search_results:
            if getattr(r, "success", False) and getattr(r, "html", None):
                urls = extract_google_search_links(r.html)
                candidate_urls.extend(urls)

        # Deduplicate against history + this session
        fresh = []
        for u in candidate_urls:
            if u not in all_seen_urls:
                all_seen_urls.add(u)
                fresh.append(u)

        skipped = len(candidate_urls) - len(fresh)
        if skipped > 0:
            print(f"    Collected {len(fresh)} fresh URLs (Skipped {skipped} already processed)")
        else:
            print(f"    Collected {len(fresh)} unique candidate URLs")

        if not fresh:
            print("  ⚠ No new URLs found this round. Trying again with new queries...")
            continue

        # Cap to BATCH_SIZE
        batch = fresh[:BATCH_SIZE]
        print(f"    Processing batch of {len(batch)} links (max {BATCH_SIZE} per round)")

        # ── Step C: Deep Crawl ──
        print(f"\n[6] Deep Crawling {len(batch)} pages with Crawl4AI...")
        with console.status(f"[bold magenta]    Crawling {len(batch)} pages...") as status:
            crawl_results = await crawl_pages(batch)

        crawled_data = []
        for r in crawl_results:
            success = getattr(r, "success", False)
            final_url = clean_text(getattr(r, "url", ""))
            page_text = ""
            if success and getattr(r, "markdown", None):
                md = r.markdown
                if hasattr(md, "fit_markdown") and md.fit_markdown:
                    page_text = md.fit_markdown
                elif hasattr(md, "raw_markdown") and md.raw_markdown:
                    page_text = md.raw_markdown
                else:
                    page_text = str(md)
            crawled_data.append({"success": success, "url": final_url, "page_text": page_text})

        valid_crawls = [r for r in crawled_data if r.get("success")]
        print(f"    {len(valid_crawls)} pages loaded successfully out of {len(batch)}")

        # ── Step D: AI Analysis with Spinning Timer ──
        remaining = target - len(verified_rows)
        print(f"\n[7] Analyzing {len(valid_crawls)} pages with AI (need {remaining} more verified)...")

        for idx, r in enumerate(valid_crawls, 1):
            if len(verified_rows) >= target:
                break

            final_url = r.get("url", "")
            if not final_url or is_blocked(final_url):
                continue

            page_text = r.get("page_text", "")
            if not page_text or len(page_text) < 200:
                continue

            title  = clean_text(page_text.splitlines()[0])[:200]
            domain = domain_of(final_url)

            with Spinner(f"Analyzing [{idx}/{len(valid_crawls)}] {domain}") as sp:
                match = ask_local_ai_to_match(resume_text, title, page_text, final_url, strictness=strictness)

            # Build row
            row = {
                "title":        clean_text(match.get("job_title")) if match else title,
                "website":      clean_text(match.get("website"))   if match else domain,
                "url":          final_url,
                "budget":       clean_text(match.get("budget"))    if match else find_budget(page_text),
                "posted":       clean_text(match.get("posted"))    if match else find_posted(page_text),
                "match_score":  clean_text(match.get("match_score")) if match else "Low",
                "match_reason": clean_text(match.get("match_reason")) if match else "AI Parse Error",
                "apply_method": clean_text(match.get("apply_method")) if match else detect_apply_method(page_text, final_url),
                "share_items":  clean_text(match.get("share_items"))  if match else detect_share_items(page_text),
                "email":        clean_text(match.get("email")) if match else "",
                "phone":        clean_text(match.get("phone")) if match else "",
            }

            if not match or not match.get("is_relevant"):
                sys.stdout.write(f"\r  ✗ Analyzing [{idx}/{len(valid_crawls)}] {domain}... {sp.elapsed:.0f}s → Rejected\n")
                rejected_rows.append(row)
                continue

            if domain in used_domains:
                continue
            if not row["title"] or len(row["title"]) < 4:
                continue

            verified_rows.append(row)
            used_domains.add(domain)
            sys.stdout.write(f"\r  ✓ Analyzing [{idx}/{len(valid_crawls)}] {domain}... {sp.elapsed:.0f}s → VERIFIED [{row['match_score']}] {row['title']}\n")

        print(f"\n    Progress: {len(verified_rows)}/{target} verified leads found.")

    # ── Save Results ──
    print(f"\n{'='*60}")
    print(f"  Saving results...")

    # Save Verified Jobs
    if os.path.exists(out_v):
        try:
            df_v_existing = pd.read_excel(out_v)
            df_v = pd.concat([df_v_existing, pd.DataFrame(verified_rows, columns=OUTPUT_COLUMNS)], ignore_index=True)
        except Exception:
            df_v = pd.DataFrame(verified_rows, columns=OUTPUT_COLUMNS)
    else:
        df_v = pd.DataFrame(verified_rows, columns=OUTPUT_COLUMNS)

    if not df_v.empty:
        df_v = df_v.drop_duplicates(subset=["url"], keep="first")
        df_v = df_v.drop_duplicates(subset=["title", "website"], keep="first")
    df_v.to_excel(out_v, index=False)

    # Save Rejected Jobs
    if os.path.exists(out_r):
        try:
            df_r_existing = pd.read_excel(out_r)
            new_rejected = pd.DataFrame(rejected_rows, columns=OUTPUT_COLUMNS).rename(columns={"match_reason": "rejection_reason"})
            df_r = pd.concat([df_r_existing, new_rejected], ignore_index=True)
        except Exception:
            df_r = pd.DataFrame(rejected_rows, columns=OUTPUT_COLUMNS).rename(columns={"match_reason": "rejection_reason"})
    else:
        df_r = pd.DataFrame(rejected_rows, columns=OUTPUT_COLUMNS).rename(columns={"match_reason": "rejection_reason"})

    if not df_r.empty:
        df_r = df_r.drop_duplicates(subset=["url"], keep="first")
        df_r = df_r.drop_duplicates(subset=["title", "website"], keep="first")
    df_r.to_excel(out_r, index=False)

    print(f"  ✅  Added {len(verified_rows)} NEW verified jobs (Total History: {len(df_v)}) → {out_v}")
    print(f"  ❌  Added {len(rejected_rows)} NEW rejected jobs (Total History: {len(df_r)}) → {out_r}")
    print(f"{'='*60}")
    if not df_v.empty:
        print("\nTOP VERIFIED MATCHES:")
        print(df_v[["title", "website", "match_score", "url"]].head(5).to_string(index=False))


if __name__ == "__main__":
    asyncio.run(main())
