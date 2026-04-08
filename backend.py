import os
import re
import json
import time
import asyncio
import requests
import pandas as pd
from datetime import datetime
from urllib.parse import urlparse, unquote
from bs4 import BeautifulSoup
import subprocess
from crawl4ai import AsyncWebCrawler, BrowserConfig, CrawlerRunConfig, CacheMode

# =========================================================================
# GLOBAL STATE & CONFIG
# =========================================================================
class ConfigManager:
    DEFAULT_BLOCKLIST = ["upwork", "fiverr", "freelancer", "peopleperhour", "guru", "truelancer", "reddit", "behance", "glassdoor", "quora"]
    PATH = "config.json"

    def __init__(self):
        self.config = {
            "llm_model": "qwen3:4b-thinking",
            "system_prompt": "You are judging whether this page is a good fit for a freelance video editor.",
            "blocked_domains": self.DEFAULT_BLOCKLIST
        }
        self.load()

    def load(self):
        if os.path.exists(self.PATH):
            try:
                with open(self.PATH, "r") as f:
                    self.config.update(json.load(f))
            except: pass

    def save(self):
        with open(self.PATH, "w") as f:
            json.dump(self.config, f, indent=4)

    def get(self, key): return self.config.get(key)
    def set(self, key, val):
        self.config[key] = val
        self.save()

CONFIG = ConfigManager()

class BouncerLogManager:
    def __init__(self, size=100):
        self.logs = []
        self.size = size

    def add(self, url, status, reason):
        entry = {
            "timestamp": datetime.now().strftime("%H:%M:%S"),
            "url": url,
            "status": status, # PASSED, BLOCKED, DUPLICATE
            "reason": reason
        }
        self.logs.insert(0, entry)
        if len(self.logs) > self.size:
            self.logs.pop()

    def get_logs(self): return self.logs

BOUNCER_LOG = BouncerLogManager()

BATCH_SIZE       = 5
MAX_RETRIES      = 6
# BLOCKED_DOMAINS is now dynamic via CONFIG.get("blocked_domains")

OUTPUT_COLUMNS = [
    "title", "website", "url", "budget", "posted", "match_score", 
    "match_reason", "apply_method", "share_items", "email", "phone"
]

class DummyResponse:
    def __init__(self, text):
        self.text = text

async def call_local_ai(prompt):
    def _run():
        url = "http://127.0.0.1:11434/v1/chat/completions"
        model_name = CONFIG.get("llm_model")
        # Ensure model exists or fallback
        try:
            mods = requests.get("http://127.0.0.1:11434/v1/models", timeout=2).json()
            names = [m["id"] for m in mods.get("data", [])]
            if model_name not in names and names:
                model_name = names[0]
        except: pass

        data = {"model": model_name, "messages": [{"role": "user", "content": prompt}], "temperature": 0.2}
        try:
            resp = requests.post(url, json=data, timeout=600)
            if resp.status_code == 200:
                return DummyResponse(resp.json()["choices"][0]["message"]["content"])
        except Exception:
            pass
        return None
    return await asyncio.to_thread(_run)

def load_resume():
    if not os.path.exists("resume.txt"): return ""
    with open("resume.txt", "r", encoding="utf-8") as f: return f.read()

def domain_of(url):
    try: return urlparse(url).netloc.lower().replace("www.", "")
    except Exception: return ""

def is_blocked(url):
    d = domain_of(url)
    blocklist = CONFIG.get("blocked_domains")
    for b in blocklist:
        if b in d:
            BOUNCER_LOG.add(url, "BLOCKED", f"Matched '{b}' in blocklist")
            return True
    return False

def clean_text(x): return re.sub(r"\s+", " ", str(x)).strip() if x else ""

def find_budget(text):
    lines = (text or "").splitlines()
    hits = []
    money_pattern = re.compile(r"(\$|usd|₹|inr|eur|€|£).{0,25}(\d[\d,]*(?:\.\d+)?)|(\d[\d,]*(?:\.\d+)?\s?(?:usd|inr|eur|€|£|/hr|per hour|hourly))", re.I)
    for line in lines[:250]:
        if money_pattern.search(line): hits.append(clean_text(line))
        if len(hits) >= 2: break
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
        if m: return clean_text(m.group(0))
    return "Unknown"

def detect_apply_method(text, url):
    t, u = (text or "").lower(), (url or "").lower()
    if "linkedin.com" in u: return "LinkedIn Apply"
    if "instagram.com" in u: return "Instagram DM"
    if "mailto:" in u or "send your resume to" in t or "email" in t: return "Email"
    if "call us" in t or "phone" in t or "contact number" in t: return "Phone Call"
    return "Website Form"

def detect_share_items(text):
    t = (text or "").lower()
    items = [i for k, i in [("resume", "CV"), ("cv", "CV"), ("portfolio", "Portfolio"), ("reel", "Reel")] if k in t]
    return " + ".join(dict.fromkeys(items)) if items else "CV + Portfolio"

def is_likely_single_job_page(text):
    """Pre-screen crawled content to check if it looks like a single job posting
    rather than a generic aggregator/listing/search results page.
    Returns (True, reason) if it looks like a real job page, (False, reason) otherwise."""
    if not text or len(text.strip()) < 100:
        return False, "Page has almost no content"
    
    lower = text.lower()
    
    # Aggregator buzzwords
    buzzwords = len(re.findall(r'\b(\d+\+?\s+jobs?|results\s+for|jobs?\s+in\s+[a-z]+|search\s+results)\b', lower))
    
    # Count how many "apply" type buttons/links appear
    apply_hits = len(re.findall(r'\bapply\s*(now|here|today|for this)?\b', lower))
    
    # Count how many salary/pay mentions appear
    salary_hits = len(re.findall(r'(\$\d|₹\d|\d+\s*/\s*hr|\d+\s*per\s*hour)', lower))
    
    # Count repeated job title patterns
    job_card_patterns = len(re.findall(r'(posted\s*\d+\s*(days?|hours?|minutes?|weeks?|months?)\s*ago)', lower))
    
    # LinkedIn often uses "Be an early applicant" repeatedly on lists
    early_applicant = len(re.findall(r'be\s+an\s+early\s+applicant', lower))
    
    if buzzwords > 0:
        return False, "Text strongly implies this is a search results page ('X jobs', 'results for', etc)"
    if early_applicant > 1:
        return False, "Repeated LinkedIn 'early applicant' badges detected - this is a list"
    if apply_hits > 4 and job_card_patterns > 2:
        return False, "Page has multiple job cards with apply buttons - looks like an aggregator"
    if job_card_patterns > 4:
        return False, "Page has too many 'posted X ago' timestamps - likely a job listing page"
    if salary_hits > 4:
        return False, "Page mentions many different salaries - likely a listing page"
    
    return True, "Content looks like it could be a specific job page"

def extract_job_links_from_listing(markdown_text, source_url, all_seen_urls):
    """Extract individual job page URLs from a listing/aggregator page's markdown.
    crawl4ai markdown contains links as [text](url) — we extract those and filter
    for URLs that look like individual job postings."""
    source_domain = domain_of(source_url)
    links = re.findall(r'\[([^\]]*?)\]\((https?://[^\)]+)\)', markdown_text)
    
    job_keywords = ["job", "jobs", "career", "careers", "position", "opening", 
                    "vacancy", "role", "apply", "posting", "opportunity",
                    "editor", "video", "freelance", "remote"]
    
    job_urls = []
    seen = set()
    for anchor_text, url in links:
        if url in seen: continue
        seen.add(url)
        
        if is_blocked(url): continue
        if "google." in domain_of(url): continue
        
        # Check against global history
        if url in all_seen_urls:
            BOUNCER_LOG.add(url, "DUPLICATE", "Already in job history")
            continue

        path = urlparse(url).path.strip("/")
        if not path or len(path) < 3: continue
        
        low_url = url.lower()
        
        # Rigorously reject directory, search, pagination, list, and auth links
        if any(bad in low_url for bad in ["/search", "sort=", "page=", "/results", "categories", "/find", "utm_", "/login", "/signup", "/register", "/auth", "/newsletter"]):
            continue
            
        # Check if the URL path or anchor text has job-related keywords
        low_text = anchor_text.lower()
        
        if any(kw in low_url for kw in job_keywords) or any(kw in low_text for kw in job_keywords):
            BOUNCER_LOG.add(url, "PASSED", "Matched job keywords")
            job_urls.append(url)
    
    return job_urls

def extract_google_search_links(html, all_seen_urls):
    soup = BeautifulSoup(html, "html.parser")
    links = []
    for a in soup.find_all("a", href=True):
        href = a["href"]
        if href.startswith("/url?q="): href = unquote(href.split("/url?q=")[1].split("&")[0])
        if not href.startswith("http") or "google." in domain_of(href): continue
        
        if is_blocked(href): continue
        
        if href in all_seen_urls:
            BOUNCER_LOG.add(href, "DUPLICATE", "Found in Google results, but already in history")
            continue

        path = urlparse(href).path.strip("/")
        # Only reject truly root-level domains (no path at all)
        if not path: continue
        
        BOUNCER_LOG.add(href, "PASSED", "Initial Google lead bouncer check")
        links.append(href)
    uniq = []
    for u in links:
        if u not in uniq: uniq.append(u)
    return uniq

async def crawl_pages(urls):
    browser_cfg = BrowserConfig(headless=True, verbose=False)
    run_cfg = CrawlerRunConfig(cache_mode=CacheMode.BYPASS)
    async with AsyncWebCrawler(config=browser_cfg) as crawler:
        return await crawler.arun_many(urls, config=run_cfg)

async def ask_local_ai_to_match(resume_text, page_title, page_text, page_url, strictness="aggressive", job_type="both"):
    system_prompt = CONFIG.get("system_prompt")
    prompt = f"""{system_prompt}

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
    # Job type filtering
    if job_type == "remote":
        prompt += "\n- IMPORTANT: Only keep remote or realistically remote-friendly opportunities. Reject on-site only jobs."
    elif job_type == "on-site":
        prompt += "\n- IMPORTANT: Only keep on-site or in-office opportunities. Reject remote-only jobs."
    else:
        prompt += "\n- Accept jobs regardless of whether they are remote, on-site, or hybrid."

    if strictness == "aggressive":
        prompt += """
Rules:
- THRESHOLD: Only set is_relevant=true if the candidate's resume matches the job requirements 75% or more.
- Mark is_relevant=false if this is NOT a specific, single job/opportunity page.
- IMPORTANT: If the page is a list of MANY jobs, a homepage, or a generic search result page, return is_relevant=false.
- If you reject a page (is_relevant=false), you MUST still provide a clear "match_reason" explaining exactly why it was rejected.
- Be conservative. If unsure, set is_relevant=false.
"""
    elif strictness == "neutral":
        prompt += """
Rules:
- THRESHOLD: Only set is_relevant=true if the candidate's resume matches the job requirements 50% or more.
- Mark is_relevant=false if this is NOT a specific, single job/opportunity page.
- IMPORTANT: If the page is a list of MANY jobs, a homepage, or a generic search result page, return is_relevant=false.
- If you reject a page (is_relevant=false), you MUST still provide a clear "match_reason".
- Be balanced. If it looks like a reasonably good fit, set is_relevant=true.
"""
    else: # loose
        prompt += """
Rules:
- THRESHOLD: Only set is_relevant=true if the candidate's resume matches the job requirements 25% or more.
- Mark is_relevant=false if this is NOT a specific, single job/opportunity page.
- If you reject a page (is_relevant=false), you MUST still provide a clear "match_reason".
- Accept video editing opportunities even if not a perfect match.
- Be extremely lenient. If it barely looks like a related job post, set is_relevant=true.
"""
        
    try:
        resp = await call_local_ai(prompt)
        text = re.sub(r"<think>.*?</think>", "", resp.text, flags=re.DOTALL).strip() if resp else ""
        m = re.search(r"{.*}", text, re.S)
        return json.loads(m.group(0)) if m else None
    except Exception:
        return None

def find_ollama_executable():
    """Finds the ollama executable using `where.exe` on Windows, fallback to 'ollama'."""
    try:
        result = subprocess.run(["where.exe", "ollama"], capture_output=True, text=True, timeout=5)
        if result.returncode == 0:
            # Take the first match (one path per line)
            path = result.stdout.strip().splitlines()[0]
            if os.path.exists(path):
                return path
    except Exception:
        pass
    return "ollama"  # Fallback to PATH lookup

async def ensure_ollama_alive(event_queue: asyncio.Queue):
    """Checks if Ollama is running, and attempts to start it if not."""
    model = CONFIG.get("llm_model")
    await event_queue.put({"type": "info", "message": "Connecting to AI agent..."})
    
    for attempt in range(6): # Retry for ~30 seconds
        try:
            # Use to_thread to prevent blocking the async event loop during connection checks
            r = await asyncio.to_thread(requests.get, "http://127.0.0.1:11434/api/tags", timeout=3)
            if r.status_code == 200:
                await event_queue.put({"type": "connected", "message": f"Connected to {model}"})
                return True
        except requests.exceptions.RequestException:
            if attempt == 0:
                await event_queue.put({"type": "info", "message": "Ollama not detected. Attempting to start engine..."})
                ollama_path = await asyncio.to_thread(find_ollama_executable)
                await event_queue.put({"type": "info", "message": f"Found Ollama at: {ollama_path}"})
                try:
                    subprocess.Popen(
                        [ollama_path, "serve"],
                        creationflags=subprocess.CREATE_NO_WINDOW | subprocess.DETACHED_PROCESS,
                        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
                    )
                except Exception as e:
                    await event_queue.put({"type": "rejected", "message": f"Failed to start Ollama: {str(e)}"})
            await asyncio.sleep(5)
    
    await event_queue.put({"type": "rejected", "message": "Ollama connection timeout. Please start Ollama manually."})
    return False

# =========================================================================
# ASYNC ENGINE WITH QUEUE
# =========================================================================
async def run_pipeline(target_leads, search_terms, strictness, job_type, event_queue: asyncio.Queue):
  try:
    os.makedirs("output", exist_ok=True)
    resume_text = load_resume()
    
    # Pre-flight check for Ollama
    if not await ensure_ollama_alive(event_queue):
        await event_queue.put({"type": "done", "message": "Pipeline aborted due to AI connection failure."})
        return

    await event_queue.put({"type": "info", "message": f"Starting up... Engine configured for {target_leads} leads ({strictness} filtering)."})
    
    out_v = os.path.join("output", "Jobs-Verified.xlsx")
    out_r = os.path.join("output", "Jobs-Rejected.xlsx")
    
    known_urls = set()
    total_history = 0
    for file_path in [out_v, out_r]:
        if os.path.exists(file_path):
            try:
                df = pd.read_excel(file_path)
                if "url" in df.columns: known_urls.update(df["url"].dropna().tolist())
                if file_path == out_v: total_history = len(df)
            except Exception: pass
            
    await event_queue.put({"type": "info", "message": f"Loaded {len(known_urls)} URLs from history. Current verified history: {total_history}"})

    verified_rows, rejected_rows = [], []
    used_domains, all_seen_urls = set(), set(known_urls)
    search_round = 0
    prev_queries = []
    total_scraped = 0
    
    # ── OUTER LOOP: Generate new search terms when URL pool is exhausted ──
    while len(verified_rows) < target_leads and search_round < 10:
        search_round += 1
        remaining = target_leads - len(verified_rows)
        await event_queue.put({"type": "info", "message": f"Search Round {search_round}: Need {remaining} more verified leads..."})
        
        # Step 1: Ask AI for search queries
        avoid_text = ""
        if prev_queries:
            avoid_text = f"\nDo NOT repeat these previously used queries:\n" + "\n".join(f'- "{q}"' for q in prev_queries)

        prompt = f"""
You are helping a freelance video editor find matching remote jobs.
Review the candidate's resume keywords to understand their niche:
{resume_text}

Task:
Generate EXACTLY {search_terms} highly optimized Google Search queries to find live job boards or company hiring pages looking for freelance video editors right now.
For example: "freelance video editor remote jobs", "hiring youtube video editor part time remote".
{avoid_text}
Requirements:
- Output JSON only! NO other text.
- JSON must be a raw list of strings.
- IMPORTANT: Do NOT include any years (e.g., 2024, 2025) or specific dates in the queries.

JSON schema:
[
  "query 1",
  "query 2"
]
"""
        await event_queue.put({"type": "info", "message": f"Asking AI to generate {search_terms} search vectors..."})
        
        resp = await call_local_ai(prompt)
        text = re.sub(r"<think>.*?</think>", "", resp.text, flags=re.DOTALL).strip() if resp else ""
        m = re.search(r"\[\s*.*?\s*\]", text, re.S)
        queries = json.loads(m.group(0))[:search_terms] if m else []
        prev_queries.extend(queries)
        
        await event_queue.put({"type": "info", "message": f"Generated: {', '.join(queries)}"})
        
        # Step 2: Google Search to build URL pool
        google_urls = [f"https://www.google.com/search?q={str(q).replace(' ', '+')}" for q in queries]
        await event_queue.put({"type": "scrape", "message": "Crawling Google Search..."})
        search_results = await crawl_pages(google_urls)
        
        url_pool = []
        for r in search_results:
            if getattr(r, "success", False) and getattr(r, "html", None):
                url_pool.extend(extract_google_search_links(r.html, all_seen_urls))
                
        # Deduplicate against history
        # (already handled inside extract_google_search_links now, but safety filter)
        url_pool = [u for u in url_pool if u not in all_seen_urls]
        for u in url_pool: all_seen_urls.add(u)
        
        await event_queue.put({"type": "info", "message": f"URL pool: {len(url_pool)} fresh candidate links found."})
        
        if not url_pool:
            await event_queue.put({"type": "info", "message": "URL pool empty. Generating new search terms..."})
            continue
        
        # ── INNER LOOP: Drain the URL pool, crawling in small batches ──
        # Keep crawling from the pool until we have BATCH_SIZE pre-verified pages
        # or until the pool is exhausted
        pool_index = 0
        
        while len(verified_rows) < target_leads and pool_index < len(url_pool):
            # Grab the next chunk of URLs from the pool to crawl
            crawl_chunk = url_pool[pool_index : pool_index + BATCH_SIZE]
            pool_index += len(crawl_chunk)
            
            await event_queue.put({"type": "scrape", "message": f"Deep crawling {len(crawl_chunk)} pages... ({pool_index}/{len(url_pool)} from pool)"})
            crawl_results = await crawl_pages(crawl_chunk)
            
            # Extract text from crawled pages
            crawled_pages = []
            for r in crawl_results:
                success = getattr(r, "success", False)
                total_scraped += 1
                if success and getattr(r, "markdown", None):
                    md = getattr(r.markdown, "fit_markdown", "") or getattr(r.markdown, "raw_markdown", "") or str(r.markdown)
                    crawled_pages.append({"url": r.url, "text": md})
            
            # Pre-screen: filter out listing pages SILENTLY
            pre_verified = []
            for page in crawled_pages:
                final_url = page["url"]
                page_text = page["text"]
                
                if not final_url or is_blocked(final_url):
                    continue
                if not page_text or len(page_text) < 200:
                    continue
                
                is_single, reason = is_likely_single_job_page(page_text)
                if not is_single:
                    # Mine the listing page for individual job links before discarding
                    mined_links = extract_job_links_from_listing(page_text, final_url, all_seen_urls)
                    new_mined = [u for u in mined_links if u not in all_seen_urls]
                    if new_mined:
                        for u in new_mined: all_seen_urls.add(u)
                        # Inject right after the current pool_index to prioritize crawling this site's jobs immediately
                        url_pool[pool_index:pool_index] = new_mined
                        await event_queue.put({"type": "info", "message": f"Mined {len(new_mined)} strict job links from {domain_of(final_url)} → prioritized for immediate crawl"})
                    else:
                        await event_queue.put({"type": "info", "message": f"Crawler filtered out {domain_of(final_url)} (listing page, no valid deep links)"})
                    continue
                
                pre_verified.append(page)
            
            await event_queue.put({"type": "info", "message": f"Crawler pre-verified {len(pre_verified)} pages out of {len(crawled_pages)} crawled."})
            await event_queue.put({"type": "stats", "scraped": total_scraped, "verified": len(verified_rows), "rejected": len(rejected_rows)})
            
            if not pre_verified:
                # No good pages in this chunk, continue draining the pool
                continue
            
            # Step 3: Send pre-verified pages to AI for deep analysis
            for page in pre_verified:
                if len(verified_rows) >= target_leads: break
                
                final_url = page["url"]
                domain = domain_of(final_url)
                page_text = page["text"]
                
                await event_queue.put({"type": "info", "message": f"AI Analyzing: {domain}..."})
                title = clean_text(page_text.splitlines()[0])[:200]
                match = await ask_local_ai_to_match(resume_text, title, page_text, final_url, strictness, job_type)
                
                row = {
                    "title": clean_text(match.get("job_title")) if match else title,
                    "website": clean_text(match.get("website")) if match else domain,
                    "url": final_url,
                    "budget": clean_text(match.get("budget")) if match else find_budget(page_text),
                    "match_score": clean_text(match.get("match_score")) if match else "Low",
                    "match_reason": clean_text(match.get("match_reason")) if match else "Parse Error"
                }
                
                if not match or not match.get("is_relevant"):
                    await event_queue.put({"type": "rejected", "message": f"{domain} - {row['match_reason']}"})
                    rejected_rows.append(row)
                else:
                    if domain in used_domains: continue
                    verified_rows.append(row)
                    used_domains.add(domain)
                    await event_queue.put({"type": "verified", "message": f"{row['title']} @ {row['website']} [{row['match_score']}]"})
                
                await event_queue.put({
                    "type": "stats", "scraped": total_scraped, "verified": len(verified_rows), "rejected": len(rejected_rows)
                })
        
        # If we're here, the URL pool is exhausted. The outer loop will generate new search terms.
        if len(verified_rows) < target_leads:
            await event_queue.put({"type": "info", "message": "URL pool exhausted. Generating new search terms..."})
            
    # Save Logic
    await event_queue.put({"type": "info", "message": "Saving results to spreadsheet..."})
    
    # Save Verified
    if verified_rows:
        try: 
            df_v = pd.concat([pd.read_excel(out_v), pd.DataFrame(verified_rows, columns=OUTPUT_COLUMNS)], ignore_index=True)
        except Exception: 
            df_v = pd.DataFrame(verified_rows, columns=OUTPUT_COLUMNS)
        df_v.drop_duplicates(subset=["url"], keep="first", inplace=True)
        df_v.to_excel(out_v, index=False)
        
    # Save Rejected
    if rejected_rows:
        try:
            df_r = pd.concat([pd.read_excel(out_r), pd.DataFrame(rejected_rows, columns=OUTPUT_COLUMNS)], ignore_index=True)
        except Exception:
            df_r = pd.DataFrame(rejected_rows, columns=OUTPUT_COLUMNS)
        df_r.drop_duplicates(subset=["url"], keep="first", inplace=True)
        df_r.to_excel(out_r, index=False)
        
    await event_queue.put({"type": "info", "message": "Results have been saved in spreadsheet."})
    await event_queue.put({"type": "done", "message": "Pipeline complete."})

  except Exception as e:
    await event_queue.put({"type": "rejected", "message": f"Fatal engine error: {str(e)}"})
    await event_queue.put({"type": "done", "message": "Pipeline crashed. Check logs."})

