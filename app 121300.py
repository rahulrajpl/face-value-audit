# ----------------Face Value Audit Source Code----------------
import os, re, time
from urllib.parse import urlparse
import requests
import pandas as pd
from bs4 import BeautifulSoup
import streamlit as st
from html import escape

# ------------------------ Page & Config ------------------------
st.set_page_config(page_title="🦷 Face Value Audit", layout="wide")
st.title("🦷 Face Value Audit")
st.subheader("A free tool to evaluate your practice's online presence & patient experience")


# one-time bootstrap
if "draft" not in st.session_state:
    st.session_state.draft = {}
if "final" not in st.session_state:
    st.session_state.final = {}
if "submitted" not in st.session_state:
    st.session_state.submitted = False
if "last_fetched_website" not in st.session_state:
    st.session_state.last_fetched_website = None


# Keys (prefer Streamlit secrets, fallback to env)
PLACES_API_KEY = st.secrets.get("GOOGLE_PLACES_API_KEY", os.getenv("GOOGLE_PLACES_API_KEY"))
CSE_API_KEY    = st.secrets.get("GOOGLE_CSE_API_KEY", os.getenv("GOOGLE_CSE_API_KEY"))
CSE_CX         = st.secrets.get("GOOGLE_CSE_CX", os.getenv("GOOGLE_CSE_CX"))
# CORE_FONT = "Helvetica"

ASSETS_DIR = os.path.join(os.getcwd(), "assets")
os.makedirs(ASSETS_DIR, exist_ok=True)
# UNICODE_FONT_PATH = os.path.join(ASSETS_DIR, "DejaVuSans.ttf")

# ------------------------ Utility & API helpers ------------------------

def _valid_email(s: str) -> bool:
    return bool(re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", (s or "").strip()))

def _valid_phone(s: str) -> bool:
    # lenient; require at least 7 digits total
    return bool(re.search(r"\d{7,}", (s or "")))

def extract_practice_name(soup: BeautifulSoup):
    if not soup: 
        return None
    # Try common places: <h1>, title, og:site_name
    h1 = soup.find("h1")
    if h1 and h1.get_text(strip=True):
        return h1.get_text(" ", strip=True)
    title = soup.find("title")
    if title and title.get_text(strip=True):
        return title.get_text(" ", strip=True)
    og = soup.find("meta", attrs={"property": "og:site_name"})
    if og and og.get("content"):
        return og["content"].strip()
    return None

def extract_address_and_maplink(soup: BeautifulSoup):
    if not soup:
        return None, None
    # 1) direct Google Maps style links
    for a in soup.find_all("a", href=True):
        href = a["href"]
        if any(k in href for k in ["google.com/maps", "goo.gl/maps", "maps.app.goo.gl", "g.page/"]):
            text = a.get_text(" ", strip=True)
            if text and not re.match(r"^https?://", text):
                return text, href
            return None, href

    # 2) schema.org PostalAddress
    postal = soup.find(attrs={"itemtype": re.compile(r"schema\.org/PostalAddress", re.I)})
    if postal:
        parts = []
        for key in ["streetAddress", "addressLocality", "addressRegion", "postalCode", "addressCountry"]:
            el = postal.find(attrs={"itemprop": key})
            if el:
                parts.append(el.get_text(" ", strip=True))
        addr = ", ".join([p for p in parts if p])
        if addr:
            return addr, None

    # 3) Regex fallback (tune for your regions)
    text = soup.get_text("\n", strip=True)
    m = re.search(
        r"\d{1,6}\s+[^\n,]+(?:road|rd\.?|street|st\.?|ave|avenue|blvd|lane|ln|dr|drive|hwy|highway|pkwy|parkway|mall|suite|ste|floor|fl|#)[^\n]*",
        text, flags=re.I
    )
    if m:
        return m.group(0).strip(), None

    return None, None

def prefill_from_website(website_url: str):
    """Fetch page → extract name+address → Places fallback → store in session_state.draft"""
    if not website_url:
        return

    # fetch & parse
    soup, _ = fetch_html(website_url)  # reuse your existing fetch_html(url) -> (soup, html_text)

    name = extract_practice_name(soup)
    addr, maps_link = extract_address_and_maplink(soup)

    # Places fallback if address or name missing and Places API is available
    if not name or not addr:
        pid = find_best_place_id(name, "", website_url)  # your existing helper; keep signature consistent
        if pid:
            det = places_details(pid)  # your existing helper
            if det and det.get("status") == "OK":
                r = det["result"]
                if not name:
                    name = r.get("name") or name
                if not addr:
                    addr = r.get("formatted_address") or addr
                if pid and not maps_link:
                    maps_link = f"https://www.google.com/maps/search/?api=1&query=place_id:{pid}"

    st.session_state.draft.update({
        "website": website_url,
        # user-provided below remain as-is; we set defaults in the UI
        "practice_name": name or "",
        "address": addr or "",
        "maps_link": maps_link or "",
        # room for more auto fields if you need later:
        # "years_in_operation": "",
        # "specialties": "",
    })

@st.cache_data(show_spinner=False, ttl=3600)
def fetch_html(url: str):
    if not url:
        return None, None
    try:
        headers = {"User-Agent": "Mozilla/5.0"}
        t0 = time.time()
        r = requests.get(url, headers=headers, timeout=10)
        elapsed = time.time() - t0
        if r.status_code == 200:
            return BeautifulSoup(r.text, "html.parser"), elapsed
    except Exception:
        pass
    return None, None

@st.cache_data(show_spinner=False, ttl=3600)
def get_domain(url: str):
    try:
        netloc = urlparse(url).netloc.lower()
        if netloc.startswith("www."): netloc = netloc[4:]
        return netloc
    except Exception:
        return None

# def years_in_operation_from_site(soup: BeautifulSoup):
#     if not soup: return "Search limited"
#     text = soup.get_text(" ", strip=True)
#     m = re.search(r"(established|since|serving since|founded)\D*((19|20)\d{2})", text, flags=re.I)
#     if m: return m.group(2)
#     yrs = re.findall(r"(19|20)\d{2}", text)
#     return min(yrs) if yrs else "Search limited"

# @st.cache_data(show_spinner=False, ttl=3600)
# def specialties_from_site(soup: BeautifulSoup):
#     if not soup: return "Search limited"
#     text = soup.get_text(" ", strip=True).lower()
#     keywords = [
#         "general dentistry","orthodontics","braces","implants","implant","cosmetic",
#         "veneers","whitening","endodontics","root canal","periodontics","gum",
#         "pediatric","children","oral surgery","tmj","sleep apnea","invisalign",
#         "prosthodontics","crowns","bridges","dental implants"
#     ]
#     found = sorted(set(k for k in keywords if k in text))
#     return ", ".join(found) if found else "Search limited"

# --- Google Places ---
@st.cache_data(show_spinner=False, ttl=3600)
def places_text_search(query: str):
    if not PLACES_API_KEY: return None
    url = "https://maps.googleapis.com/maps/api/place/textsearch/json"
    params = {"query": query, "key": PLACES_API_KEY}
    r = requests.get(url, params=params, timeout=10)
    return r.json() if r.status_code == 200 else None

@st.cache_data(show_spinner=False, ttl=3600)
def places_find_place(text_query: str):
    if not PLACES_API_KEY: return None
    url = "https://maps.googleapis.com/maps/api/place/findplacefromtext/json"
    params = {
        "input": text_query,
        "inputtype": "textquery",
        "fields": "place_id,name,formatted_address,website",
        "key": PLACES_API_KEY
    }
    r = requests.get(url, params=params, timeout=10)
    return r.json() if r.status_code == 200 else None

@st.cache_data(show_spinner=False, ttl=3600)
def places_details(place_id: str):
    if not PLACES_API_KEY or not place_id: return None
    url = "https://maps.googleapis.com/maps/api/place/details/json"
    fields = ",".join([
        "name","place_id","formatted_address","international_phone_number","website",
        "opening_hours","photos","rating","user_ratings_total","types","geometry/location",
        "reviews"
    ])
    params = {"place_id": place_id, "fields": fields, "key": PLACES_API_KEY}
    r = requests.get(url, params=params, timeout=10)
    return r.json() if r.status_code == 200 else None

@st.cache_data(show_spinner=False, ttl=3600)
def find_best_place_id(clinic_name: str, address: str, website: str):
    queries = []
    if clinic_name and address: queries.append(f"{clinic_name} {address}")
    if clinic_name: queries.append(clinic_name)
    if website:
        domain = get_domain(website)
        if domain: queries.append(domain)

    for q in queries:
        js = places_text_search(q)
        # if DEBUG: st.sidebar.write("Text Search:", q, (js or {}).get("status"))
        if js and js.get("status") == "OK" and js.get("results"):
            return js["results"][0].get("place_id")

    for q in queries:
        js = places_find_place(q)
        # if DEBUG: st.sidebar.write("Find Place:", q, (js or {}).get("status"))
        if js and js.get("status") == "OK" and js.get("candidates"):
            return js["candidates"][0].get("place_id")
    return None

@st.cache_data(show_spinner=False, ttl=3600)
def rating_and_reviews(details: dict):
    if not details or details.get("status") != "OK":
        return "Search limited", "Search limited", []
    res = details.get("result", {})
    rating = res.get("rating")
    count = res.get("user_ratings_total")
    reviews = res.get("reviews", []) or []
    simplified = []
    for rv in reviews:
        simplified.append({
            "relative_time": rv.get("relative_time_description"),
            "rating": rv.get("rating"),
            "author_name": rv.get("author_name"),
            "text": rv.get("text") or ""
        })
    rating_str = f"{rating}/5" if rating is not None else "Search limited"
    total_reviews = count if count is not None else "Search limited"
    return rating_str, total_reviews, simplified

@st.cache_data(show_spinner=False, ttl=3600)
def office_hours_from_places(details: dict):
    if not details or details.get("status") != "OK": return "Search limited"
    res = details["result"]
    oh = res.get("opening_hours", {})
    wt = oh.get("weekday_text")
    return "; ".join(wt) if wt else "Search limited"

@st.cache_data(show_spinner=False, ttl=3600)
def photos_count_from_places(details: dict):
    if not details or details.get("status") != "OK": return "Search limited"
    return len(details["result"].get("photos", []))

# --- Custom Search ---
def appears_on_page1_for_dentist_near_me(website: str, clinic_name: str, address: str):
    if not (CSE_API_KEY and CSE_CX): return "Search limited"
    try:
        domain = get_domain(website) if website else None
        city = None
        if address and "," in address:
            parts = [p.strip() for p in address.split(",")]
            if len(parts) >= 2: city = parts[-2]
        q = f"dentist near {city}" if city else f"dentist near me {clinic_name or ''}".strip()
        r = requests.get(
            "https://www.googleapis.com/customsearch/v1",
            params={"key": CSE_API_KEY, "cx": CSE_CX, "q": q, "num": 10},
            timeout=10
        )
        if r.status_code != 200:
            return "Search limited"
        data = r.json()
        for it in data.get("items", []):
            link = it.get("link","")
            title = it.get("title","")
            snippet = it.get("snippet","")
            if domain and get_domain(link) == domain:
                return "Yes (Page 1)"
            if clinic_name and (clinic_name.lower() in title.lower() or clinic_name.lower() in snippet.lower()):
                return "Yes (Page 1)"
        return "No (Not on Page 1)"
    except Exception:
        return "Search limited"

# --- Website checks & parsing ---
def website_health(url: str, soup: BeautifulSoup, load_time: float):
    if not url: return "Search limited", "No URL"
    score = 0; checks = []
    if url.lower().startswith("https"):
        score += 34; checks.append("HTTPS ✅")
    else:
        checks.append("HTTPS ❌")
    if soup and soup.find("meta", attrs={"name": "viewport"}):
        score += 33; checks.append("Mobile-friendly ✅")
    else:
        checks.append("Mobile-friendly ❌")
    if load_time is not None:
        if load_time < 2:
            score += 33; checks.append(f"Load speed ✅ ({load_time:.2f}s)")
        elif load_time < 5:
            score += 16; checks.append(f"Load speed ⚠️ ({load_time:.2f}s)")
        else:
            checks.append(f"Load speed ❌ ({load_time:.2f}s)")
    else:
        checks.append("Load speed ❓")
    return f"{min(score,100)}/100", " | ".join(checks)

def social_presence_from_site(soup: BeautifulSoup):
    if not soup: return "None"
    links = [a.get("href") or "" for a in soup.find_all("a", href=True)]
    fb = any("facebook.com" in l for l in links)
    ig = any("instagram.com" in l for l in links)
    if fb and ig: return "Facebook, Instagram"
    if fb: return "Facebook"
    if ig: return "Instagram"
    return "None"

def media_count_from_site(soup: BeautifulSoup):
    if not soup: return "Search limited"
    imgs = len(soup.find_all("img"))
    vids = len(soup.find_all(["video","source"]))
    return f"{imgs} photos, {vids} videos"

def advertising_signals(soup: BeautifulSoup):
    if not soup: return "Search limited"
    html = str(soup)
    sig = []
    if "gtag(" in html or "gtag.js" in html or "www.googletagmanager.com" in html:
        sig.append("Google tag")
    if "fbq(" in html:
        sig.append("Facebook Pixel")
    return ", ".join(sig) if sig else "None detected"

def appointment_booking_from_site(soup: BeautifulSoup):
    if not soup: return "Search limited"
    t = soup.get_text(" ", strip=True).lower()
    if any(p in t for p in ["book", "appointment", "schedule", "reserve"]):
        if "calendly" in t or "zocdoc" in t or "square appointments" in t:
            return "Online booking (embedded)"
        return "Online booking (link/form)"
    return "Phone-only or unclear"

def insurance_from_site(soup: BeautifulSoup):
    if not soup: return "Search limited"
    t = soup.get_text(" ", strip=True).lower()
    if "insurance" in t or "we accept" in t or "ppo" in t or "delta dental" in t:
        m = re.search(r"([^.]*insurance[^.]*\.)", t)
        return m.group(0) if m else "Mentioned on site"
    return "Unclear"

# --- Sentiment/theme analysis (simple keyword approach on up to 5 Google reviews) ---
def analyze_review_texts(reviews):
    if not reviews:
        return "Search limited", "Search limited", "Search limited"
    text_blob = " ".join((rv.get("text") or "") for rv in reviews).lower()
    positive_themes = {
        "friendly staff": ["friendly","kind","caring","nice","welcoming","courteous"],
        "cleanliness": ["clean","hygienic","spotless"],
        "pain-free experience": ["painless","no pain","gentle","pain free","comfortable"],
        "professionalism": ["professional","expert","knowledgeable"],
        "communication": ["explained","explain","transparent","informative"]
    }
    negative_themes = {
        "long wait": ["wait","waiting","late","delay","overbooked"],
        "billing issues": ["billing","charges","overcharged","invoice","insurance problem"],
        "front desk experience": ["front desk","reception","rude","unhelpful"],
        "pain/discomfort": ["painful","hurt","rough","uncomfortable"],
        "upselling": ["upsell","salesy","sold me","pushy"]
    }
    def count_hits(theme_dict):
        scores = {}
        for theme, kws in theme_dict.items():
            c = 0
            for kw in kws:
                c += text_blob.count(kw)
            if c > 0: scores[theme] = c
        return sorted(scores.items(), key=lambda x: x[1], reverse=True)
    pos = count_hits(positive_themes)
    neg = count_hits(negative_themes)
    pos_total = sum(v for _, v in pos); neg_total = sum(v for _, v in neg)
    if pos_total == 0 and neg_total == 0:
        sentiment = "Mixed/neutral (few obvious themes)"
    elif pos_total >= neg_total:
        sentiment = f"Mostly positive mentions ({pos_total} vs {neg_total})"
    else:
        sentiment = f"Mixed with notable concerns ({neg_total} negatives vs {pos_total} positives)"
    def top3(items):
        if not items: return "None detected"
        return "; ".join([f"{k} ({v})" for k, v in items[:3]])
    return sentiment, top3(pos), top3(neg)

# --- Scoring ---
def to_pct_from_score_str(s):
    try:
        if isinstance(s, str) and "/" in s:
            return int(s.split("/")[0])
    except:
        pass
    return None

def compute_smile_score(wh_pct, social_present, rating, reviews_total, booking, hours_present, insurance_clear, accessibility_present=False):
    vis_parts = []
    if isinstance(wh_pct, (int,float)): vis_parts.append(wh_pct)
    if social_present == "Facebook, Instagram": vis_parts.append(100)
    elif social_present in ("Facebook","Instagram"): vis_parts.append(60)
    else: vis_parts.append(0)
    vis_avg = sum(vis_parts)/len(vis_parts) if vis_parts else 0
    vis_score = (vis_avg/100)*30

    rep_parts = []
    if isinstance(rating, (int,float)): rep_parts.append((rating/5.0)*100)
    if isinstance(reviews_total, (int,float)): rep_parts.append(min(1, reviews_total/500)*100)
    rep_avg = sum(rep_parts)/len(rep_parts) if rep_parts else 0
    rep_score = (rep_avg/100)*40

    exp_parts = []
    if booking and "Online booking" in booking: exp_parts.append(80)
    elif booking and "Phone-only" in booking: exp_parts.append(40)
    if hours_present: exp_parts.append(70)
    if insurance_clear: exp_parts.append(80)
    if accessibility_present: exp_parts.append(70)
    exp_avg = sum(exp_parts)/len(exp_parts) if exp_parts else 0
    exp_score = (exp_avg/100)*30

    total = round(vis_score + rep_score + exp_score, 1)
    return total, round(vis_score,1), round(rep_score,1), round(exp_score,1)

# --- Advice (blank when API-limited) ---
def advise(metric, value):
    if value is None: return ""
    s = str(value).strip().lower()
    # Blank if API-limited/problematic
    for marker in ["search limited", "not available via places api", "request_denied", "invalid request", "permission denied", "zero_results"]:
        if marker in s: return ""

    def pct_from_score_str(x):
        try:
            if isinstance(x, (int, float)): return int(x)
            if isinstance(x, str) and "/" in x: return int(x.split("/")[0])
        except: return None

    if "website health score" in metric.lower():
        pct = pct_from_score_str(value)
        return "You nailed it" if (pct is not None and pct >= 90) else "Improve HTTPS/mobile/speed"

    if "gbp completeness" in metric.lower():
        pct = pct_from_score_str(value)
        return "You nailed it" if (pct is not None and pct >= 90) else "Add hours, photos, website, phone on GBP"

    if "search visibility" in metric.lower():
        return "You nailed it" if "yes" in s else "Improve local SEO & citations"

    if "social media presence" in metric.lower():
        if "facebook, instagram" in s: return "You nailed it"
        if "facebook" in s or "instagram" in s: return "Add the other platform & post weekly"
        return "Add FB/IG links; post 2–3×/week"

    if "google reviews (avg)" in metric.lower():
        try:
            rating = float(str(value).split("/")[0])
            if rating >= 4.6: return "You nailed it"
            if rating >= 4.0: return "Ask happy patients for reviews to reach 4.6+"
            return "Address negatives & request fresh 5★ reviews"
        except: return ""

    if "total google reviews" in metric.lower():
        try:
            n = int(value)
            if n >= 300: return "You nailed it"
            if n >= 100: return "Run a monthly review drive to hit 300"
            return "Launch QR/SMS review ask at checkout"
        except: return ""

    if "appointment booking" in metric.lower():
        return "You nailed it" if "online booking" in s else "Add an online booking link/button"

    if "office hours" in metric.lower():
        return "Offer evenings/weekends to boost conversions"

    if "insurance acceptance" in metric.lower():
        return "You nailed it" if ("unclear" not in s) else "Publish accepted plans on site & GBP"

    if "sentiment highlights" in metric.lower():
        if "mostly positive" in s: return "You nailed it"
        if "mixed" in s: return "Fix top negatives & reply to reviews"
        return "Reply to negative themes with solutions"

    if "top positive themes" in metric.lower():
        return "Amplify these themes on website & ads" if ("none detected" not in s) else ""

    if "top negative themes" in metric.lower():
        if "none detected" in s: return "You nailed it"
        if "long wait" in s: return "Stagger scheduling & add SMS reminders"
        if "billing" in s: return "Clarify estimates & billing SOP"
        if "front desk" in s: return "Train front desk on empathy scripts"
        return "Tackle top 1–2 negative themes this month"

    if "photos" in metric.lower():
        return "You nailed it" if ("none" not in s and "0" not in s) else "Upload 10–20 clinic & team photos"

    if "advertising scripts" in metric.lower():
        return "You nailed it" if ("none" not in s) else "Add GA4/Ads pixel for conversion tracking"

    return ""

# ------------------------ UI form ------------------------
# with st.form("audit_form"):
#     clinic_name = st.text_input("Clinic Name")
#     address = st.text_input("Address")
#     phone = st.text_input("Phone Number")
#     website = st.text_input("Website URL (include http/https)")
#     submitted = st.form_submit_button("Run Audit")

# ------------------------ UI: inputs + auto-fill ------------------------

# ============ RESULTS (TOP) ============
if st.session_state.submitted and st.session_state.final:
    st.success("✅ Submitted. Showing results.")
    final = st.session_state.final

    # Example: pipe the confirmed values into your existing overview/sections
    # Replace this with your current render/audit functions.
    st.markdown("### Overview")
    cols = st.columns(2)
    with cols[0]:
        st.write("**Practice Name**:", final.get("practice_name") or "—")
        # linkify address when maps_link exists
        if final.get("maps_link") and final.get("address"):
            st.markdown(f'**Address**: [{final["address"]}]({final["maps_link"]})')
        else:
            st.write("**Address**:", final.get("address") or "—")
        st.write("**Phone**:", final.get("phone") or "—")
    with cols[1]:
        st.write("**Website**:", final.get("website") or "—")
        st.write("**Email**:", final.get("email") or "—")

    st.divider()
    # ... continue with the rest of your audit UI/logic using `final` ...

st.markdown("### Clinic Inputs")
def _normalize_url(u: str) -> str:
    if not u: return u
    u = u.strip()
    return ("https://" + u) if not urlparse(u).scheme else u

# 1) Only these three inputs (Email/Phone are user-supplied; keep as-is)
website = st.text_input("Website Link", key="website_input")
email   = st.text_input("Email ID",     key="email_input",  value=st.session_state.draft.get("email", ""))
phone   = st.text_input("Phone Number", key="phone_input",  value=st.session_state.draft.get("phone", ""))

# store user-supplied email/phone continuously (don't overwrite by auto)
st.session_state.draft["email"] = email
st.session_state.draft["phone"] = phone

# 2) If we have auto-pulled data, show a REVIEW & CONFIRM form (editable)
if st.session_state.draft.get("practice_name") or st.session_state.draft.get("address"):
    st.info("Review the auto-filled details below. You can edit before submitting.")
    with st.form("review_confirm_form", clear_on_submit=False):
        # editable fields shown after auto-fill:
        name   = st.text_input("Practice Name", st.session_state.draft.get("practice_name",""))
        addr   = st.text_area("Address", st.session_state.draft.get("address",""), height=80)
        maps   = st.text_input("Google Maps Link (optional)", st.session_state.draft.get("maps_link",""))

        confirmed = st.form_submit_button("✅ Confirm & Run Audit")
        if confirmed:
            st.session_state.final = {
                "website": st.session_state.draft.get("website", st.session_state.get("website_input","")),
                "email":   st.session_state.draft.get("email",   st.session_state.get("email_input","")),
                "phone":   st.session_state.draft.get("phone",   st.session_state.get("phone_input","")),
                "practice_name": name,
                "address": addr,
                "maps_link": maps,
            }
            st.session_state.submitted = True
            st.rerun()   # or _safe_rerun() helper if you added it


else:
    st.caption("Enter the website and I’ll auto-pull the remaining details.")

# # Show the (possibly prefilled) Address input
# st.text_input("Address", key="address", value=st.session_state.get("address", ""))

# Show a Maps link if we have one
# if st.session_state.get("maps_link"):
#     st.markdown(f"[Open in Google Maps]({st.session_state['maps_link']})")

# ------------------------ Tables with advice ------------------------
def section_df(section_dict):
    rows = []
    for k, v in section_dict.items():
        rows.append({"Metric": k, "Result": v, "Comments/ Recommendations": advise(k, v)})
    return pd.DataFrame(rows)

def show_table(title, data_dict):
    st.markdown(f"### {title}")
    df = section_df(data_dict)
    st.dataframe(df, use_container_width=True)

# --- Pretty card view for Practice Overview (with icons) ---
# def show_overview_cards(overview: dict):
#     # one-time lightweight CSS
#     st.markdown(
#         """
#         <style>
#         .ov-grid{display:grid;grid-template-columns:1fr 1fr;gap:12px;}
#         @media (max-width: 900px){.ov-grid{grid-template-columns:1fr;}}
#         .ov-card{border:1px solid #e5e7eb;background:#fff;border-radius:12px;padding:10px 12px;}
#         .ov-label{font-size:12px;color:#6b7280;text-transform:uppercase;letter-spacing:.03em;display:flex;align-items:center;gap:6px;}
#         .ov-value{font-size:14px;font-weight:600;color:#111827;line-height:1.5;margin-top:2px;word-break:break-word;}
#         .ov-value-muted{color:#6b7280;font-weight:500;}
#         .ov-link{color:#184A75;text-decoration:none;border-bottom:1px dotted #184A75;}
#         .ov-icon{font-size:13px;opacity:.9}
#         </style>
#         """,
#         unsafe_allow_html=True
#     )

#     # Subtle label icons (emoji → universal, no deps)
#     ICON = {
#         "Practice Name": "🏷️",
#         "Address": "📍",
#         "Phone": "☎️",
#         "Website": "🔗",
#         "Years in Operation": "🗓️",
#         "Specialties Highlighted": "⭐",
#     }

#     # Order the cards for a nicer flow
#     order = [
#         "Practice Name", "Address", "Phone", "Website",
#         "Years in Operation", "Specialties Highlighted"
#     ]
#     items = [(k, overview.get(k)) for k in order if k in overview]

#     def render_card(label: str, value):
#         icon = ICON.get(label, "•")
#         # prettify value (linkify website, mute "Search limited")
#         v = "—" if (value is None or str(value).strip() == "") else str(value)
#         if label.lower() == "website" and isinstance(v, str) and v.startswith(("http://", "https://")):
#             try:
#                 dom = urlparse(v).netloc or v
#             except Exception:
#                 dom = v
#             v_html = f'<a class="ov-link" href="{v}" target="_blank" rel="noopener">{dom}</a>'
#         else:
#             v_html = v

#         is_limited = isinstance(value, str) and value.lower().startswith("search limited")
#         value_cls = "ov-value ov-value-muted" if is_limited else "ov-value"

#         st.markdown(
#             f"""
#             <div class="ov-card">
#               <div class="ov-label"><span class="ov-icon">{icon}</span>{label}</div>
#               <div class="{value_cls}">{v_html}</div>
#             </div>
#             """,
#             unsafe_allow_html=True
#         )

#     st.markdown("### Practice Overview")
#     # st.markdown('<div class="ov-grid">', unsafe_allow_html=True)
#     # manual grid: render in column-major order
#     # 3 columns x 2 rows (max 6 items)
#     cols = st.columns(3)
#     for i, (label, value) in enumerate(items[:6]):
#         with cols[i % 3]:
#             render_card(label, value)
        
#     # st.markdown('</div>', unsafe_allow_html=True)

def show_visibility_cards(visibility: dict):
    st.markdown("### Online Presence & Visibility")

    # Minimal CSS to style each tile like your overview cards
    st.markdown(
        """
        <style>
        .vis-card{border:1px solid #e5e7eb;background:#fff;border-radius:12px;padding:10px 12px;}
        .vis-metric{font-size:12px;color:#6b7280;text-transform:uppercase;letter-spacing:.03em;}
        .vis-value{font-size:14px;font-weight:700;color:#111827;line-height:1.4;margin-top:4px;word-break:break-word;}
        .vis-value-small{font-size:12.5px;font-weight:500;color:#374151;line-height:1.5;margin-top:4px;word-break:break-word;white-space:pre-wrap;}

        .badge{display:inline-block;font-size:11px;padding:2px 8px;border-radius:999px;margin-left:8px;border:1px solid transparent;vertical-align:middle;}
        .badge-ok{background:#ecfdf5;color:#065f46;border-color:#a7f3d0;}
        .badge-warn{background:#fffbeb;color:#92400e;border-color:#fcd34d;}
        .badge-bad{background:#fef2f2;color:#991b1b;border-color:#fecaca;}
        .badge-muted{background:#f3f4f6;color:#374151;border-color:#e5e7eb;}

        .vis-recs{margin-top:12px;border-left:4px solid #2563eb;background:#eff6ff;border-radius:10px;padding:10px 12px;}
        .vis-recs-title{font-weight:700;color:#1d4ed8;margin-bottom:6px;}
        .vis-recs ul{margin:0;padding-left:18px;}
        .vis-recs li{margin:4px 0;}
        </style>
        """,
        unsafe_allow_html=True
    )

    # Exactly six metrics -> 3x2
    order = [
        "GBP Completeness (estimate)",
        "Website Health Score",
        "Search Visibility (Page 1?)",
        "Social Media Presence",
        "GBP Signals",
        "Website Health Checks",
    ]
    items = [(k, visibility.get(k, "—")) for k in order if k in visibility]
    items6 = items[:6] + [("", "")] * (6 - len(items))  # pad to 6

    # --- helpers for badges (same logic you had, trimmed) ---
    def _parse_pct_str(s):
        try:
            s = str(s)
            if "/" in s:
                return int(s.split("/")[0].strip())
        except Exception:
            return None
        return None

    def _ratio_from_checks(s):
        if not isinstance(s, str) or not s:
            return None
        good = s.count("✅"); warn = s.count("⚠️"); bad = s.count("❌")
        total = good + warn + bad
        if total == 0: return None
        score = good*1.0 + warn*0.5
        return score / total

    def _badge_for(label, value):
        s = "" if value is None else str(value).strip().lower()
        if s in ("", "—") or "search limited" in s:
            return ("Unknown", "badge-muted")
        if "completeness" in label.lower() or "health score" in label.lower():
            pct = _parse_pct_str(value)
            if pct is None: return ("Unknown", "badge-muted")
            if pct >= 80: return (f"{pct}", "badge-ok")
            if pct >= 60: return (f"{pct}", "badge-warn")
            return (f"{pct}", "badge-bad")
        if "search visibility" in label.lower():
            if "yes" in s: return ("Page 1", "badge-ok")
            if "no"  in s: return ("Not on Page 1", "badge-bad")
            return ("Unknown", "badge-muted")
        if "social media presence" in label.lower():
            if "facebook, instagram" in s: return ("Both", "badge-ok")
            if "facebook" in s or "instagram" in s: return ("Partial", "badge-warn")
            if "none" in s: return ("None", "badge-bad")
            return ("Unknown", "badge-muted")
        if "signals" in label.lower() or "checks" in label.lower():
            r = _ratio_from_checks(value)
            if r is None: return ("Unknown", "badge-muted")
            if r >= 0.75: return ("Strong", "badge-ok")
            if r >= 0.45: return ("Mixed", "badge-warn")
            return ("Weak", "badge-bad")
        return ("", "badge-muted")

    # --- per-tile renderer (like overview) ---
    def render_vis_card(label: str, value):
        if not label:  # placeholder
            st.markdown('<div class="vis-card" style="visibility:hidden;"></div>', unsafe_allow_html=True)
            return
        v = "—" if (value is None or str(value).strip() == "") else str(value)
        small = ("Signals" in label) or ("Checks" in label) or (len(v) > 80)
        val_cls = "vis-value-small" if small else "vis-value"
        badge_text, badge_class = _badge_for(label, value)
        badge_html = f'<span class="badge {badge_class}">{badge_text}</span>' if badge_text else ''
        st.markdown(
            f"""
            <div class="vis-card">
              <div class="vis-metric">{label}</div>
              <div class="{val_cls}">{v} {badge_html}</div>
            </div>
            """,
            unsafe_allow_html=True
        )

    # --- layout: EXACTLY 3 columns × 2 rows (like overview) ---
    cols = st.columns(3)
    for i, (label, value) in enumerate(items6):
        with cols[i % 3]:
            render_vis_card(label, value)

    # --- recommendations below the grid ---
    recs = []
    for k, v in items6:
        if not k:  # ignore placeholders
            continue
        r = advise(k, v)
        if r:
            recs.append(f"{k}: {r}")
    if recs:
        bullets = "".join([f"<li>{r}</li>" for r in recs])
        st.markdown(
            f"""
            <div class="vis-recs">
              <div class="vis-recs-title">💡 Recommendations</div>
              <ul>{bullets}</ul>
            </div>
            """,
            unsafe_allow_html=True
        )

def show_reputation_cards(reputation: dict):
    st.markdown("### Patient Reputation & Feedback")

    # CSS for tiles + badges + recs box
    st.markdown(
        """
        <style>
        .rep-card{border:1px solid #e5e7eb;background:#fff;border-radius:12px;padding:10px 12px;}
        .rep-metric{font-size:12px;color:#6b7280;text-transform:uppercase;letter-spacing:.03em;}
        .rep-value{font-size:14px;font-weight:700;color:#111827;line-height:1.4;margin-top:4px;word-break:break-word;}
        .rep-value-small{font-size:12.5px;font-weight:500;color:#374151;line-height:1.5;margin-top:4px;word-break:break-word;white-space:pre-wrap;}

        .badge{display:inline-block;font-size:11px;padding:2px 8px;border-radius:999px;margin-left:8px;border:1px solid transparent;vertical-align:middle;}
        .badge-ok{background:#ecfdf5;color:#065f46;border-color:#a7f3d0;}
        .badge-warn{background:#fffbeb;color:#92400e;border-color:#fcd34d;}
        .badge-bad{background:#fef2f2;color:#991b1b;border-color:#fecaca;}
        .badge-muted{background:#f3f4f6;color:#374151;border-color:#e5e7eb;}

        .rep-recs{margin-top:12px;border-left:4px solid #2563eb;background:#eff6ff;border-radius:10px;padding:10px 12px;}
        .rep-recs-title{font-weight:700;color:#1d4ed8;margin-bottom:6px;}
        .rep-recs ul{margin:0;padding-left:18px;}
        .rep-recs li{margin:4px 0;}
        </style>
        """,
        unsafe_allow_html=True
    )

    # Choose 6 metrics for 3x2
    order = [
        "Google Reviews (Avg)",
        "Total Google Reviews",
        "Sentiment Highlights",
        "Top Positive Themes",
        "Top Negative Themes",
        "Review Response Rate",  # or swap with "Yelp / Healthgrades / Zocdoc"
    ]
    items = [(k, reputation.get(k, "—")) for k in order if k in reputation]
    items6 = items[:6] + [("", "")] * (6 - len(items))  # pad to 6 tiles

    # --------- badges ----------
    def _badge_for(label, value):
        s = "" if value is None else str(value).strip()
        sl = s.lower()

        # Unknown/limited
        if s in ("", "—") or "search limited" in sl or "not available" in sl:
            return ("Unknown", "badge-muted")

        # Avg rating like "4.4/5"
        if "google reviews (avg)" in label.lower():
            try:
                rating = float(s.split("/")[0])
                if rating >= 4.6: return (f"{rating:.1f}", "badge-ok")
                if rating >= 4.0: return (f"{rating:.1f}", "badge-warn")
                return (f"{rating:.1f}", "badge-bad")
            except Exception:
                return ("Unknown", "badge-muted")

        # Total reviews (int)
        if "total google reviews" in label.lower():
            try:
                n = int(s)
                if n >= 300: return (str(n), "badge-ok")
                if n >= 100: return (str(n), "badge-warn")
                return (str(n), "badge-bad")
            except Exception:
                return ("Unknown", "badge-muted")

        # Sentiment
        if "sentiment highlights" in label.lower():
            if "mostly positive" in sl: return ("Positive", "badge-ok")
            if "mixed" in sl:           return ("Mixed", "badge-warn")
            if "concern" in sl or "negative" in sl: return ("Negative", "badge-bad")
            return ("Unknown", "badge-muted")

        # Top themes
        if "top positive themes" in label.lower():
            return ("Good Themes" if "none detected" not in sl else "None", 
                    "badge-ok" if "none detected" not in sl else "badge-muted")
        if "top negative themes" in label.lower():
            return ("None" if "none detected" in sl else "Issues", 
                    "badge-ok" if "none detected" in sl else "badge-warn")

        # Review response rate (string; may be % if you add later)
        if "review response rate" in label.lower():
            # If you later compute %, parse here for better badges
            return ("Unknown", "badge-muted")

        return ("", "badge-muted")

    # --------- tile renderer ----------
    def render_rep_card(label: str, value):
        if not label:
            st.markdown('<div class="rep-card" style="visibility:hidden;"></div>', unsafe_allow_html=True)
            return
        v = "—" if (value is None or str(value).strip() == "") else str(value)
        small = (len(v) > 80) or ("Top " in label)  # make long texts smaller
        val_cls = "rep-value-small" if small else "rep-value"
        badge_text, badge_class = _badge_for(label, value)
        badge_html = f'<span class="badge {badge_class}">{badge_text}</span>' if badge_text else ''
        st.markdown(
            f"""
            <div class="rep-card">
              <div class="rep-metric">{label}</div>
              <div class="{val_cls}">{v} {badge_html}</div>
            </div>
            """,
            unsafe_allow_html=True
        )

    # --------- layout: EXACT 3 columns × 2 rows ----------
    cols = st.columns(3)
    for i, (label, value) in enumerate(items6):
        with cols[i % 3]:
            render_rep_card(label, value)

    # --------- recommendations (below grid) ----------
    recs = []
    for k, v in items6:
        if not k:
            continue
        r = advise(k, v)  # your existing helper
        if r:
            recs.append(f"{k}: {r}")

    # de-dup while preserving order
    seen = set()
    recs = [x for x in recs if not (x in seen or seen.add(x))]

    if recs:
        
        bullets = "".join(f"<li>{escape(r)}</li>" for r in recs)
        st.markdown(
            f"""
            <div class="rep-recs">
              <div class="rep-recs-title">💡 Recommendations</div>
              <ul>{bullets}</ul>
            </div>
            """,
            unsafe_allow_html=True
        )

def show_reviews_cards(reviews: list):
    """
    Render up to 6 review cards in a fixed 3x2 grid.
    Each card shows author, time, star rating, and a hard-trimmed (~5 lines) preview.
    No 'Read more' or modal.
    """
    # ---- minimal card CSS ----
    st.markdown(
        """
        <style>
        .rev-card{border:1px solid #e5e7eb;background:#fff;border-radius:12px;padding:12px 12px;}
        .rev-card.empty{visibility:hidden;}
        .rev-header{display:flex;align-items:center;gap:10px;margin-bottom:6px;}
        .rev-avatar{
          width:32px;height:32px;border-radius:999px;display:flex;align-items:center;justify-content:center;
          background:linear-gradient(135deg,#e0e7ff,#fce7f3);color:#1f2937;font-weight:700;font-size:13px;
        }
        .rev-author{font-weight:700;color:#111827;font-size:14px;line-height:1.2;}
        .rev-time{font-size:12px;color:#6b7280;line-height:1.2;}
        .rev-stars{margin:4px 0 6px 0;font-size:14px;line-height:1;}
        .star{color:#f59e0b;} .star-empty{color:#e5e7eb;}
        .rev-text{font-size:13px;color:#111827;line-height:1.5;word-break:break-word;}
        </style>
        """,
        unsafe_allow_html=True
    )

    # ---- helpers ----
    def _initials(name: str) -> str:
        s = (name or "").strip()
        return s[:1].upper() if s else "?"

    def _stars(r):
        try:
            n = int(round(float(r)))
        except Exception:
            n = 0
        n = max(0, min(5, n))
        return "".join(
            [f'<span class="star">★</span>' for _ in range(n)] +
            [f'<span class="star-empty">★</span>' for _ in range(5 - n)]
        )

    def _trim_to_5_lines(text: str, avg_chars_per_line: int = 100, max_lines: int = 5):
        """Word-safe hard trim to roughly max_lines worth of characters."""
        if not text:
            return ""
        limit = avg_chars_per_line * max_lines
        if len(text) <= limit:
            return text
        words, out, count = text.split(), [], 0
        for w in words:
            add = (1 if out else 0) + len(w)
            if count + add > limit:
                break
            out.append(w)
            count += add
        return " ".join(out) + "…"

    # normalize (max 6) and pad for a stable 3x2 grid
    items = []
    for rv in (reviews or [])[:6]:
        items.append({
            "author": rv.get("author_name") or "Anonymous",
            "when": rv.get("relative_time") or "",
            "rating": rv.get("rating"),
            "text": rv.get("text") or "",
        })
    while len(items) < 6:
        items.append(None)

    # layout: exactly 3 columns × 2 rows
    cols = st.columns(3)
    for i, item in enumerate(items):
        with cols[i % 3]:
            if item is None:
                st.markdown('<div class="rev-card empty"></div>', unsafe_allow_html=True)
                continue

            author = item["author"]; when = item["when"]; rating = item["rating"]
            preview = _trim_to_5_lines(item["text"])
            stars_html = _stars(rating)

            st.markdown(
                f"""
                <div class="rev-card">
                  <div class="rev-header">
                    <div class="rev-avatar">{escape(_initials(author))}</div>
                    <div>
                      <div class="rev-author">{escape(author)}</div>
                      <div class="rev-time">{escape(when)}</div>
                    </div>
                  </div>
                  <div class="rev-stars">{stars_html}</div>
                  <div class="rev-text">{escape(preview)}</div>
                </div>
                """,
                unsafe_allow_html=True
            )

def show_marketing_cards(marketing: dict):
    st.markdown("### Marketing Signals")

    # CSS for tiles + badges + recs box (matches your other sections)
    st.markdown(
        """
        <style>
        .mkt-card{border:1px solid #e5e7eb;background:#fff;border-radius:12px;padding:10px 12px;}
        .mkt-card.empty{visibility:hidden;}
        .mkt-metric{font-size:12px;color:#6b7280;text-transform:uppercase;letter-spacing:.03em;}
        .mkt-value{font-size:14px;font-weight:700;color:#111827;line-height:1.4;margin-top:4px;word-break:break-word;}
        .mkt-value-small{font-size:12.5px;font-weight:500;color:#374151;line-height:1.5;margin-top:4px;word-break:break-word;white-space:pre-wrap;}

        .badge{display:inline-block;font-size:11px;padding:2px 8px;border-radius:999px;margin-left:8px;border:1px solid transparent;vertical-align:middle;}
        .badge-ok{background:#ecfdf5;color:#065f46;border-color:#a7f3d0;}
        .badge-warn{background:#fffbeb;color:#92400e;border-color:#fcd34d;}
        .badge-bad{background:#fef2f2;color:#991b1b;border-color:#fecaca;}
        .badge-muted{background:#f3f4f6;color:#374151;border-color:#e5e7eb;}

        .mkt-recs{margin-top:12px;border-left:4px solid #2563eb;background:#eff6ff;border-radius:10px;padding:10px 12px;}
        .mkt-recs-title{font-weight:700;color:#1d4ed8;margin-bottom:6px;}
        .mkt-recs ul{margin:0;padding-left:18px;}
        .mkt-recs li{margin:4px 0;}
        </style>
        """,
        unsafe_allow_html=True
    )

    # choose up to 6 metrics → fixed 3x2 grid (keys that exist in your file)
    order = [
        "Photos/Videos on Website",
        "Photos count in Google",
        "Advertising Scripts Detected",
        # add more here if you later include them:
        # "Local SEO (NAP consistency)",
        # "Social Proof (media/mentions)",
    ]
    items = [(k, marketing.get(k, "—")) for k in order if k in marketing]
    items6 = items[:6] + [("", "")] * (6 - len(items))  # pad to 6

    # ----- helpers -----
    def _int_from_any(s):
        try:
            # pull first integer in the string (e.g., "Photos ✅ (12)" -> 12)
            m = re.search(r"-?\d+", str(s))
            return int(m.group(0)) if m else None
        except Exception:
            return None

    def _vendor_count(s):
        """Count ad vendors from a string like 'Google Ads, Meta Pixel, ...'"""
        if not isinstance(s, str) or not s.strip() or "search limited" in s.lower():
            return None
        # split by comma or pipe
        parts = [p.strip() for p in s.replace("|", ",").split(",") if p.strip()]
        return len(parts) if parts else 0

    def _badge_for(label, value):
        s = "" if value is None else str(value).strip()
        sl = s.lower()

        if s in ("", "—") or "search limited" in sl or "not available" in sl:
            return ("Unknown", "badge-muted")

        if "photos/videos on website" in label.lower():
            n = _int_from_any(value)
            if n is None: return ("Unknown", "badge-muted")
            if n >= 15: return (str(n), "badge-ok")
            if n >= 5:  return (str(n), "badge-warn")
            return (str(n), "badge-bad")

        if "photos count in google" in label.lower():
            n = _int_from_any(value)
            if n is None: return ("Unknown", "badge-muted")
            if n >= 50: return (str(n), "badge-ok")
            if n >= 15: return (str(n), "badge-warn")
            return (str(n), "badge-bad")

        if "advertising scripts detected" in label.lower():
            # treat “None” as OK (privacy-friendly), 1–2 as Warn, 3+ as Bad
            if "none" in sl or "0" == sl:
                return ("None", "badge-ok")
            n = _vendor_count(value)
            if n is None: return ("Unknown", "badge-muted")
            if n <= 1: return (f"{n}", "badge-warn")
            if n <= 2: return (f"{n}", "badge-warn")
            return (f"{n}", "badge-bad")

        return ("", "badge-muted")

    def render_mkt_card(label: str, value):
        if not label:
            st.markdown('<div class="mkt-card empty"></div>', unsafe_allow_html=True)
            return
        v = "—" if (value is None or str(value).strip() == "") else str(value)
        small = len(v) > 80
        val_cls = "mkt-value-small" if small else "mkt-value"
        badge_text, badge_class = _badge_for(label, value)
        badge_html = f'<span class="badge {badge_class}">{badge_text}</span>' if badge_text else ''
        st.markdown(
            f"""
            <div class="mkt-card">
              <div class="mkt-metric">{label}</div>
              <div class="{val_cls}">{v} {badge_html}</div>
            </div>
            """,
            unsafe_allow_html=True
        )

    # ----- layout: EXACT 3 columns × 2 rows (like your Reputation cards) -----
    cols = st.columns(3)
    for i, (label, value) in enumerate(items6):
        with cols[i % 3]:
            render_mkt_card(label, value)

    # ----- recommendations under the grid -----
    recs = []
    for k, v in items6:
        if not k:
            continue
        r = advise(k, v)  # reuse your existing advice helper
        if r:
            recs.append(f"{k}: {r}")

    # de-dup while preserving order
    seen = set()
    recs = [x for x in recs if not (x in seen or seen.add(x))]

    if recs:
        from html import escape
        bullets = "".join(f"<li>{escape(r)}</li>" for r in recs)
        st.markdown(
            f"""
            <div class="mkt-recs">
              <div class="mkt-recs-title">💡 Recommendations</div>
              <ul>{bullets}</ul>
            </div>
            """,
            unsafe_allow_html=True
        )

def show_experience_cards(experience: dict):
    st.markdown("### Patient Experience & Accessibility")

    # Tile + badge + recs styles (same visual language as Reputation)
    st.markdown(
        """
        <style>
        .exp-card{border:1px solid #e5e7eb;background:#fff;border-radius:12px;padding:10px 12px;}
        .exp-card.empty{visibility:hidden;}
        .exp-metric{font-size:12px;color:#6b7280;text-transform:uppercase;letter-spacing:.03em;}
        .exp-value{font-size:14px;font-weight:700;color:#111827;line-height:1.4;margin-top:4px;word-break:break-word;}
        .exp-value-small{font-size:12.5px;font-weight:500;color:#374151;line-height:1.5;margin-top:4px;word-break:break-word;white-space:pre-wrap;}

        .badge{display:inline-block;font-size:11px;padding:2px 8px;border-radius:999px;margin-left:8px;border:1px solid transparent;vertical-align:middle;}
        .badge-ok{background:#ecfdf5;color:#065f46;border-color:#a7f3d0;}
        .badge-warn{background:#fffbeb;color:#92400e;border-color:#fcd34d;}
        .badge-bad{background:#fef2f2;color:#991b1b;border-color:#fecaca;}
        .badge-muted{background:#f3f4f6;color:#374151;border-color:#e5e7eb;}

        .exp-recs{margin-top:12px;border-left:4px solid #2563eb;background:#eff6ff;border-radius:10px;padding:10px 12px;}
        .exp-recs-title{font-weight:700;color:#1d4ed8;margin-bottom:6px;}
        .exp-recs ul{margin:0;padding-left:18px;}
        .exp-recs li{margin:4px 0;}
        </style>
        """,
        unsafe_allow_html=True
    )

    # Choose up to 6 metrics -> fixed 3x2
    order = [
        "Appointment Booking",
        "Office Hours",
        "Insurance Acceptance",
        "Accessibility Signals",   # exists in some runs; safely ignored if missing
    ]
    # keep declared order, then append any extra keys that may exist
    ordered = [(k, experience.get(k, "—")) for k in order if k in experience]
    extras = [(k, v) for k, v in experience.items() if k not in {k for k, _ in ordered}]
    items = (ordered + extras)[:6]
    # pad to 6 for a stable 3x2 grid
    items6 = items + [("", "")] * (6 - len(items))

    # ----- badges (same idea as Reputation section) -----
    def _badge_for(label: str, value):
        s = "" if value is None else str(value).strip()
        sl = s.lower()

        if not label or s in ("", "—") or "search limited" in sl:
            return ("Unknown", "badge-muted")

        if label == "Appointment Booking":
            if any(w in sl for w in ["online", "book", "booking", "zocdoc", "practo", "calendly"]):
                return ("Available", "badge-ok")
            if any(w in sl for w in ["no", "none", "unavailable"]):
                return ("Missing", "badge-bad")
            return ("Check", "badge-warn")

        if label == "Office Hours":
            if any(ch.isdigit() for ch in s):
                return ("Published", "badge-ok")
            return ("Missing", "badge-muted")

        if label == "Insurance Acceptance":
            if any(w in sl for w in ["yes", "accept", "network", "ppo", "hmo"]):
                return ("Listed", "badge-ok")
            if "unclear" in sl:
                return ("Unclear", "badge-warn")
            return ("Missing", "badge-muted")

        if label == "Accessibility Signals":
            if any(w in sl for w in ["wheelchair", "accessible", "ramp", "lift"]):
                return ("Accessible", "badge-ok")
            return ("Unknown", "badge-muted")

        return ("", "badge-muted")

    # ----- tile renderer -----
    def render_exp_card(label: str, value):
        if not label:
            st.markdown('<div class="exp-card empty"></div>', unsafe_allow_html=True)
            return
        v = "—" if (value is None or str(value).strip() == "") else str(value)
        val_cls = "exp-value-small" if (len(v) > 80 or "\n" in v) else "exp-value"
        badge_text, badge_class = _badge_for(label, value)
        badge_html = f'<span class="badge {badge_class}">{badge_text}</span>' if badge_text else ''
        st.markdown(
            f"""
            <div class="exp-card">
              <div class="exp-metric">{escape(label)}</div>
              <div class="{val_cls}">{escape(v)} {badge_html}</div>
            </div>
            """,
            unsafe_allow_html=True
        )

    # ----- layout: EXACT 3 columns × 2 rows (like Reputation) -----
    cols = st.columns(3)
    for i, (label, value) in enumerate(items6):
        with cols[i % 3]:
            render_exp_card(label, value)

    # ----- recommendations below -----
    recs = []
    for k, v in items6:
        if not k:
            continue
        r = advise(k, v)
        if r:
            recs.append(f"{k}: {r}")

    # de-dup while preserving order
    seen = set()
    recs = [x for x in recs if not (x in seen or seen.add(x))]

    if recs:
        bullets = "".join(f"<li>{escape(r)}</li>" for r in recs)
        st.markdown(
            f"""
            <div class="exp-recs">
              <div class="exp-recs-title">💡 Recommendations</div>
              <ul>{bullets}</ul>
            </div>
            """,
            unsafe_allow_html=True
        )

# =================== Summary cards: Smile + 3 Buckets (4 columns) ===================
# Minimal CSS for card style + progress bars + recs box
st.markdown(
    """
    <style>
    .top-card{border:1px solid #e5e7eb;background:#fff;border-radius:12px;padding:10px 12px;margin-bottom:12px;}
    .top-metric{font-size:12px;color:#6b7280;text-transform:uppercase;letter-spacing:.03em;}
    .top-big{font-size:18px;font-weight:700;color:#111827;margin-top:4px;}
    .top-bar{height:8px;border-radius:999px;background:#f3f4f6;margin-top:6px;overflow:hidden;}
    .top-bar span{display:block;height:100%;background:#2563eb;}
    .top-recs{margin-top:8px;border-left:4px solid #2563eb;background:#eff6ff;border-radius:10px;padding:10px 12px;}
    .top-recs-title{font-weight:700;color:#1d4ed8;margin-bottom:6px;}
    .top-recs ul{margin:0;padding-left:18px;}
    .top-recs li{margin:4px 0;}
    </style>
    """,
    unsafe_allow_html=True
)

def _pct(score, denom):
    try:
        return max(0, min(100, int(round(float(score) / float(denom) * 100))))
    except Exception:
        return 0

def bucket_card(col, label, score, denom):
    pct = _pct(score, denom)
    with col:
        st.markdown(
            f"""
            <div class="top-card">
              <div class="top-metric">{label}</div>
              <div class="top-big">{int(round(score))} / {denom}</div>
              <div class="top-bar"><span style="width:{pct}%"></span></div>
            </div>
            """,
            unsafe_allow_html=True
        )

# plumb the values used downstream
if st.session_state.submitted:
    clinic_name = st.session_state.final.get("practice_name")
    address     = st.session_state.final.get("address")
    phone       = st.session_state.final.get("phone")
    website     = st.session_state.final.get("website")
    # ... continue your existing audit pipeline ...
#  ------------------------ Run audit ------------------------
    soup, load_time = fetch_html(website)
    place_id = find_best_place_id(clinic_name, address, website)
    details = places_details(place_id) if place_id else None

    # 1) Overview
    overview = {
        "Practice Name": clinic_name or "Search limited",
        "Address": address or "Search limited",
        "Phone": phone or "Search limited",
        "Website": website or "Search limited",
        # "Years in Operation": years_in_operation_from_site(soup),
        # "Specialties Highlighted": specialties_from_site(soup),
    }

    # 2) Visibility
    wh_str, wh_checks = website_health(website, soup, load_time)
    social_present = social_presence_from_site(soup)
    appears = appears_on_page1_for_dentist_near_me(website, clinic_name, address)

    gbp_score = "Search limited"; gbp_signals = "Search limited"
    if details and details.get("status") == "OK":
        res = details["result"]; score = 0; checks = []
        if res.get("opening_hours"): score += 20; checks.append("Hours ✅")
        else: checks.append("Hours ❌")
        if res.get("photos"): score += 20; checks.append(f"Photos ✅ ({len(res.get('photos',[]))})")
        else: checks.append("Photos ❌ (0)")
        if res.get("website"): score += 15; checks.append("Website ✅")
        else: checks.append("Website ❌")
        if res.get("international_phone_number"): score += 15; checks.append("Phone ✅")
        else: checks.append("Phone ❌")
        if res.get("rating") and res.get("user_ratings_total",0)>0: score += 10; checks.append("Reviews ✅")
        else: checks.append("Reviews ❌")
        if "dentist" in res.get("types", []) or "dental_clinic" in res.get("types", []):
            score += 10; checks.append("Category ✅")
        else:
            checks.append("Category ❌")
        if res.get("formatted_address"): score += 10; checks.append("Address ✅")
        else:
            checks.append("Address ❌")
        gbp_score = f"{min(score,100)}/100"
        gbp_signals = " | ".join(checks)

    visibility = {
        "GBP Completeness (estimate)": gbp_score,
        "GBP Signals": gbp_signals,
        "Search Visibility (Page 1?)": appears,
        "Website Health Score": wh_str,
        "Website Health Checks": wh_checks,
        "Social Media Presence": social_present
    }

    # 3) Reputation
    rating_str, review_count_out, reviews = rating_and_reviews(details)
    sentiment_summary, top_pos_str, top_neg_str = analyze_review_texts(reviews)

    reputation = {
        "Google Reviews (Avg)": rating_str,
        "Total Google Reviews": review_count_out,
        "Sentiment Highlights": sentiment_summary,
        # "Yelp / Healthgrades / Zocdoc": "Search limited",
        "Top Positive Themes": top_pos_str,
        "Top Negative Themes": top_neg_str,
        # "Review Response Rate": "Not available via Places API (GBP needed)"
    }

    # 4) Marketing
    marketing = {
        "Photos/Videos on Website": media_count_from_site(soup) if soup else "Search limited",
        "Photos count in Google": photos_count_from_places(details) if details else "Search limited",
        "Advertising Scripts Detected": advertising_signals(soup) if soup else "Search limited",
        # "Local SEO (NAP consistency)": "Search limited",
        # "Social Proof (media/mentions)": "Search limited"
    }

    # 5) Experience
    booking = appointment_booking_from_site(soup)
    hours = office_hours_from_places(details)
    insurance = insurance_from_site(soup)
    experience = {
        "Appointment Booking": booking,
        "Office Hours": hours,
        "Insurance Acceptance": insurance,
        # "Accessibility Signals": "Search limited"
    }

    # ------------------------ Scoring ------------------------
    wh_pct = to_pct_from_score_str(wh_str)
    rating_val = None
    try:
        if isinstance(rating_str, str) and rating_str.endswith("/5"):
            rating_val = float(rating_str.split("/")[0])
    except Exception:
        pass
    reviews_total = review_count_out if isinstance(review_count_out, (int, float)) else None
    hours_present = isinstance(hours, str) and hours != "Search limited"
    insurance_clear = isinstance(insurance, str) and insurance not in ["Search limited", "Unclear"]

    smile, vis_score, rep_score, exp_score = compute_smile_score(
        wh_pct, social_present, rating_val, reviews_total, booking, hours_present, insurance_clear, accessibility_present=False
    )

    # 4 columns: 1) Smile Score  2) Visibility  3) Reputation  4) Experience
    c1, c2, c3, c4 = st.columns(4)

    bucket_card(c1, "Overall Score",       smile,     100)
    bucket_card(c2, "Visibility Score",  vis_score, 30)
    bucket_card(c3, "Reputation Score",  rep_score, 40)
    bucket_card(c4, "Experience Score",  exp_score, 30)

    st.markdown("---")
    show_visibility_cards(visibility)
    show_reputation_cards(reputation)

    if reviews:
        st.markdown("### Recent Google Reviews")
        show_reviews_cards(reviews)

    show_marketing_cards(marketing)
    show_experience_cards(experience)
