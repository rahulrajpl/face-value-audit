# ----------------Face Value Audit Source Code----------------
import os, re, time
from urllib.parse import urlparse
import requests
import pandas as pd
from bs4 import BeautifulSoup
import streamlit as st
from html import escape
import asyncio
import concurrent.futures
from functools import lru_cache

# For Report Generation
import base64, json, hashlib
import streamlit.components.v1 as components

# For LLM-based social media analysis
try:
    import anthropic
    HAS_CLAUDE = True
except ImportError:
    HAS_CLAUDE = False

# Enhanced caching with LRU and memory management
from functools import lru_cache
import sys

# Global variable to store single LLM analysis result to avoid multiple API calls
_llm_analysis_cache = {}
_cache_max_size = 100  # Limit cache size to prevent memory issues

class AdvancedLLMCache:
    def __init__(self, max_size=100):
        self.cache = {}
        self.max_size = max_size
        self.access_order = []

    def get(self, key):
        if key in self.cache:
            # Move to end (most recently used)
            self.access_order.remove(key)
            self.access_order.append(key)
            return self.cache[key]
        return None

    def put(self, key, value):
        # Remove oldest if cache is full
        if len(self.cache) >= self.max_size and key not in self.cache:
            oldest = self.access_order.pop(0)
            del self.cache[oldest]

        self.cache[key] = value
        if key in self.access_order:
            self.access_order.remove(key)
        self.access_order.append(key)

    def clear(self):
        self.cache.clear()
        self.access_order.clear()

# Initialize advanced cache
_advanced_cache = AdvancedLLMCache(max_size=_cache_max_size)

# Claude API helper function
def call_claude_api(prompt: str, model: str = "claude-3-haiku-20240307", timeout: int = 30) -> str:
    """Helper function to call Claude API with timeout"""
    if not (HAS_CLAUDE and CLAUDE_API_KEY and claude_client):
        return None

    import signal
    import functools

    def timeout_handler(signum, frame):
        raise TimeoutError("Claude API call timed out")

    try:
        # Set timeout signal (only on Unix systems)
        if hasattr(signal, 'SIGALRM'):
            signal.signal(signal.SIGALRM, timeout_handler)
            signal.alarm(timeout)

        response = claude_client.messages.create(
            model=model,
            max_tokens=1024,
            temperature=0.3,
            messages=[
                {
                    "role": "user",
                    "content": prompt
                }
            ]
        )

        # Cancel the alarm
        if hasattr(signal, 'SIGALRM'):
            signal.alarm(0)

        return response.content[0].text
    except TimeoutError:
        st.warning("⚠️ Claude API took too long. Skipping AI analysis...")
        return None
    except Exception as e:
        st.sidebar.write(f"⚠️ Claude API error: {str(e)[:100]}")
        return None
    finally:
        # Ensure alarm is cancelled
        if hasattr(signal, 'SIGALRM'):
            signal.alarm(0)

# one-time session flag so we don't open multiple tabs on reruns
if "opened_report_id" not in st.session_state:
    st.session_state.opened_report_id = None

# For Saving to Google Sheets (optional)
import gspread
from google.oauth2.service_account import Credentials
from zoneinfo import ZoneInfo  # stdlib; for IST timestamp if you later want it
from datetime import datetime

# ------------------------ Page & Config ------------------------
st.set_page_config(page_title="Face Value Audit", layout="wide")

# Modern mobile-first UI styling
hide_streamlit_style = """
    <style>
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
    header {visibility: hidden;}

    /* Mobile-first responsive design */
    .stApp {
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%) !important;
        min-height: 100vh;
    }

    /* Reduce padding and margins for mobile */
    .main .block-container {
        padding-top: 1rem !important;
        padding-bottom: 1rem !important;
        padding-left: 1rem !important;
        padding-right: 1rem !important;
        max-width: 100% !important;
    }

    /* Card-like containers for form sections */
    .stForm {
        background: rgba(255, 255, 255, 0.95) !important;
        border-radius: 20px !important;
        padding: 1.5rem !important;
        margin: 0.5rem 0 !important;
        box-shadow: 0 8px 32px rgba(31, 38, 135, 0.37) !important;
        backdrop-filter: blur(8px) !important;
        border: 1px solid rgba(255, 255, 255, 0.18) !important;
    }

    /* Input styling */
    .stTextInput > div > div > input,
    .stSelectbox > div > div,
    .stTextArea > div > div > textarea {
        background: rgba(255, 255, 255, 0.9) !important;
        border: 1px solid rgba(102, 126, 234, 0.3) !important;
        border-radius: 12px !important;
        color: #333 !important;
        font-size: 16px !important; /* Prevents zoom on mobile */
        padding: 0.75rem !important;
        transition: all 0.3s ease !important;
    }

    .stTextInput > div > div > input:focus,
    .stSelectbox > div > div:focus,
    .stTextArea > div > div > textarea:focus {
        border-color: #667eea !important;
        box-shadow: 0 0 0 3px rgba(102, 126, 234, 0.1) !important;
        outline: none !important;
    }

    /* Button styling */
    .stButton > button {
        background: linear-gradient(45deg, #667eea, #764ba2) !important;
        color: white !important;
        border: none !important;
        border-radius: 15px !important;
        padding: 0.75rem 2rem !important;
        font-weight: 600 !important;
        font-size: 16px !important;
        transition: all 0.3s ease !important;
        box-shadow: 0 4px 15px rgba(102, 126, 234, 0.4) !important;
        width: 100% !important;
    }

    .stButton > button:hover {
        transform: translateY(-2px) !important;
        box-shadow: 0 8px 25px rgba(102, 126, 234, 0.6) !important;
    }

    .stButton > button:active {
        transform: translateY(0) !important;
    }

    /* Form submit button special styling */
    .stForm > button[type="submit"] {
        background: linear-gradient(45deg, #11998e, #38ef7d) !important;
        font-size: 18px !important;
        padding: 1rem 2rem !important;
        margin-top: 1rem !important;
    }

    /* Labels and text */
    label {
        color: #333 !important;
        font-weight: 600 !important;
        font-size: 14px !important;
        margin-bottom: 0.5rem !important;
    }

    /* Headers */
    h1 {
        color: white !important;
        text-align: center !important;
        font-weight: 700 !important;
        text-shadow: 2px 2px 4px rgba(0, 0, 0, 0.3) !important;
        margin-bottom: 2rem !important;
    }

    h2, h3, h4 {
        color: #333 !important;
        font-weight: 600 !important;
    }

    /* Compact spacing */
    .stTextInput, .stSelectbox, .stTextArea {
        margin-bottom: 0.5rem !important;
    }

    /* Column spacing */
    .stColumn {
        padding: 0.25rem !important;
    }

    /* Sidebar compact */
    .stSidebar {
        background: rgba(255, 255, 255, 0.95) !important;
        backdrop-filter: blur(10px) !important;
    }

    .stSidebar .block-container {
        padding-top: 1rem !important;
        padding-bottom: 1rem !important;
    }

    /* Mobile optimizations */
    @media (max-width: 768px) {
        .main .block-container {
            padding-left: 0.5rem !important;
            padding-right: 0.5rem !important;
        }

        .stForm {
            padding: 1rem !important;
            border-radius: 15px !important;
        }

        h1 {
            font-size: 2rem !important;
        }

        .stButton > button {
            font-size: 16px !important;
            padding: 0.75rem !important;
        }
    }

    /* Tablet optimizations */
    @media (min-width: 769px) and (max-width: 1024px) {
        .main .block-container {
            padding-left: 2rem !important;
            padding-right: 2rem !important;
        }
    }

    /* Hide Streamlit elements */
    [data-testid="stDecoration"],
    [data-testid="stStatusWidget"],
    .reportview-container .main footer,
    .streamlit-footer {
        display: none !important;
    }

    /* Spinner positioning for mobile */
    .stSpinner {
        position: fixed !important;
        top: 20px !important;
        left: 50% !important;
        transform: translateX(-50%) !important;
        z-index: 9999 !important;
        background: rgba(255, 255, 255, 0.9) !important;
        padding: 1rem 2rem !important;
        border-radius: 25px !important;
        box-shadow: 0 4px 20px rgba(0, 0, 0, 0.3) !important;
    }

    /* Caption text */
    .stCaption {
        color: #666 !important;
        font-size: 12px !important;
    }

    /* Success/warning messages */
    .stAlert {
        border-radius: 12px !important;
        margin: 0.5rem 0 !important;
    }
    </style>
"""
st.markdown(hide_streamlit_style, unsafe_allow_html=True)

ASSETS_DIR = os.path.join(os.getcwd(), "assets")
os.makedirs(ASSETS_DIR, exist_ok=True)

# Check if report is ready to display (move this to top)
if st.session_state.get('report_ready', False):
    # Display only the report at the top of the page
    components.html(st.session_state.report_html, height=1000, scrolling=True)

    # Reset button below the report
    if st.button("🔄 Run Another Audit", use_container_width=True):
        # Clear session state to start fresh
        for key in ['draft', 'final', 'submitted', 'last_fetched_website', 'opened_report_id', 'report_ready', 'report_html']:
            if key in st.session_state:
                del st.session_state[key]
        st.rerun()

    # Add footer below the Run Another Audit button
    st.markdown("---")
    st.markdown("""
    <div style="text-align: center; padding: 2rem 0; background: linear-gradient(90deg, #f8f9fa 0%, #ffffff 50%, #f8f9fa 100%); border-radius: 10px; margin-top: 3rem;">
        <h4 style="margin: 0 0 1rem 0; color: #333; font-weight: 600;">Powered by Needle Tail</h4>
        <p style="color: #666; margin: 0; font-size: 0.9rem;">Experience the future of healthcare eligibility verification with AI agents that work 24/7 to automate insurance verification processes.</p>
        <p style="color: #999; margin: 0.5rem 0 0 0; font-size: 0.8rem;">© 2025 Needle Tail. All rights reserved.</p>
    </div>
    """, unsafe_allow_html=True)

    # Stop rendering the rest of the page
    st.stop()

# Show the form only if report is not ready
# Centered logo and title
with open("assets/logo-big.png", "rb") as logo_file:
    logo_base64 = base64.b64encode(logo_file.read()).decode()

st.markdown(f"""
<div style="text-align: center; margin-bottom: 2rem;">
    <img src="data:image/png;base64,{logo_base64}" width="200" style="margin-bottom: 1rem;">
    <h1 style="margin: 0; font-size: 3rem; color: #262730;">Face Value Audit</h1>
</div>
""", unsafe_allow_html=True)

st.markdown("""
<h3 style="text-align: center; color: #666; margin-bottom: 2rem;">
A free tool to evaluate your practice's online presence & patient experience
</h3>
""", unsafe_allow_html=True)


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
CLAUDE_API_KEY = st.secrets.get("CLAUDE_API_KEY", os.getenv("CLAUDE_API_KEY"))

# Configure Claude if available
if HAS_CLAUDE and CLAUDE_API_KEY:
    claude_client = anthropic.Anthropic(api_key=CLAUDE_API_KEY)
else:
    claude_client = None
COLUMNS = ["Website Link", "Doctor Name", "Email ID", "Phone Number", "Practice Name", "Address", "Timestamp (IST)"] #For google sheet updation

# Debug: Check API keys configuration (REMOVE AFTER DEBUGGING)
# st.sidebar.write("🔧 Debug Info:")
# st.sidebar.write("Places API Key present:", bool(PLACES_API_KEY))
# st.sidebar.write("CSE API Key present:", bool(CSE_API_KEY))
# st.sidebar.write("CSE CX present:", bool(CSE_CX))

if PLACES_API_KEY:
    st.sidebar.write("Places API Key length:", len(PLACES_API_KEY))
if CSE_API_KEY:
    st.sidebar.write("CSE API Key length:", len(CSE_API_KEY))


# ------------------------ Utility & API helpers ------------------------
def _valid_email(s: str) -> bool:
    return bool(re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", (s or "").strip()))

def _valid_phone(s: str) -> bool:
    # lenient; require at least 7 digits total
    return bool(re.search(r"\d{7,}", (s or "")))

def shorten_address(full_address: str) -> str:
    """
    Shorten a full address to be less descriptive while keeping essential info
    Example: "123 Main Street, Suite 456, Downtown District, Springfield, IL 62701, USA"
    becomes "123 Main Street, Springfield, IL 62701"
    """
    if not full_address or full_address.strip() == "":
        return full_address

    # Remove common verbose elements
    address = full_address.strip()

    # Split by commas and process each part
    parts = [part.strip() for part in address.split(',')]
    filtered_parts = []

    # Keep essential parts, filter out verbose ones
    for part in parts:
        part_lower = part.lower()
        # Skip overly descriptive parts
        if any(skip in part_lower for skip in [
            'suite', 'unit', 'floor', 'building', 'complex', 'plaza', 'center',
            'district', 'neighborhood', 'area', 'united states', 'usa', 'america'
        ]):
            continue

        # Keep street address, city, state/province, postal code
        if part and len(part) > 1:
            filtered_parts.append(part)

    # Limit to maximum 4 parts (street, city, state, zip)
    if len(filtered_parts) > 4:
        # Keep first part (street) and last 3 parts (city, state, zip)
        filtered_parts = [filtered_parts[0]] + filtered_parts[-3:]

    return ', '.join(filtered_parts)

def validate_address_with_geocoding(address: str) -> tuple[bool, str]:
    """
    Validate an address using Google Geocoding API reverse search
    Returns (is_valid, validated_address)
    """
    if not address or not PLACES_API_KEY:
        return False, address

    try:
        # Use Google Geocoding API to validate address
        url = "https://maps.googleapis.com/maps/api/geocode/json"
        params = {
            "address": address,
            "key": PLACES_API_KEY
        }

        response = requests.get(url, params=params, timeout=10)
        if response.status_code != 200:
            return False, address

        data = response.json()

        if data.get("status") == "OK" and data.get("results"):
            # Get the first result (most accurate)
            result = data["results"][0]
            validated_address = result.get("formatted_address", address)

            # Shorten the validated address
            shortened = shorten_address(validated_address)
            return True, shortened
        else:
            return False, address

    except Exception as e:
        st.sidebar.write(f"⚠️ Address validation failed: {str(e)[:50]}")
        return False, address


# LLM-powered extraction functions
def extract_practice_name_with_llm(soup: BeautifulSoup, website_url: str):
    """Extract practice name using LLM if traditional methods fail"""
    if not (HAS_CLAUDE and CLAUDE_API_KEY and soup):
        return None

    try:
        # Get page content
        page_text = soup.get_text(" ", strip=True)[:1500]  # Limit for faster processing

        # Create focused prompt for practice name extraction
        prompt = f"""
        Extract the dental practice name from this website content.

        Website URL: {website_url}
        Content: {page_text}

        Instructions:
        - Find the official business/practice name
        - Return ONLY 3-4 words maximum (e.g., "Smith Family Dental", "Downtown Dentistry")
        - Use proper title case
        - Ignore generic terms like "Dentist" alone
        - If no clear practice name, return "NOT_FOUND"

        Practice Name (3-4 words max):"""

        result = call_claude_api(prompt)
        if not result:
            return None

        result = result.strip()

        # Validate the result - enforce 3-4 word limit
        if (result and result != "NOT_FOUND" and
            len(result) > 2 and len(result) < 50 and
            len(result.split()) <= 4 and  # Maximum 4 words
            not result.lower().startswith('http') and
            not result.lower() in ['dentist', 'dental', 'dental services', 'dental office']):
            return result.title()

        return None

    except Exception as e:
        st.sidebar.write(f"⚠️ LLM name extraction failed: {str(e)[:50]}")
        return None

def extract_address_with_llm(soup: BeautifulSoup, website_url: str):
    """Extract physical address using LLM if traditional methods fail"""
    if not (HAS_CLAUDE and CLAUDE_API_KEY and soup):
        return None

    try:
        # Get page content
        page_text = soup.get_text(" ", strip=True)[:1500]

        # Create focused prompt for address extraction
        prompt = f"""
        Extract the physical address of this dental practice from the website content.

        Website URL: {website_url}
        Content: {page_text}

        Instructions:
        - Find the complete physical address (street, city, state/province, zip/postal code)
        - Look for contact sections, footer, about pages
        - Return ONLY the full address in standard format
        - If multiple locations, return the main/primary address
        - If no physical address exists, return "NOT_FOUND"
        - Do not include phone numbers or email addresses

        Physical Address:"""

        result = call_claude_api(prompt)
        if not result:
            return None

        result = result.strip()

        # Validate the result - should contain typical address components
        if (result and result != "NOT_FOUND" and
            len(result) > 10 and len(result) < 200 and
            not result.lower().startswith('http') and  # Not a URL
            any(word in result.lower() for word in ['street', 'st', 'avenue', 'ave', 'road', 'rd', 'drive', 'dr', 'lane', 'ln', 'blvd', 'suite', 'ste', 'way', 'place', 'circle', 'court']) and
            any(char.isdigit() for char in result)):  # Should contain at least one number

            # Shorten and validate the LLM-extracted address with Google Maps
            shortened_address = shorten_address(result.strip())
            is_valid, validated_address = validate_address_with_geocoding(shortened_address)

            if is_valid:
                st.sidebar.write(f"✅ Address validated with Google Maps: {validated_address[:50]}...")
                return validated_address
            else:
                # If validation fails, don't return the address - let it be empty
                st.sidebar.write(f"❌ Address not found in Google Maps: {shortened_address[:50]}...")
                return None

        return None

    except Exception as e:
        st.sidebar.write(f"⚠️ LLM address extraction failed: {str(e)[:50]}")
        return None

def extract_doctor_name_with_llm(soup: BeautifulSoup, website_url: str):
    """Extract main doctor name using LLM"""
    if not (HAS_CLAUDE and CLAUDE_API_KEY and soup):
        return None

    try:
        # Get page content
        page_text = soup.get_text(" ", strip=True)[:1500]

        # Create focused prompt for doctor name extraction
        prompt = f"""
        Extract the main doctor's name from this dental practice website content.

        Website URL: {website_url}
        Content: {page_text}

        Instructions:
        - Find the primary dentist/doctor's full name
        - Look for "Dr.", "Doctor", "Meet Dr.", "About Dr.", etc.
        - Return ONLY the doctor's name with title (e.g., "Dr. John Smith")
        - If multiple doctors, return the main/primary one
        - If no clear doctor name exists, return "NOT_FOUND"

        Doctor Name:"""

        result = call_claude_api(prompt)
        if not result:
            return None

        result = result.strip()

        # Validate the result
        if (result and result != "NOT_FOUND" and
            len(result) > 3 and len(result) < 100 and
            not result.lower().startswith('http')):
            return result

        return None

    except Exception as e:
        st.sidebar.write(f"⚠️ LLM doctor name extraction failed: {str(e)[:50]}")
        return None

def extract_email_with_llm(soup: BeautifulSoup, website_url: str):
    """Extract contact email using LLM"""
    if not (HAS_CLAUDE and CLAUDE_API_KEY and soup):
        return None

    try:
        # Get page content
        page_text = soup.get_text(" ", strip=True)[:1500]

        # Create focused prompt for email extraction
        prompt = f"""
        Extract the main contact email address from this dental practice website content.

        Website URL: {website_url}
        Content: {page_text}

        Instructions:
        - Find the primary contact email address
        - Look for contact sections, footer, about pages
        - Return ONLY the email address (e.g., "info@practice.com")
        - If multiple emails, return the main contact one (avoid personal emails)
        - If no email exists, return "NOT_FOUND"

        Email Address:"""

        result = call_claude_api(prompt)
        if not result:
            return None

        result = result.strip()

        # Validate the result with email regex
        if (result and result != "NOT_FOUND" and
            _valid_email(result)):
            return result

        return None

    except Exception as e:
        st.sidebar.write(f"⚠️ LLM email extraction failed: {str(e)[:50]}")
        return None

def extract_phone_with_llm(soup: BeautifulSoup, website_url: str):
    """Extract contact phone using LLM"""
    if not (HAS_CLAUDE and CLAUDE_API_KEY and soup):
        return None

    try:
        # Get page content
        page_text = soup.get_text(" ", strip=True)[:1500]

        # Create focused prompt for phone extraction
        prompt = f"""
        Extract the main contact phone number from this dental practice website content.

        Website URL: {website_url}
        Content: {page_text}

        Instructions:
        - Find the primary contact phone number
        - Look for contact sections, header, footer
        - Return ONLY the phone number (e.g., "(555) 123-4567" or "555-123-4567")
        - If multiple phones, return the main office line
        - If no phone exists, return "NOT_FOUND"

        Phone Number:"""

        result = call_claude_api(prompt)
        if not result:
            return None

        result = result.strip()

        # Validate the result with phone regex
        if (result and result != "NOT_FOUND" and
            _valid_phone(result)):
            return result

        return None

    except Exception as e:
        st.sidebar.write(f"⚠️ LLM phone extraction failed: {str(e)[:50]}")
        return None

def extract_appointment_channels_with_llm(soup: BeautifulSoup, website_url: str):
    """Extract appointment booking methods using LLM"""
    if not (HAS_CLAUDE and CLAUDE_API_KEY and soup):
        return None, None

    try:
        # Get page content
        page_text = soup.get_text(" ", strip=True)[:2000]

        # Create focused prompt for appointment channels
        prompt = f"""
        Analyze this dental practice website to identify appointment booking methods.

        Website URL: {website_url}
        Content: {page_text}

        Instructions:
        - Identify how patients can book appointments
        - Be VERY concise - use minimal words
        - Look for: online booking, phone numbers, forms, third-party systems

        Return in this exact format:
        CHANNELS: [concise list, max 5 words]
        SCORE: [Phone-only/Phone + Online Form/Phone + Advanced System]

        Appointment Analysis:"""

        result = call_claude_api(prompt)
        if not result:
            return None, None

        result = result.strip()

        # Parse the result
        channels = ""
        score = "Phone-only"

        if "CHANNELS:" in result:
            channels_line = result.split("CHANNELS:")[1].split("SCORE:")[0].strip()
            channels = channels_line

        if "SCORE:" in result:
            score_line = result.split("SCORE:")[1].strip()
            score = score_line

        return channels, score

    except Exception as e:
        st.sidebar.write(f"⚠️ LLM appointment channels extraction failed: {str(e)[:50]}")
        return None, None

def extract_insurance_info_with_llm(soup: BeautifulSoup, website_url: str):
    """Extract insurance information using LLM"""
    if not (HAS_CLAUDE and CLAUDE_API_KEY and soup):
        return None

    try:
        # Get page content
        page_text = soup.get_text(" ", strip=True)[:2000]

        # Create focused prompt for insurance info
        prompt = f"""
        Extract insurance information from this dental practice website.

        Website URL: {website_url}
        Content: {page_text}

        Requirements:
        - MAXIMUM 3 lines only
        - Each line maximum 15 words
        - Be specific about insurance plans (Delta Dental, Blue Cross, Cigna, etc.)
        - If no insurance info found, return: "No insurance information found"
        - If they don't accept insurance, return: "Does not accept insurance"
        - Format as simple sentences, not bullet points

        Examples:
        "Accepts most major insurance plans including Delta Dental and Blue Cross"
        "PPO and HMO plans welcome with payment plans available"
        "No insurance information found"
        """

        result = call_claude_api(prompt)
        if not result:
            return None

        result = result.strip()

        if result and result != "NOT_FOUND" and len(result) > 5:
            # Limit to exactly 3 lines maximum
            lines = [line.strip() for line in result.split('\n') if line.strip()]

            # Take only first 3 lines
            if len(lines) > 3:
                lines = lines[:3]

            # Join lines with newline for multi-line display, or space for single line
            if len(lines) > 1:
                return '\n'.join(lines)
            else:
                return lines[0] if lines else result

        return None

    except Exception as e:
        st.sidebar.write(f"⚠️ LLM insurance extraction failed: {str(e)[:50]}")
        return None

def guess_practice_name_from_url_with_llm(website_url: str, soup: BeautifulSoup):
    """Guess practice name from URL and validate with LLM (max 3-4 words)"""
    if not (HAS_CLAUDE and CLAUDE_API_KEY and website_url):
        return ""

    try:
        # Extract potential name from URL
        from urllib.parse import urlparse
        parsed_url = urlparse(website_url.lower())
        domain = parsed_url.netloc.replace('www.', '')
        domain_parts = domain.split('.')[0]  # Get main part before .com/.net etc

        # Common words to remove from domain
        common_words = ['dental', 'dentist', 'clinic', 'practice', 'center', 'office', 'care', 'health', 'medical', 'smile', 'teeth', 'oral']

        # Create URL-based guess
        url_guess = domain_parts.replace('-', ' ').replace('_', ' ')
        for word in common_words:
            url_guess = url_guess.replace(word, '')
        url_guess = ' '.join(url_guess.split()).title()  # Clean and title case

        # Get website content for LLM validation
        page_text = soup.get_text(" ", strip=True)[:1500] if soup else ""

        prompt = f"""
        Guess and validate the dental practice name from this URL and website content.

        URL: {website_url}
        Domain guess: {url_guess}
        Website content: {page_text}

        Instructions:
        - Use the URL domain to guess the practice name
        - Validate the guess against website content
        - Return ONLY the practice name (3-4 words maximum)
        - Use proper title case (e.g., "Smith Family Dentistry")
        - If the URL guess doesn't match website content, use content instead
        - If unclear, return "NOT_FOUND"

        Practice Name:"""

        result = call_claude_api(prompt)
        if not result:
            return ""

        result = result.strip()

        # Validate result
        if (result and result != "NOT_FOUND" and
            len(result) > 0 and len(result) < 50 and
            len(result.split()) <= 4):  # Max 4 words
            return result

        return ""

    except Exception as e:
        st.sidebar.write(f"⚠️ URL name guessing failed: {str(e)[:50]}")
        return ""

def prefill_from_website(website_url: str):
    """LLM-only extraction with URL-based practice name guessing"""
    if not website_url:
        return

    # Initialize all fields and messages
    email_message = phone_message = name_message = address_message = ""
    practice_name = email = phone = addr = maps_link = ""

    # Store the last error for better messaging
    st.session_state.last_fetch_error = None

    # Check if LLM is available
    if not (HAS_CLAUDE and CLAUDE_API_KEY):
        st.session_state.draft.update({
            "website": website_url,
            "email": "",
            "phone": "",
            "practice_name": "",
            "address": "",
            "maps_link": "",
            "email_message": "LLM unavailable. Please fill email manually.",
            "phone_message": "LLM unavailable. Please fill phone manually.",
            "name_message": "LLM unavailable. Please fill practice name manually.",
            "address_message": "LLM unavailable. Please fill address manually.",
        })
        return

    # Fetch webpage
    soup, load_time = fetch_html(website_url)

    if not soup:
        error_type = st.session_state.get("last_fetch_error", "unknown")
        error_messages = {
            "blocked": "Website blocked automated access",
            "not_found": "Website not found",
            "server_error": "Website server error",
            "timeout": "Website took too long to respond",
            "connection": "Could not connect to website",
            "request_error": "Network request failed",
            "failed": "Website fetch failed",
            "unexpected": "Unexpected error occurred",
            "unknown": "Couldn't load website"
        }
        error_msg = error_messages.get(error_type, "Couldn't load website")

        st.session_state.draft.update({
            "website": website_url,
            "email": "",
            "phone": "",
            "practice_name": "",
            "address": "",
            "maps_link": "",
            "email_message": f"{error_msg}. Please fill email manually.",
            "phone_message": f"{error_msg}. Please fill phone manually.",
            "name_message": f"{error_msg}. Please fill practice name manually.",
            "address_message": f"{error_msg}. Please fill address manually.",
        })
        return

    # LLM-ONLY extraction approach
    st.sidebar.write("🤖 Using AI to extract contact details...")

    # Step 1: Guess practice name from URL and validate with LLM
    practice_name = guess_practice_name_from_url_with_llm(website_url, soup)

    # Step 2: Extract all other fields using ONLY LLM
    addr = extract_address_with_llm(soup, website_url)
    email = extract_email_with_llm(soup, website_url)
    phone = extract_phone_with_llm(soup, website_url)

    # Step 4: Set messages for missing information and success indicators
    if not email:
        email_message = "Couldn't get the email from website. Please fill it manually."
    else:
        st.sidebar.success(f"✅ Email extracted: {email}")

    if not phone:
        phone_message = "Couldn't get the phone from website. Please fill it manually."
    else:
        st.sidebar.success(f"✅ Phone extracted: {phone}")

    if not practice_name:
        name_message = "Couldn't get the practice name from website. Please fill it manually."
    else:
        st.sidebar.success(f"✅ Practice name extracted: {practice_name[:40]}{'...' if len(practice_name) > 40 else ''}")

    if not addr:
        address_message = "Couldn't get the address from website. Please fill it manually."
    else:
        st.sidebar.success(f"✅ Address extracted: {addr[:40]}{'...' if len(addr) > 40 else ''}")

    # Update session state with results and messages
    st.session_state.draft.update({
        "website": website_url,
        "email": email or "",
        "phone": phone or "",
        "practice_name": practice_name or "",
        "address": addr or "",
        "maps_link": maps_link or "",
        "email_message": email_message,
        "phone_message": phone_message,
        "name_message": name_message,
        "address_message": address_message,
    })

@st.cache_data(show_spinner=False, ttl=3600)
def fetch_html(url: str):
    if not url:
        return None, None

    st.sidebar.write(f"🌐 Fetching website: {url[:50]}...")

    try:
        # More comprehensive headers to avoid blocking
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.5",
            "Accept-Encoding": "gzip, deflate",
            "Connection": "keep-alive",
            "Upgrade-Insecure-Requests": "1"
        }

        t0 = time.time()
        r = requests.get(url, headers=headers, timeout=15, allow_redirects=True)
        elapsed = time.time() - t0

        st.sidebar.write(f"📡 Website Response: {r.status_code} ({elapsed:.2f}s)")

        if r.status_code == 200:
            st.sidebar.write("✅ Website fetched successfully")
            return BeautifulSoup(r.text, "html.parser"), elapsed
        elif r.status_code == 403:
            st.sidebar.write("⚠️ Website blocked automated access (403 Forbidden)")
            st.session_state.last_fetch_error = "blocked"
        elif r.status_code == 404:
            st.sidebar.write("❌ Website not found (404)")
            st.session_state.last_fetch_error = "not_found"
        elif r.status_code >= 500:
            st.sidebar.write(f"⚠️ Website server error ({r.status_code})")
            st.session_state.last_fetch_error = "server_error"
        else:
            st.sidebar.write(f"❌ Website fetch failed: {r.status_code}")
            st.session_state.last_fetch_error = "failed"
    except requests.exceptions.Timeout:
        st.sidebar.write("⏰ Website request timed out")
        st.session_state.last_fetch_error = "timeout"
    except requests.exceptions.ConnectionError:
        st.sidebar.write("🔌 Could not connect to website")
        st.session_state.last_fetch_error = "connection"
    except requests.exceptions.RequestException as e:
        st.sidebar.write(f"❌ Request error: {str(e)[:50]}")
        st.session_state.last_fetch_error = "request_error"
    except Exception as e:
        st.sidebar.write(f"❌ Unexpected error: {str(e)[:50]}")
        st.session_state.last_fetch_error = "unexpected"

    return None, None

@st.cache_data(show_spinner=False, ttl=3600)
def get_domain(url: str):
    try:
        netloc = urlparse(url).netloc.lower()
        if netloc.startswith("www."): netloc = netloc[4:]
        return netloc
    except Exception:
        return None


# --- Google Places ---
@st.cache_data(show_spinner=False, ttl=3600)
def places_text_search(query: str):
    if not PLACES_API_KEY:
        st.sidebar.write("❌ Places API Key missing")
        return None

    st.sidebar.write(f"🔍 Making Places text search: {query[:50]}...")
    url = "https://maps.googleapis.com/maps/api/place/textsearch/json"
    params = {"query": query, "key": PLACES_API_KEY}

    try:
        r = requests.get(url, params=params, timeout=10)
        st.sidebar.write(f"📡 Places API Response Status: {r.status_code}")

        if r.status_code == 200:
            data = r.json()
            st.sidebar.write(f"✅ Places API Success - Results: {len(data.get('results', []))}")
            return data
        else:
            st.sidebar.write(f"❌ Places API Error: {r.text[:200]}")
            return None
    except Exception as e:
        st.sidebar.write(f"❌ Places API Exception: {str(e)}")
        return None

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
        if js and js.get("status") == "OK" and js.get("results"):
            return js["results"][0].get("place_id")

    for q in queries:
        js = places_find_place(q)
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

def calculate_separate_ratings(details: dict):
    """Calculate all-time average and recent 10 ratings separately"""
    if not details or details.get("status") != "OK":
        return "Search limited", "Search limited"

    res = details.get("result", {})
    all_time_rating = res.get("rating")
    reviews = res.get("reviews", []) or []

    # Calculate average of recent 10 ratings
    recent_ratings = []
    for rv in reviews[:10]:  # Google typically returns up to 5 recent reviews
        rating = rv.get("rating")
        if rating is not None:
            recent_ratings.append(rating)

    all_time_str = f"{all_time_rating}/5" if all_time_rating is not None else "Search limited"

    if recent_ratings:
        recent_avg = sum(recent_ratings) / len(recent_ratings)
        recent_str = f"{recent_avg:.1f}/5 (from {len(recent_ratings)} recent reviews)"
    else:
        recent_str = "No recent reviews available"

    return all_time_str, recent_str

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

@st.cache_data(show_spinner=False, ttl=3600)
def social_presence_from_site(_soup: BeautifulSoup):
    """Extract social media presence with comprehensive search including text-based detection"""
    if not _soup:
        return {"platforms": [], "links": {}, "summary": "None"}

    platforms_found = {}

    # STEP 1: Search for any text mentioning social media accounts (as requested)
    page_text = _soup.get_text(" ", strip=True)

    # Search for Facebook references in text
    fb_patterns = [
        r"facebook\.com/[\w./-]+",
        r"@[\w.]+\s*on\s*facebook",
        r"facebook[:\s]*[@]?[\w.]+",
        r"fb\.com/[\w./-]+",
        r"find us on facebook[:\s]*[@]?[\w.]*"
    ]

    for pattern in fb_patterns:
        matches = re.findall(pattern, page_text, re.IGNORECASE)
        if matches:
            # Take the first match and try to construct a proper URL
            match = matches[0].strip()
            if match.startswith(('facebook.com/', 'fb.com/')):
                if not match.startswith('http'):
                    platforms_found["Facebook"] = f"https://www.{match}"
                else:
                    platforms_found["Facebook"] = match
            break

    # Search for Instagram references in text
    ig_patterns = [
        r"instagram\.com/[\w./-]+",
        r"@[\w.]+\s*on\s*instagram",
        r"instagram[:\s]*[@]?[\w.]+",
        r"insta[:\s]*[@]?[\w.]+"
    ]

    for pattern in ig_patterns:
        matches = re.findall(pattern, page_text, re.IGNORECASE)
        if matches:
            match = matches[0].strip()
            if 'instagram.com/' in match:
                if not match.startswith('http'):
                    platforms_found["Instagram"] = f"https://www.{match}"
                else:
                    platforms_found["Instagram"] = match
            break

    # Search for Twitter/X references in text
    twitter_patterns = [
        r"twitter\.com/[\w./-]+",
        r"x\.com/[\w./-]+",
        r"@[\w.]+\s*on\s*twitter",
        r"twitter[:\s]*[@]?[\w.]+",
        r"tweet\s*[@]?[\w.]+"
    ]

    for pattern in twitter_patterns:
        matches = re.findall(pattern, page_text, re.IGNORECASE)
        if matches:
            match = matches[0].strip()
            if any(domain in match for domain in ['twitter.com/', 'x.com/']):
                if not match.startswith('http'):
                    platforms_found["Twitter"] = f"https://www.{match}"
                else:
                    platforms_found["Twitter"] = match
            break

    # Search for Yelp references in text
    yelp_patterns = [
        r"yelp\.com/biz/[\w./-]+",
        r"yelp[:\s]*[\w.\s-]+",
        r"find us on yelp"
    ]

    for pattern in yelp_patterns:
        matches = re.findall(pattern, page_text, re.IGNORECASE)
        if matches:
            match = matches[0].strip()
            if 'yelp.com/biz/' in match:
                if not match.startswith('http'):
                    platforms_found["Yelp"] = f"https://www.{match}"
                else:
                    platforms_found["Yelp"] = match
            break

    # STEP 2: If text search didn't find everything, search HTML links more broadly
    all_links = [a.get("href", "") for a in _soup.find_all("a", href=True)]

    # Define patterns that suggest it's NOT the practice's profile (more selective now)
    exclude_patterns = [
        "/sharer", "/share.php", "/plugins", "/tr/", "/intent/", "/embed/",
        "oauth", "login", "api.facebook", "developers.", "business.facebook.com/help"
    ]

    for href in all_links:
        href_lower = href.lower()

        # Skip obvious sharing/widget links
        if any(pattern in href_lower for pattern in exclude_patterns):
            continue

        # Facebook detection - be more permissive
        if "facebook.com/" in href_lower and "Facebook" not in platforms_found:
            # More inclusive - accept most facebook.com links that aren't sharing widgets
            if href_lower.count("/") >= 3:  # Has some path after facebook.com
                platforms_found["Facebook"] = href

        # Instagram detection - more permissive
        elif "instagram.com/" in href_lower and "Instagram" not in platforms_found:
            if href_lower.count("/") >= 3:  # Has some path after instagram.com
                platforms_found["Instagram"] = href

        # Twitter/X detection - more permissive
        elif ("twitter.com/" in href_lower or "x.com/" in href_lower) and "Twitter" not in platforms_found:
            if href_lower.count("/") >= 3:  # Has some path after twitter.com/x.com
                platforms_found["Twitter"] = href

        # Yelp detection
        elif "yelp.com/biz/" in href_lower and "Yelp" not in platforms_found:
            platforms_found["Yelp"] = href

    # STEP 3: Look for social media icons or widgets (even if no direct links)
    # Search for common social media class names and data attributes
    social_elements = []

    # Look for Font Awesome icons, common CSS classes, and data attributes
    for element in _soup.find_all(['i', 'span', 'div', 'a'], class_=True):
        classes = ' '.join(element.get('class', [])).lower()
        if any(social in classes for social in ['fa-facebook', 'facebook', 'fb-', 'icon-facebook']):
            if "Facebook" not in platforms_found:
                # Try to find a parent link or data attribute
                parent_link = element.find_parent('a')
                if parent_link and parent_link.get('href'):
                    href = parent_link.get('href')
                    if 'facebook.com' in href.lower():
                        platforms_found["Facebook"] = href

        elif any(social in classes for social in ['fa-instagram', 'instagram', 'ig-', 'icon-instagram']):
            if "Instagram" not in platforms_found:
                parent_link = element.find_parent('a')
                if parent_link and parent_link.get('href'):
                    href = parent_link.get('href')
                    if 'instagram.com' in href.lower():
                        platforms_found["Instagram"] = href

    # Format results
    platform_list = list(platforms_found.keys())

    if len(platform_list) == 4:
        summary = "Facebook, Instagram, Twitter, Yelp"
    elif len(platform_list) >= 3:
        summary = ", ".join(platform_list)
    elif len(platform_list) == 2:
        summary = ", ".join(platform_list)
    elif len(platform_list) == 1:
        summary = platform_list[0]
    else:
        summary = "None"

    return {
        "platforms": platform_list,
        "links": platforms_found,
        "summary": summary
    }

@st.cache_data(show_spinner=False, ttl=3600)
def comprehensive_llm_analysis(_soup: BeautifulSoup, website_url: str, practice_name: str, reviews: list):
    """Single comprehensive LLM analysis to avoid multiple API calls"""
    if not (HAS_CLAUDE and CLAUDE_API_KEY and _soup):
        return None

    # Use URL as cache key with hash for better memory management
    cache_key = hashlib.md5(f"{website_url}_{practice_name}_{len(reviews or [])}".encode()).hexdigest()

    # Check advanced cache first
    cached_result = _advanced_cache.get(cache_key)
    if cached_result:
        return cached_result

    try:
        # Prepare all data for single analysis
        page_text = _soup.get_text(" ", strip=True)[:2500]  # Reduced limit
        links = [a.get("href") or "" for a in _soup.find_all("a", href=True)]

        # Filter social media links - be more comprehensive
        social_platforms = ["facebook", "instagram", "twitter", "x.com", "yelp", "fb.com", "ig.com"]
        social_links = [l for l in links[:50] if any(platform in l.lower() for platform in social_platforms)]

        # Also search for social media mentions in text
        social_text_mentions = []
        for platform in ["Facebook", "Instagram", "Twitter", "Yelp"]:
            if platform.lower() in page_text.lower():
                social_text_mentions.append(f"'{platform}' mentioned in text")

        if social_text_mentions:
            social_links.extend(social_text_mentions)

        # Basic counts
        img_count = len(_soup.find_all("img"))
        vid_count = len(_soup.find_all(["video", "source"]))

        # Review text (limit to prevent timeout)
        review_texts = []
        for review in (reviews or [])[:5]:  # Reduced to 5 reviews
            text = review.get("text", "").strip()
            if text:
                review_texts.append(text[:200])  # Limit each review text

        reviews_context = " | ".join(review_texts) if review_texts else "No reviews available"

        # Single comprehensive prompt
        prompt = f"""
        You are an expert Online Marketing professional specializing in dental practices. Analyze this dental practice website comprehensively and return a JSON response with actionable marketing insights:

        Practice: {practice_name or "Dental Practice"}
        Website: {website_url}
        Content: {page_text[:800]}...

        Social Media Links Found: {social_links[:5]}
        Visual Content: {img_count} images, {vid_count} videos
        Sample Reviews: {reviews_context[:500]}

        Return JSON with ALL sections:
        {{
            "social_media": {{
                "platforms": ["Facebook", "Instagram", "Twitter", "Yelp"],
                "links": {{"Facebook": "url_or_null", "Instagram": "url_or_null", "Twitter": "url_or_null", "Yelp": "url_or_null"}},
                "advice": "Brief social media strategy advice",
                "visibility_insights": "• Implement local SEO with city + dentist keywords\\n• Create Google My Business posts weekly\\n• Build local directory citations"
            }},
            "reputation": {{
                "sentiment": "Overall review sentiment summary",
                "positive_themes": "Top positive themes (comma-separated)",
                "negative_themes": "Top negative themes or 'None detected'",
                "advice": "Brief reputation management advice"
            }},
            "marketing": {{
                "content_quality": "Website content assessment",
                "visual_effectiveness": "Photo/video marketing assessment",
                "key_recommendations": "Top 3 marketing improvements",
                "advertising_advice": "Marketing tools recommendation"
            }}
        }}

        CRITICAL REQUIREMENTS:
        1. For visibility_insights: Provide exactly 3 actionable bullet points formatted as "• Point 1\\n• Point 2\\n• Point 3"
        2. Each bullet point should be specific, actionable advice a dental practice can implement immediately
        3. Focus on: local SEO, Google My Business, online directories, website optimization, social media presence
        4. Act as an expert marketing consultant - give professional, practical advice
        5. Keep bullet points under 60 characters each for clear display

        For social media links, only include actual practice profile URLs, not general pages or sharing widgets.
        """

        response_text = call_claude_api(prompt)
        if not response_text:
            return None

        # Parse response
        response_text = response_text.strip()
        if "```json" in response_text:
            json_text = response_text.split("```json")[1].split("```")[0].strip()
        else:
            json_text = response_text

        result = json.loads(json_text)

        # Store in advanced cache
        _advanced_cache.put(cache_key, result)

        return result

    except Exception as e:
        st.sidebar.write(f"⚠️ Comprehensive LLM analysis failed: {str(e)[:100]}")
        return None

# Async LLM processing for improved performance
async def async_llm_call(prompt: str, model_name: str = 'claude-3-haiku-20240307'):
    """Async wrapper for LLM API calls"""
    if not (HAS_CLAUDE and CLAUDE_API_KEY):
        return None

    try:
        loop = asyncio.get_event_loop()

        # Run the blocking LLM call in a thread pool
        with concurrent.futures.ThreadPoolExecutor() as executor:
            response = await loop.run_in_executor(executor, call_claude_api, prompt, model_name)
            return response
    except Exception as e:
        st.sidebar.write(f"⚠️ Async LLM call failed: {str(e)[:100]}")
        return None

async def batch_llm_analysis(prompts_dict: dict):
    """Process multiple LLM prompts concurrently"""
    if not prompts_dict:
        return {}

    # Create async tasks for all prompts
    tasks = {}
    for key, prompt in prompts_dict.items():
        tasks[key] = asyncio.create_task(async_llm_call(prompt))

    # Wait for all tasks to complete
    results = {}
    for key, task in tasks.items():
        try:
            results[key] = await task
        except Exception as e:
            st.sidebar.write(f"⚠️ Batch analysis failed for {key}: {str(e)[:50]}")
            results[key] = None

    return results

def run_async_llm_analysis(prompts_dict: dict):
    """Synchronous wrapper for async batch processing"""
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        return loop.run_until_complete(batch_llm_analysis(prompts_dict))
    except Exception as e:
        st.sidebar.write(f"⚠️ Async analysis wrapper failed: {str(e)[:100]}")
        return {}
    finally:
        loop.close()

# Streaming and progress support
def stream_llm_analysis_with_progress(soup, website_url, practice_name, reviews):
    """Streamlined LLM analysis with timeout protection"""
    if not (HAS_CLAUDE and CLAUDE_API_KEY and soup):
        return None

    try:
        # Quick cache check
        cache_key = hashlib.md5(f"{website_url}_{practice_name}_{len(reviews or [])}".encode()).hexdigest()
        cached_result = _advanced_cache.get(cache_key)
        if cached_result:
            return cached_result

        # Fast data preparation
        page_text = soup.get_text(" ", strip=True)[:1500]  # Reduced from 2500
        links = [a.get("href") or "" for a in soup.find_all("a", href=True)]
        social_links = [l for l in links[:15] if any(platform in l.lower() for platform in ["facebook", "instagram", "twitter", "x.com", "yelp"])][:3]  # Limit to 3

        # Simplified prompt for faster processing
        prompt = f"""
        Analyze this dental practice website and return JSON with marketing insights:

        Practice: {practice_name or "Dental Practice"}
        Website: {website_url}
        Content: {page_text[:600]}...
        Social Links: {social_links}

        Return JSON:
        {{
            "social_media": {{
                "platforms": ["Facebook", "Instagram", "Twitter", "Yelp"],
                "links": {{"Facebook": "url_or_null", "Instagram": "url_or_null", "Twitter": "url_or_null", "Yelp": "url_or_null"}},
                "advice": "Brief social media strategy advice",
                "visibility_insights": "• Optimize Google My Business\\n• Add location-based keywords\\n• Build online directory listings"
            }},
            "reputation": {{
                "sentiment": "Review sentiment summary",
                "positive_themes": "Top positive themes",
                "negative_themes": "Top negative themes or 'None detected'",
                "advice": "Brief reputation management advice"
            }},
            "marketing": {{
                "content_quality": "Website content assessment",
                "key_recommendations": "Top 3 marketing improvements",
                "advertising_advice": "Marketing tools recommendation"
            }}
        }}

        Keep it concise and actionable.
        """

        # Call API with shorter timeout
        response_text = call_claude_api(prompt, timeout=15)  # Reduced from 30
        if not response_text:
            return None

        # Fast JSON parsing
        response_text = response_text.strip()
        if "```json" in response_text:
            json_text = response_text.split("```json")[1].split("```")[0].strip()
        else:
            json_text = response_text

        result = json.loads(json_text)

        # Cache results
        _advanced_cache.put(cache_key, result)
        return result

    except Exception as e:
        # Return None on any error - the app will continue with basic analysis
        return None

def extract_social_media_with_llm(links, soup):
    """Use Claude AI to identify social media profile links"""
    if not (HAS_CLAUDE and CLAUDE_API_KEY):
        return None

    try:
        # Prepare context for LLM
        page_text = soup.get_text(" ", strip=True)[:2000]  # Limit context
        links_text = "\n".join([f"- {link}" for link in links[:50] if any(platform in link.lower() for platform in ["facebook", "instagram", "twitter", "x.com", "yelp"])])

        if not links_text:
            return None

        prompt = f"""
        Analyze this dental practice website content and identify OFFICIAL social media profile links.

        Website context: {page_text[:500]}...

        Potential social media links found:
        {links_text}

        For each link, determine if it's an OFFICIAL profile for this dental practice (not ads, general pages, or unrelated profiles).

        Return ONLY a JSON object with this exact format:
        {{
            "links": {{
                "Facebook": "actual_facebook_url_or_null",
                "Instagram": "actual_instagram_url_or_null",
                "Twitter": "actual_twitter_url_or_null",
                "Yelp": "actual_yelp_url_or_null"
            }}
        }}

        Rules:
        - Only include URLs that are clearly official practice profiles
        - Use null for platforms with no official presence
        - Yelp business pages count as official presence
        - Personal profiles or general company pages don't count
        """

        response_text = call_claude_api(prompt)
        if not response_text:
            return None

        # Parse LLM response
        response_text = response_text.strip()
        if "```json" in response_text:
            json_text = response_text.split("```json")[1].split("```")[0].strip()
        else:
            json_text = response_text

        result = json.loads(json_text)
        return result

    except Exception as e:
        st.sidebar.write(f"LLM extraction error: {str(e)[:100]}")
        return None

def analyze_marketing_signals_with_llm(_soup: BeautifulSoup, website_url: str, practice_name: str = ""):
    """Enhanced marketing analysis using Claude AI"""
    if not (HAS_CLAUDE and CLAUDE_API_KEY and _soup):
        return None

    try:
        # Extract website content and marketing elements
        page_text = _soup.get_text(" ", strip=True)[:3000]  # Limit context
        html_content = str(_soup)[:5000]  # Limited HTML for analysis

        # Basic counts
        img_count = len(_soup.find_all("img"))
        vid_count = len(_soup.find_all(["video", "source"]))

        # Find marketing-related elements
        scripts = [script.get("src", "") for script in _soup.find_all("script", src=True)]
        meta_tags = [meta.get("name", "") + ":" + meta.get("content", "") for meta in _soup.find_all("meta", attrs={"name": True, "content": True})]

        prompt = f"""
        Analyze this dental practice website for marketing effectiveness and provide actionable insights:

        Practice: {practice_name or "Dental Practice"}
        Website: {website_url}

        Content Overview: {page_text[:1000]}...

        Technical Elements:
        - Images: {img_count}
        - Videos: {vid_count}
        - Script sources: {scripts[:10]}
        - Meta tags: {meta_tags[:5]}

        Analyze and return JSON with:
        {{
            "content_quality": "Assessment of website content effectiveness",
            "visual_appeal": "Analysis of photos/videos and visual elements",
            "seo_signals": "SEO optimization status and recommendations",
            "conversion_optimization": "How easy it is for patients to book appointments from the website",
            "patient_engagement": "How well the site engages potential patients",
            "marketing_tools": "Detected marketing/tracking tools analysis",
            "key_recommendations": "Top 3 actionable marketing improvements"
        }}

        Focus on dental practice marketing best practices:
        - Patient testimonials and before/after photos
        - Clear call-to-actions (book appointment, call now)
        - Trust signals (certifications, awards, team photos)
        - Local SEO optimization
        - Mobile-friendliness
        - Service descriptions and benefits
        - Contact information prominence
        - Emergency dental care messaging
        """

        response_text = call_claude_api(prompt)
        if not response_text:
            return None

        # Parse LLM response
        response_text = response_text.strip()
        if "```json" in response_text:
            json_text = response_text.split("```json")[1].split("```")[0].strip()
        else:
            json_text = response_text

        result = json.loads(json_text)
        return result

    except Exception as e:
        st.sidebar.write(f"LLM marketing analysis error: {str(e)[:100]}")
        return None

def media_count_from_site(_soup: BeautifulSoup):
    """Enhanced media analysis with content quality assessment"""
    if not _soup: return "Search limited"

    imgs = _soup.find_all("img")
    vids = _soup.find_all(["video","source"])

    # Basic count
    img_count = len(imgs)
    vid_count = len(vids)

    # Note: Visual content analysis moved to comprehensive_llm_analysis for performance

    return f"{img_count} photos, {vid_count} videos"

def advertising_signals(_soup: BeautifulSoup):
    """Enhanced advertising and tracking analysis"""
    if not _soup: return "Search limited"
    html = str(_soup)
    sig = []

    # Enhanced tracking detection
    if "gtag(" in html or "gtag.js" in html or "www.googletagmanager.com" in html:
        sig.append("Google Analytics/GTM")
    if "fbq(" in html:
        sig.append("Facebook Pixel")
    if "google-site-verification" in html:
        sig.append("Google Search Console")
    if "linkedin.com/in" in html or "linkedin insight" in html.lower():
        sig.append("LinkedIn Tracking")
    if "_gaq" in html or "ga(" in html:
        sig.append("Google Analytics (Legacy)")
    if "hotjar" in html.lower():
        sig.append("Hotjar")
    if "intercom" in html.lower():
        sig.append("Intercom Chat")
    if "zendesk" in html.lower() or "zopim" in html.lower():
        sig.append("Zendesk Chat")

    detected_tools = ", ".join(sig) if sig else "None detected"

    # Note: Marketing tools analysis moved to comprehensive_llm_analysis for performance

    return detected_tools

def analyze_website_conversion_elements(soup: BeautifulSoup):
    """Analyze how well the website encourages visitors to become patients"""
    if not soup:
        return "Could not analyze website"

    html = str(soup).lower()
    text = soup.get_text(" ", strip=True).lower()

    user_friendly_features = []

    # Call-to-action buttons (action prompts)
    action_keywords = ['book', 'appointment', 'call now', 'schedule', 'contact', 'get started', 'free consultation']
    action_count = sum(1 for keyword in action_keywords if keyword in text)
    if action_count >= 3:
        user_friendly_features.append("Easy to find appointment buttons")
    elif action_count > 0:
        user_friendly_features.append("Some appointment options available")

    # Contact information visibility
    if 'phone' in text and ('call' in text or 'tel:' in html):
        user_friendly_features.append("Phone number clearly displayed")

    # Contact forms
    forms = soup.find_all('form')
    if len(forms) > 1:
        user_friendly_features.append("Multiple ways to contact practice")
    elif forms:
        user_friendly_features.append("Contact form available")

    # Credibility indicators
    trust_keywords = ['certified', 'award', 'years experience', 'licensed', 'dds', 'dmd', 'insurance accepted']
    trust_count = sum(1 for keyword in trust_keywords if keyword in text)
    if trust_count >= 2:
        user_friendly_features.append("Shows doctor credentials and experience")

    return '; '.join(user_friendly_features) if user_friendly_features else "Website could be more patient-friendly"

def analyze_content_marketing(soup: BeautifulSoup, website_url: str = ""):
    """Analyze content marketing strategy and quality"""
    if not soup:
        return "Search limited"

    content_signals = []
    text = soup.get_text(" ", strip=True).lower()

    # Blog/content sections
    blog_indicators = ['blog', 'articles', 'news', 'tips', 'education', 'learn more']
    if any(indicator in text for indicator in blog_indicators):
        content_signals.append("Educational content")

    # Service descriptions
    service_keywords = ['services', 'treatment', 'procedure', 'cleaning', 'whitening', 'implant', 'orthodontic']
    service_count = sum(1 for keyword in service_keywords if keyword in text)
    if service_count >= 4:
        content_signals.append("Comprehensive service descriptions")
    elif service_count > 0:
        content_signals.append("Basic service information")

    # Patient testimonials/reviews
    testimonial_keywords = ['testimonial', 'review', 'patient says', 'happy patient', 'success story']
    if any(keyword in text for keyword in testimonial_keywords):
        content_signals.append("Patient testimonials")

    # Before/after content
    if 'before' in text and 'after' in text:
        content_signals.append("Before/after showcases")

    return '; '.join(content_signals) if content_signals else "Basic content strategy"

def analyze_local_seo_signals(soup: BeautifulSoup, address: str = ""):
    """Analyze local SEO optimization"""
    if not soup:
        return "Search limited"

    html = str(soup).lower()
    text = soup.get_text(" ", strip=True).lower()

    local_signals = []

    # Schema markup
    if 'schema.org' in html and ('localbusiness' in html or 'dentist' in html):
        local_signals.append("Schema markup")

    # NAP consistency (Name, Address, Phone)
    if address:
        address_parts = address.lower().split(',')
        if len(address_parts) > 0 and address_parts[0].strip() in text:
            local_signals.append("Address consistency")

    # Local keywords
    local_keywords = ['dentist near', 'dental practice', 'local dentist', 'area dentist', 'neighborhood']
    local_count = sum(1 for keyword in local_keywords if keyword in text)
    if local_count >= 2:
        local_signals.append("Local keyword optimization")

    # Google My Business integration
    if 'google.com/maps' in html or 'google my business' in text:
        local_signals.append("GMB integration")

    # Location pages
    location_keywords = ['location', 'directions', 'hours', 'address', 'visit us']
    if sum(1 for keyword in location_keywords if keyword in text) >= 3:
        local_signals.append("Location information complete")

    return '; '.join(local_signals) if local_signals else "Limited local SEO"

def generate_marketing_insights(soup: BeautifulSoup, website_url: str, practice_name: str, social_data: dict, photos_count: int, advertising_tools: str):
    """Generate AI-powered marketing insights and recommendations"""
    if not (HAS_CLAUDE and CLAUDE_API_KEY and soup):
        return "Enable Claude AI for detailed insights"

    try:
        # Gather marketing data
        text_content = soup.get_text(" ", strip=True)[:2000]
        conversion_elements = analyze_website_conversion_elements(soup)
        content_strategy = analyze_content_marketing(soup, website_url)
        local_seo = analyze_local_seo_signals(soup)

        # Social media status
        social_platforms = []
        if social_data:
            for platform, status in social_data.items():
                if status and status != "❌":
                    social_platforms.append(platform)

        prompt = f"""
        Analyze this dental practice's marketing and provide EXACTLY 3 short, actionable recommendations:

        Practice: {practice_name}
        Current Status:
        - Social Media: {', '.join(social_platforms) if social_platforms else 'Limited presence'}
        - Photos: {photos_count} on Google
        - Tools: {advertising_tools}
        - Website Features: {conversion_elements}

        Requirements:
        - EXACTLY 3 bullet points only
        - Maximum 15 words per point
        - Straight to the point, no fluff
        - Focus on biggest impact improvements
        - Format: • [action]

        Example:
        • Add before/after photos to showcase results
        • Set up online appointment booking system
        • Create Google My Business posts weekly
        """

        result = call_claude_api(prompt)
        if result and result.strip():
            # Ensure exactly 3 lines
            lines = [line.strip() for line in result.strip().split('\n') if line.strip()]
            # Take first 3 lines that start with bullet points
            bullet_lines = [line for line in lines if line.startswith('•')]
            if len(bullet_lines) >= 3:
                return '\n'.join(bullet_lines[:3])
            else:
                return result.strip()
        else:
            return "• Optimize Google My Business with more photos\n• Add patient testimonials to build trust\n• Implement clear call-to-action buttons"

    except Exception as e:
        st.sidebar.write(f"⚠️ Marketing insights error: {str(e)[:50]}")
        return "• Optimize Google My Business profile\n• Add more professional photos\n• Implement online booking system"

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

def appointment_channels_from_site(soup: BeautifulSoup, website_url: str = ""):
    """Enhanced appointment booking analysis with LLM support (max 10 words)"""
    if not soup:
        return "Search limited"

    def limit_to_10_words(text: str) -> str:
        """Limit text to maximum 10 words"""
        words = text.split()
        return ' '.join(words[:10])

    # Try LLM analysis first
    if HAS_CLAUDE and CLAUDE_API_KEY and website_url:
        channels, score = extract_appointment_channels_with_llm(soup, website_url)
        if channels and score:
            # Format the response and limit to 10 words
            full_response = f"{score} - {channels}"
            return limit_to_10_words(full_response)

    # Fallback to traditional analysis (already under 10 words)
    t = soup.get_text(" ", strip=True).lower()
    if any(p in t for p in ["book", "appointment", "schedule", "reserve"]):
        if "calendly" in t or "zocdoc" in t or "square appointments" in t:
            return "Phone + Advanced System"
        return "Phone + Online Form"
    return "Phone-only"

def enhanced_insurance_from_site(soup: BeautifulSoup, website_url: str = ""):
    """Enhanced insurance analysis with LLM support"""
    if not soup:
        return "Search limited"

    # Try LLM analysis first
    if HAS_CLAUDE and CLAUDE_API_KEY and website_url:
        insurance_info = extract_insurance_info_with_llm(soup, website_url)
        if insurance_info:
            return insurance_info

    # Fallback to traditional analysis
    t = soup.get_text(" ", strip=True).lower()
    if "insurance" in t or "we accept" in t or "ppo" in t or "delta dental" in t:
        m = re.search(r"([^.]*insurance[^.]*\.)", t)
        if m:
            # Limit fallback to 3 lines max
            fallback_text = m.group(0)
            if len(fallback_text) > 100:  # If too long, shorten it
                return "Insurance accepted - Check website for details"
            return fallback_text
        return "Insurance accepted - Details on website"
    return "No insurance information found"

def generate_patient_experience_insights(appointment_channels: str, insurance_info: str, office_hours: str):
    """Generate AI insights for patient experience improvements"""
    if not (HAS_CLAUDE and CLAUDE_API_KEY):
        return "• Improve online booking convenience\n• Clarify insurance acceptance\n• Optimize office hours for patients"

    try:
        prompt = f"""
        You are an expert patient experience consultant for dental practices. Analyze this practice's patient convenience data and provide actionable improvement insights.

        Patient Experience Data:
        - Appointment Options Available: {appointment_channels}
        - Insurance Information: {insurance_info}
        - Office Hours (as mentioned in Website): {office_hours}

        Provide exactly 3 actionable bullet points to improve patient experience. Focus on:
        - Appointment booking convenience
        - Insurance clarity and payment options
        - Accessibility and communication improvements

        Format as: • Point 1\n• Point 2\n• Point 3

        Keep each point under 60 characters and immediately actionable.

        Patient Experience Insights:"""

        result = call_claude_api(prompt)
        if not result:
            return "• Improve online booking convenience\n• Clarify insurance acceptance\n• Optimize office hours for patients"

        result = result.strip()

        # Ensure proper bullet point formatting
        if "•" in result:
            return result
        else:
            # Convert to bullet points if not formatted properly
            lines = result.split('\n')[:3]
            bullet_points = []
            for line in lines:
                line = line.strip()
                if line and len(line) > 5:
                    if not line.startswith('•'):
                        line = f"• {line}"
                    bullet_points.append(line)

            if bullet_points:
                return '\n'.join(bullet_points)

        return "• Improve online booking convenience\n• Clarify insurance acceptance\n• Optimize office hours for patients"

    except Exception as e:
        st.sidebar.write(f"⚠️ Patient experience insights failed: {str(e)[:50]}")
        return "• Improve online booking convenience\n• Clarify insurance acceptance\n• Optimize office hours for patients"

# --- Enhanced LLM-based reputation analysis ---
def analyze_review_texts(reviews):
    """Review analysis using ONLY Claude AI LLM - no fallback methods"""
    if not reviews:
        return "Search limited", "Search limited", "Search limited"

    # Use ONLY LLM analysis - no fallbacks
    llm_result = analyze_reviews_with_llm(reviews)
    if llm_result:
        sentiment = llm_result.get("sentiment", "Mostly positive feedback")
        positive_themes = llm_result.get("positive_themes", "Professional staff, clean environment")
        negative_themes = llm_result.get("negative_themes", "None detected")
        return sentiment, positive_themes, negative_themes

    # If LLM is not available or fails, return search limited
    return "Search limited", "Search limited", "Search limited"

def extract_ratings_with_llm(reviews, details):
    """Extract rating information using ONLY LLM"""
    if not (HAS_CLAUDE and CLAUDE_API_KEY and reviews):
        return {
            "all_time_avg": "Search limited",
            "recent_avg": "Search limited",
            "total_count": "Search limited"
        }

    try:
        # Prepare review data for LLM
        review_data = []
        for review in reviews[:20]:  # Analyze up to 20 reviews
            rating = review.get("rating", "")
            text = review.get("text", "").strip()
            time_desc = review.get("relative_time_description", "")
            if rating and text:
                review_data.append(f"Rating: {rating}★, Posted: {time_desc}, Review: {text[:100]}...")

        if not review_data:
            return {
                "all_time_avg": "Search limited",
                "recent_avg": "Search limited",
                "total_count": "Search limited"
            }

        reviews_context = "\n\n".join(review_data)

        prompt = f"""
        Analyze these Google reviews and extract rating statistics:

        {reviews_context}

        Please return a JSON response with:
        {{
            "all_time_avg": "Overall average rating (e.g., '4.2 stars')",
            "recent_avg": "Recent 10 reviews average (e.g., '4.5 stars')",
            "total_count": "Total number of reviews analyzed (e.g., '25 reviews')"
        }}

        Be concise and specific with the numbers.
        """

        response_text = call_claude_api(prompt)
        if not response_text:
            return {
                "all_time_avg": "Search limited",
                "recent_avg": "Search limited",
                "total_count": "Search limited"
            }

        # Parse LLM response
        response_text = response_text.strip()
        if "```json" in response_text:
            json_text = response_text.split("```json")[1].split("```")[0].strip()
        else:
            json_text = response_text

        import json
        result = json.loads(json_text)
        return result

    except Exception as e:
        st.sidebar.write(f"⚠️ LLM rating extraction failed: {str(e)[:50]}")
        return {
            "all_time_avg": "Search limited",
            "recent_avg": "Search limited",
            "total_count": "Search limited"
        }

def analyze_reviews_with_llm(reviews):
    """Use Claude AI to analyze dental practice reviews"""
    if not (HAS_CLAUDE and CLAUDE_API_KEY and reviews):
        return None

    try:
        # Prepare review texts (limit for context)
        review_texts = []
        for i, review in enumerate(reviews[:10]):  # Analyze up to 10 reviews
            text = review.get("text", "").strip()
            rating = review.get("rating", "")
            author = review.get("author_name", "Anonymous")
            if text:
                review_texts.append(f"Review {i+1} ({rating}★ by {author}): {text}")

        if not review_texts:
            return None

        reviews_context = "\n\n".join(review_texts)

        prompt = f"""
        Analyze these Google reviews for a dental practice and provide insights:

        {reviews_context}

        Please analyze and return a JSON response with:
        {{
            "sentiment": "Overall sentiment summary (1 line)",
            "positive_themes": "Top 3 positive themes mentioned (comma-separated)",
            "negative_themes": "Top 3 negative concerns mentioned (comma-separated, or 'None detected' if none)",
            "key_insights": "2-3 key insights for practice improvement"
        }}

        Focus on dental practice specific themes like:
        - Staff friendliness, professionalism
        - Pain management, comfort
        - Cleanliness, hygiene
        - Wait times, scheduling
        - Communication, explanations
        - Billing, insurance issues
        - Office environment
        - Treatment quality

        Keep responses concise and actionable.
        """

        response_text = call_claude_api(prompt)
        if not response_text:
            return None

        # Parse LLM response
        response_text = response_text.strip()
        if "```json" in response_text:
            json_text = response_text.split("```json")[1].split("```")[0].strip()
        else:
            json_text = response_text

        result = json.loads(json_text)
        return result

    except Exception as e:
        st.sidebar.write(f"LLM review analysis error: {str(e)[:100]}")
        return None

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

    # New 4-platform scoring system
    if isinstance(social_present, dict):
        platforms = social_present.get("platforms", [])
        platform_score = len(platforms) * 25  # 25 points per platform
        vis_parts.append(min(platform_score, 100))
    elif isinstance(social_present, str):
        # Fallback for old format
        if social_present == "Facebook, Instagram, Twitter, Yelp":
            vis_parts.append(100)
        elif "," in social_present and len(social_present.split(",")) >= 3:
            vis_parts.append(75)
        elif "," in social_present:
            vis_parts.append(50)
        elif social_present not in ("None", ""):
            vis_parts.append(25)
        else:
            vis_parts.append(0)
    else:
        vis_parts.append(0)

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

    if "ai insights" in metric.lower():
        return "AI-generated recommendations based on website analysis"

    if "social media presence" in metric.lower():
        # Try LLM-based advice first
        llm_advice = generate_social_media_advice_with_llm(value)
        if llm_advice:
            return llm_advice

        # Fallback to rule-based advice
        if isinstance(value, dict):
            platforms = value.get("platforms", [])
            if len(platforms) >= 4: return "You nailed it - excellent social presence!"
            elif len(platforms) == 3: return "Great start! Add remaining platform for complete coverage"
            elif len(platforms) == 2: return "Good foundation. Add 2 more platforms and post regularly"
            elif len(platforms) == 1: return "Expand to Facebook, Instagram, Twitter & Yelp"
            else: return "Create profiles on Facebook, Instagram, Twitter & Yelp"
        else:
            # Old string format fallback
            if "facebook, instagram, twitter, yelp" in s.lower(): return "You nailed it"
            if len([p for p in ["facebook", "instagram", "twitter", "yelp"] if p in s.lower()]) >= 3: return "Almost there! Add missing platform"
            if "facebook" in s or "instagram" in s: return "Add other platforms & post weekly"
            return "Add FB/IG/Twitter/Yelp links; post 2–3×/week"

def format_social_media_with_links(social_data):
    """Format social media presence with hyperlinks for display in reports"""
    if not isinstance(social_data, dict):
        return str(social_data)

    platforms = social_data.get("platforms", [])
    links = social_data.get("links", {})

    if not platforms:
        return "None"

    # Create linked platform names
    linked_platforms = []
    for platform in platforms:
        link = links.get(platform)
        if link and link != "null":  # LLM might return "null" string
            # Clean the link - ensure it's a proper URL
            clean_link = link.strip()
            if not clean_link.startswith(('http://', 'https://')):
                clean_link = 'https://' + clean_link
            linked_platforms.append(f'<a href="{escape(clean_link)}" target="_blank" rel="noopener">{escape(platform)}</a>')
        else:
            linked_platforms.append(escape(platform))

    return ", ".join(linked_platforms)

def generate_social_media_advice_with_llm(social_data):
    """Generate personalized social media advice using Claude"""
    if not (HAS_CLAUDE and CLAUDE_API_KEY):
        return None

    try:
        if isinstance(social_data, dict):
            platforms = social_data.get("platforms", [])
            links = social_data.get("links", {})
        else:
            # Fallback for string format
            platforms = [p.strip() for p in str(social_data).split(",") if p.strip() != "None"]
            links = {}

        platform_count = len(platforms)
        missing_platforms = [p for p in ["Facebook", "Instagram", "Twitter", "Yelp"] if p not in platforms]

        prompt = f"""
        Generate concise social media advice for a dental practice with current presence on: {platforms if platforms else "no platforms"}.

        Missing platforms: {missing_platforms}

        Provide a brief, actionable recommendation (max 15 words) focusing on:
        - Which platforms to prioritize next
        - Content strategy hints
        - Patient engagement tips

        Make it dental practice specific and professional.
        """

        response_text = call_claude_api(prompt)
        if not response_text:
            return None

        advice = response_text.strip()
        # Clean up the response
        if len(advice) > 100:  # Truncate if too long
            advice = advice[:97] + "..."

        return advice

    except Exception as e:
        return None  # Fallback to rule-based advice

def generate_reputation_advice_with_llm(advice_type, value):
    """Generate LLM-powered reputation management advice"""
    if not (HAS_CLAUDE and CLAUDE_API_KEY):
        return None

    try:
        if advice_type == "sentiment":
            prompt = f"""
            A dental practice has this reputation sentiment: "{value}"

            Generate a concise, actionable recommendation (max 12 words) for improving their online reputation.
            Focus on practical steps they can take immediately.
            """

        elif advice_type == "positive":
            if "none detected" in str(value).lower():
                return None  # Use fallback
            prompt = f"""
            A dental practice has these positive review themes: "{value}"

            Generate a brief marketing suggestion (max 12 words) on how to amplify these strengths.
            Focus on leveraging these positives for growth.
            """

        elif advice_type == "negative":
            if "none detected" in str(value).lower():
                return "You nailed it - maintain current quality standards"
            prompt = f"""
            A dental practice has these negative review concerns: "{value}"

            Generate a specific action plan (max 12 words) to address these issues.
            Focus on operational improvements and patient satisfaction.
            """
        else:
            return None

        response_text = call_claude_api(prompt)
        if not response_text:
            return None

        advice = response_text.strip()
        # Clean and truncate if needed
        if len(advice) > 80:
            advice = advice[:77] + "..."

        return advice

    except Exception as e:
        return None  # Fallback to rule-based advice

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
        # Try LLM-based reputation advice
        llm_advice = generate_reputation_advice_with_llm("sentiment", value)
        if llm_advice:
            return llm_advice

        # Fallback to rule-based advice
        if "mostly positive" in s: return "You nailed it"
        if "mixed" in s: return "Fix top negatives & reply to reviews"
        return "Reply to negative themes with solutions"

    if "top positive themes" in metric.lower():
        llm_advice = generate_reputation_advice_with_llm("positive", value)
        if llm_advice:
            return llm_advice
        return "Amplify these themes on website & ads" if ("none detected" not in s) else ""

    if "top negative themes" in metric.lower():
        llm_advice = generate_reputation_advice_with_llm("negative", value)
        if llm_advice:
            return llm_advice

        # Fallback to rule-based advice
        if "none detected" in s: return "You nailed it"
        if "long wait" in s: return "Stagger scheduling & add SMS reminders"
        if "billing" in s: return "Clarify estimates & billing SOP"
        if "front desk" in s: return "Train front desk on empathy scripts"
        return "Tackle top 1–2 negative themes this month"

    if "photos" in metric.lower():
        # Enhanced photo/video advice
        llm_advice = generate_marketing_advice_with_llm("visual_content", value)
        if llm_advice:
            return llm_advice
        return "You nailed it" if ("none" not in s and "0" not in s) else "Upload 10–20 clinic & team photos"

    if "advertising scripts" in metric.lower():
        # Try LLM-based marketing advice
        llm_advice = generate_marketing_advice_with_llm("advertising", value)
        if llm_advice:
            return llm_advice
        return "You nailed it" if ("none" not in s) else "Add GA4/Ads pixel for conversion tracking"

    return ""

def generate_marketing_advice_with_llm(advice_type, value):
    """Generate LLM-powered marketing advice"""
    if not (HAS_CLAUDE and CLAUDE_API_KEY):
        return None

    try:
        if advice_type == "visual_content":
            prompt = f"""
            A dental practice website has: "{value}"

            Generate brief visual content marketing advice (max 12 words) focusing on:
            - Professional photography needs
            - Patient trust building through visuals
            - Before/after content opportunities
            """

        elif advice_type == "advertising":
            if "none detected" in str(value).lower():
                prompt = f"""
                A dental practice has no marketing tracking tools detected.

                Suggest essential marketing tools (max 12 words) for patient acquisition:
                - Which tracking pixels are most important?
                - What should they implement first?
                """
            else:
                prompt = f"""
                A dental practice uses these marketing tools: "{value}"

                Provide optimization advice (max 12 words) for better patient acquisition:
                - Are they missing key tools?
                - How to improve conversion tracking?
                """

        elif advice_type == "content_strategy":
            prompt = f"""
            A dental practice website shows: "{value}"

            Generate content marketing strategy advice (max 12 words) focusing on:
            - Patient education content
            - Trust building elements
            - Local SEO opportunities
            """
        else:
            return None

        response_text = call_claude_api(prompt)
        if not response_text:
            return None

        advice = response_text.strip()
        # Clean and truncate if needed
        if len(advice) > 80:
            advice = advice[:77] + "..."

        return advice

    except Exception as e:
        return None  # Fallback to rule-based advice

def _normalize_url(u: str) -> str:
    if not u: return u
    u = u.strip()
    return ("https://" + u) if not urlparse(u).scheme else u

@st.cache_resource(show_spinner=False)
def _get_gs_worksheet():
    """Build a cached gspread worksheet handle from Streamlit secrets."""
    try:
        svc_info = dict(st.secrets["gcp_service_account"])
        spreadsheet_id = st.secrets["gsheets"]["SPREADSHEET_ID"]
        worksheet_name = st.secrets["gsheets"].get("WORKSHEET_NAME", "Submissions")
    except Exception:
        return None  # secrets missing

    creds = Credentials.from_service_account_info(
        svc_info,
        scopes=["https://www.googleapis.com/auth/spreadsheets"]
    )
    client = gspread.authorize(creds)
    sh = client.open_by_key(spreadsheet_id)
    try:
        ws = sh.worksheet(worksheet_name)
    except gspread.WorksheetNotFound:
        ws = sh.add_worksheet(title=worksheet_name, rows=100, cols=20)
        # add header row once
        ws.append_row(COLUMNS, value_input_option="USER_ENTERED")
    return ws

def append_submission_to_sheet(data: dict) -> bool:
    """
    Appends a single row with the six requested fields.
    Returns True on success, False otherwise. Never raises to the UI.
    """
    ws = _get_gs_worksheet()
    if not ws:
        # Secrets not configured — skip silently but inform user once
        st.warning("Google Sheet isn’t configured. Skipping save.", icon="⚠️")
        return False

    row = [
        data.get("website", ""),
        data.get("doctor_name", ""),
        data.get("email", ""),
        data.get("phone", ""),
        data.get("practice_name", ""),
        data.get("address", ""),
    ]

    row.append(datetime.now(ZoneInfo("Asia/Kolkata")).strftime("%Y-%m-%d %H:%M:%S"))  # IST timestamp
    
    try:
        ws.append_row(row, value_input_option="USER_ENTERED")
        return True
    except Exception as e:
        st.warning(f"Couldn’t save to Google Sheet: {e}", icon="⚠️")
        return False

def build_static_report_html(final, overview, visibility, reputation, marketing, experience, scores, reviews):
    def _kv_table(title, d):
        rows = ""
        for k, v in d.items():
            # Special handling for Social Media Presence to preserve HTML links
            if k == "Social Media Presence" and isinstance(v, str) and "<a href=" in v:
                cell_content = v  # Don't escape HTML links
            elif isinstance(v, str):
                cell_content = escape(v)
            elif v:
                cell_content = escape(json.dumps(v))
            else:
                cell_content = "—"

            rows += f"<tr><th>{escape(k)}</th><td>{cell_content}</td></tr>"

        return f"<section><h2>{title}</h2><table>{rows}</table></section>"

    email = final.get('email', '')

    style = """
    <style>
      * { box-sizing: border-box; }
      body {
        font-family: 'Inter', system-ui, -apple-system, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;
        margin: 0;
        padding: 0;
        line-height: 1.6;
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        min-height: 100vh;
        color: #333;
      }
      .container {
        max-width: 1000px;
        margin: 0 auto;
        padding: 20px;
      }
      .report-card {
        background: #ffffff;
        border-radius: 16px;
        box-shadow: 0 20px 40px rgba(0,0,0,0.1);
        overflow: hidden;
        margin-bottom: 20px;
      }
      .report-header {
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        color: white;
        padding: 40px;
        text-align: center;
        position: relative;
      }
      .report-header::before {
        content: '';
        position: absolute;
        top: 0;
        left: 0;
        right: 0;
        bottom: 0;
        background: url('data:image/svg+xml,<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100"><defs><pattern id="grain" width="100" height="100" patternUnits="userSpaceOnUse"><circle cx="25" cy="25" r="1" fill="%23ffffff" opacity="0.1"/><circle cx="75" cy="75" r="1" fill="%23ffffff" opacity="0.1"/></pattern></defs><rect width="100" height="100" fill="url(%23grain)"/></svg>');
        opacity: 0.3;
      }
      h1 {
        margin: 0 0 10px;
        font-size: 2.5rem;
        font-weight: 700;
        position: relative;
        z-index: 1;
      }
      .practice-name {
        font-size: 1.8rem;
        margin: 0 0 20px;
        opacity: 0.95;
        position: relative;
        z-index: 1;
      }
      .header-info {
        background: rgba(255,255,255,0.15);
        backdrop-filter: blur(10px);
        border: 1px solid rgba(255,255,255,0.2);
        padding: 20px;
        border-radius: 12px;
        margin: 20px auto 0;
        max-width: 600px;
        position: relative;
        z-index: 1;
      }
      .header-info-row {
        display: grid;
        grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
        gap: 15px;
        margin-bottom: 15px;
      }
      .header-info-row:last-child {
        margin-bottom: 0;
      }
      .info-item {
        display: flex;
        flex-direction: column;
      }
      .info-label {
        font-size: 0.85rem;
        opacity: 0.8;
        margin-bottom: 5px;
        text-transform: uppercase;
        letter-spacing: 0.5px;
      }
      .info-value {
        font-weight: 600;
        font-size: 0.95rem;
      }
      .scores-container {
        margin: 30px 0;
        text-align: center;
        position: relative;
        z-index: 1;
      }
      .scores-grid {
        display: grid;
        grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
        gap: 15px;
        margin-top: 20px;
      }
      .score-card {
        background: rgba(255,255,255,0.2);
        backdrop-filter: blur(10px);
        padding: 20px;
        border-radius: 12px;
        border: 1px solid rgba(255,255,255,0.3);
        text-align: center;
      }
      .score-value {
        font-size: 2rem;
        font-weight: 700;
        margin-bottom: 5px;
      }
      .score-label {
        font-size: 0.9rem;
        opacity: 0.9;
      }
      .content {
        padding: 40px;
      }
      h2 {
        color: #4c1d95;
        font-size: 1.5rem;
        margin: 0 0 20px;
        font-weight: 700;
        display: flex;
        align-items: center;
        gap: 10px;
      }
      h2::before {
        content: '';
        width: 4px;
        height: 24px;
        background: linear-gradient(135deg, #667eea, #764ba2);
        border-radius: 2px;
      }
      section {
        margin-bottom: 35px;
        background: #f8fafc;
        padding: 25px;
        border-radius: 12px;
        border: 1px solid #e2e8f0;
        position: relative;
        overflow: hidden;
      }
      section::before {
        content: '';
        position: absolute;
        top: 0;
        left: 0;
        width: 100%;
        height: 4px;
        background: linear-gradient(90deg, #667eea, #764ba2);
      }
      table {
        width: 100%;
        border-collapse: collapse;
        margin: 0;
        background: white;
        border-radius: 8px;
        overflow: hidden;
        box-shadow: 0 1px 3px rgba(0,0,0,0.1);
      }
      th, td {
        padding: 16px 20px;
        text-align: left;
        border-bottom: 1px solid #e2e8f0;
      }
      th {
        background: linear-gradient(135deg, #f1f5f9, #e2e8f0);
        font-weight: 600;
        color: #475569;
        width: 35%;
        font-size: 0.9rem;
        text-transform: uppercase;
        letter-spacing: 0.5px;
      }
      td {
        color: #334155;
        font-weight: 500;
      }
      tr:last-child th,
      tr:last-child td {
        border-bottom: none;
      }
      tr:hover {
        background: #f8fafc;
      }
      a {
        color: #3b82f6;
        text-decoration: none;
        font-weight: 600;
        transition: all 0.2s ease;
      }
      a:hover {
        color: #1d4ed8;
        text-decoration: underline;
      }
      .reviews-list {
        background: white;
        padding: 0;
        border-radius: 8px;
        overflow: hidden;
        box-shadow: 0 1px 3px rgba(0,0,0,0.1);
      }
      .reviews-list ul {
        list-style: none;
        padding: 0;
        margin: 0;
      }
      .reviews-list li {
        padding: 20px;
        border-bottom: 1px solid #e2e8f0;
        position: relative;
        background: white;
        transition: all 0.2s ease;
      }
      .reviews-list li:last-child {
        border-bottom: none;
      }
      .reviews-list li:hover {
        background: #f8fafc;
        transform: translateX(5px);
      }
      .reviews-list li::before {
        content: '★';
        position: absolute;
        left: 20px;
        top: 20px;
        color: #fbbf24;
        font-size: 1.2rem;
      }
      .reviews-list li {
        padding-left: 50px;
      }
      .review-author {
        font-weight: 600;
        color: #4c1d95;
        margin-bottom: 8px;
      }
      .review-text {
        color: #64748b;
        line-height: 1.6;
      }
      .footer {
        background: #1e293b;
        color: #e2e8f0;
        text-align: center;
        padding: 40px;
        margin-top: 40px;
      }
      .footer-content {
        max-width: 600px;
        margin: 0 auto;
      }
      .footer-logo {
        display: flex;
        align-items: center;
        justify-content: center;
        margin-bottom: 20px;
        gap: 12px;
      }
      .footer h3 {
        margin: 0;
        font-size: 1.2rem;
        color: white;
      }
      .footer p {
        margin: 10px 0;
        opacity: 0.8;
        line-height: 1.6;
      }
      .footer-copyright {
        margin-top: 30px;
        padding-top: 20px;
        border-top: 1px solid #334155;
        font-size: 0.9rem;
        opacity: 0.7;
      }
      @media (max-width: 768px) {
        .container { padding: 10px; }
        .report-header { padding: 30px 20px; }
        .content { padding: 25px 20px; }
        h1 { font-size: 2rem; }
        .practice-name { font-size: 1.4rem; }
        .header-info-row { grid-template-columns: 1fr; }
        .scores-grid { grid-template-columns: repeat(2, 1fr); }
      }
    </style>
    """

    title = final.get("practice_name") or "Face Value Audit"
    addr  = final.get("address") or "—"
    maps  = final.get("maps_link")
    addr_html = f'<a href="{escape(maps)}" target="_blank" rel="noopener">{escape(addr)}</a>' if (maps and final.get("address")) else escape(addr)

    header = f"""
      <div class="report-header">
        <h1>Face Value Audit Report</h1>
        <div class="practice-name">{escape(title)}</div>
        <div class="header-info">
          <div class="header-info-row">
            <div class="info-item">
              <div class="info-label">Doctor</div>
              <div class="info-value">{escape(final.get('doctor_name','—'))}</div>
            </div>
            <div class="info-item">
              <div class="info-label">Website</div>
              <div class="info-value">{escape(final.get('website','—'))}</div>
            </div>
            <div class="info-item">
              <div class="info-label">Email</div>
              <div class="info-value">{escape(final.get('email','—'))}</div>
            </div>
          </div>
          <div class="header-info-row">
            <div class="info-item">
              <div class="info-label">Phone</div>
              <div class="info-value">{escape(final.get('phone','—'))}</div>
            </div>
            <div class="info-item">
              <div class="info-label">Address</div>
              <div class="info-value">{addr_html}</div>
            </div>
          </div>
        </div>
        <div class="scores-container">
          <div class="scores-grid">
            <div class="score-card">
              <div class="score-value">{scores['overall']}/100</div>
              <div class="score-label">Overall Score</div>
            </div>
            <div class="score-card">
              <div class="score-value">{scores['visibility']}/30</div>
              <div class="score-label">Visibility</div>
            </div>
            <div class="score-card">
              <div class="score-value">{scores['reputation']}/40</div>
              <div class="score-label">Reputation</div>
            </div>
            <div class="score-card">
              <div class="score-value">{scores['experience']}/30</div>
              <div class="score-label">Experience</div>
            </div>
          </div>
        </div>
      </div>
    """


    # Encode logo for use in report footer
    with open("assets/logo-big.png", "rb") as report_logo_file:
        report_logo_base64 = base64.b64encode(report_logo_file.read()).decode()

    footer = f"""
    <div class="footer">
        <div class="footer-content">
            <div class="footer-logo">
                <img src="data:image/png;base64,{report_logo_base64}" width="40">
                <h3>Powered by NeedleTail AI</h3>
            </div>
            <p>Experience the future of healthcare eligibility verification with AI agents that work 24/7 to automate insurance verification processes.</p>
            <div class="footer-copyright">© 2025 Needle Tail. All rights reserved.</div>
        </div>
    </div>
    """

    reviews_section = ""
    if reviews:
        reviews_html = "".join(
            f"""<li>
                <div class="review-author">{escape(r.get('author_name', 'Anonymous'))}</div>
                <div class="review-text">{escape((r.get('text') or '')[:400])}</div>
            </li>"""
            for r in reviews[:10]
        )
        reviews_section = f"""
        <section>
            <h2>Recent Google Reviews</h2>
            <div class="reviews-list">
                <ul>{reviews_html}</ul>
            </div>
        </section>
        """

    html = f"""<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
    <title>Face Value Audit Report – {escape(title)}</title>{style}</head><body>
    <div class="container">
        <div class="report-card">
            {header}
            <div class="content">
                {_kv_table("Practice Overview", overview)}
                {_kv_table("Online Visibility", visibility)}
                {_kv_table("Reputation & Feedback", reputation)}
                {reviews_section}
                {_kv_table("Marketing Signals", marketing)}
                {_kv_table("Patient Experience", experience)}
            </div>
        </div>
    </div>
    {footer}
    </body></html>"""
    return html


# ------------------------ UI form ------------------------

# ------------------------ UI: inputs + auto-fill ------------------------




# ---- Modern Mobile-Friendly Form Layout ----
st.markdown("""
<div style="text-align: center; margin-bottom: 2rem;">
    <h2 style="color: white; font-size: 1.8rem; margin: 0;">🦷 Practice Details</h2>
    <p style="color: rgba(255,255,255,0.8); font-size: 0.9rem; margin-top: 0.5rem;">Enter your practice information to get started</p>
</div>
""", unsafe_allow_html=True)

# Create columns for better mobile layout
col1, col2 = st.columns([1, 1])

with col1:
    # 1. Website URL
    website = st.text_input(
        "🌐 Website URL *",
        key="website_input",
        value=st.session_state.draft.get("website", ""),
        placeholder="https://yourpractice.com",
        help="Enter your practice website URL"
    )

    # 2. Practice's Name
    practice_name_value = st.session_state.draft.get("practice_name", "")
    name_message = st.session_state.draft.get("name_message", "")

    practice_name = st.text_input(
        "🏢 Practice Name *",
        value=practice_name_value,
        key="practice_name_input",
        placeholder="Smile Dental Care",
        help="Your practice or clinic name"
    )


    # 3. Contact Person/ Doctor Name
    doctor_name = st.text_input(
        "👨‍⚕️ Doctor/Contact Name *",
        key="doctor_name_input",
        value=st.session_state.draft.get("doctor_name", ""),
        placeholder="Dr. John Smith",
        help="Primary contact or lead doctor"
    )

with col2:
    # 4. Email ID (with prefill messages)
    email_value = st.session_state.draft.get("email", "")
    email_message = st.session_state.draft.get("email_message", "")

    email = st.text_input(
        "📧 Email Address *",
        value=email_value,
        key="email_input",
        placeholder="contact@yourpractice.com",
        help="Primary contact email"
    )


    # 5. Phone Number (with prefill messages)
    phone_value = st.session_state.draft.get("phone", "")
    phone_message = st.session_state.draft.get("phone_message", "")

    phone = st.text_input(
        "📞 Phone Number *",
        value=phone_value,
        key="phone_input",
        placeholder="+1 (555) 123-4567",
        help="Primary contact phone number"
    )


# Auto-prefill functionality when website URL changes
if website and website != st.session_state.get("last_prefill_website", ""):
    normalized_website = _normalize_url(website)
    if normalized_website and normalized_website != st.session_state.get("last_prefill_website", ""):
        st.session_state.last_prefill_website = normalized_website

        # Create a top-positioned spinner container
        spinner_container = st.empty()
        with spinner_container:
            st.markdown("""
            <div style="position: fixed; top: 20px; left: 50%; transform: translateX(-50%);
                        z-index: 9999; background: rgba(255, 255, 255, 0.95);
                        padding: 1rem 2rem; border-radius: 25px;
                        box-shadow: 0 4px 20px rgba(0, 0, 0, 0.3);
                        border: 1px solid rgba(102, 126, 234, 0.3);">
                <div style="display: flex; align-items: center; gap: 10px;">
                    <div style="width: 20px; height: 20px; border: 3px solid #667eea;
                               border-top: 3px solid transparent; border-radius: 50%;
                               animation: spin 1s linear infinite;"></div>
                    <span style="color: #333; font-weight: 600;">🔍 Analyzing website...</span>
                </div>
            </div>
            <style>
                @keyframes spin { 0% { transform: rotate(0deg); } 100% { transform: rotate(360deg); } }
            </style>
            """, unsafe_allow_html=True)

        prefill_from_website(normalized_website)
        st.session_state.last_fetched_website = normalized_website
        spinner_container.empty()
        st.rerun()

# Address field spans both columns
st.markdown("---")
address_value = st.session_state.draft.get("address", "")
address_message = st.session_state.draft.get("address_message", "")

address = st.text_area(
    "🏠 Full Practice Address *",
    value=address_value,
    height=60,
    key="address_input",
    placeholder="123 Main Street, City, State, ZIP Code",
    help="Complete address including street, city, state, and ZIP code"
)


# Show helpful tip for blocked websites
if (st.session_state.get("last_fetch_error") == "blocked" and
    not practice_name_value and not address_value):
    st.info("💡 **Tip**: Some websites block automated access for security. Please manually enter the practice name and address from the website.")

# Persist user entries into draft continuously
st.session_state.draft.update({
    "website": website,
    "doctor_name": doctor_name,
    "email": email,
    "phone": phone,
    "practice_name": practice_name,
    "address": address
})

# Validation
url_ok = bool(_normalize_url(website))
email_ok = _valid_email(email)
phone_ok = _valid_phone(phone)
doctor_ok = bool(doctor_name.strip())
practice_ok = bool(practice_name.strip())
address_ok = bool(address.strip())

ready = url_ok and email_ok and phone_ok and doctor_ok and practice_ok and address_ok

# Show validation messages
col1, col2 = st.columns(2)
with col1:
    if website and not url_ok:
        st.caption("⚠️ Please include a valid URL (we'll add https:// if missing).")
    if email and not email_ok:
        st.caption("⚠️ That email doesn't look valid.")
    if phone and not phone_ok:
        st.caption("⚠️ Please include a valid phone number (at least 7 digits).")

with col2:
    if doctor_name and not doctor_ok:
        st.caption("⚠️ Doctor name is required.")
    if practice_name and not practice_ok:
        st.caption("⚠️ Practice name is required.")
    if address and not address_ok:
        st.caption("⚠️ Full address is required.")

# Add note about extracted data
st.markdown("---")
st.info("ℹ️ **Note**: Some details may have been extracted from the website. Please recheck/edit before submitting.")

# Form with only the submit button
with st.form("practice_details_form", clear_on_submit=False):
    # Submit button
    confirmed = st.form_submit_button("✅ Run Audit", use_container_width=True, disabled=not ready)

    if confirmed:
        maps_link = st.session_state.draft.get("maps_link", "")
        normalized_website = _normalize_url(website)
        st.session_state.final = {
            "website": normalized_website,
            "doctor_name": doctor_name,
            "email": email,
            "phone": phone,
            "practice_name": practice_name,
            "address": address,
            "maps_link": maps_link,
        }

        # 👉 append to Google Sheet BEFORE audit begins
        saved = append_submission_to_sheet(st.session_state.final)
        if saved:
            st.toast("Saved to Google Sheet ✅")

        # now proceed with your existing flow
        st.session_state.submitted = True
        st.rerun()  # safe on modern Streamlit; or call your _safe_rerun()


# Add custom Needle Tail footer
st.markdown("---")
st.markdown("""
<div style="text-align: center; padding: 2rem 0; background: linear-gradient(90deg, #f8f9fa 0%, #ffffff 50%, #f8f9fa 100%); border-radius: 10px; margin-top: 3rem;">
    <h4 style="margin: 0 0 1rem 0; color: #333; font-weight: 600;">Powered by Needle Tail</h4>
    <p style="color: #666; margin: 0; font-size: 0.9rem;">Experience the future of healthcare eligibility verification with AI agents that work 24/7 to automate insurance verification processes.</p>
    <p style="color: #999; margin: 0.5rem 0 0 0; font-size: 0.8rem;">© 2025 Needle Tail. All rights reserved.</p>
</div>
""", unsafe_allow_html=True)



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
            # Handle new format - count platforms from HTML or platform count
            platform_count = 0
            if "<a href=" in s:  # Has hyperlinks (new format)
                platform_count = s.count("<a href=")
            elif "," in s:  # Comma-separated list
                platform_count = len([p.strip() for p in s.split(",") if p.strip() and p.strip().lower() != "none"])
            elif s.lower() not in ("none", "", "—"):
                platform_count = 1

            if platform_count >= 4: return ("All 4", "badge-ok")
            elif platform_count == 3: return ("3 of 4", "badge-warn")
            elif platform_count == 2: return ("2 of 4", "badge-warn")
            elif platform_count == 1: return ("1 of 4", "badge-bad")
            else: return ("None", "badge-bad")
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
        "Office Hours (as mentioned in Website)",
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

        if label == "Appointment Booking" or label == "Appointment Channels" or label == "Appointment Options Available":
            if any(w in sl for w in ["phone + advanced", "excellent", "online", "book", "booking", "zocdoc", "practo", "calendly"]):
                return ("Available", "badge-ok")
            if any(w in sl for w in ["phone-only", "phone + online form"]):
                return ("Basic", "badge-warn")
            if any(w in sl for w in ["no", "none", "unavailable"]):
                return ("Missing", "badge-bad")
            return ("Check", "badge-warn")

        if label == "Office Hours" or label == "Office Hours (as mentioned in Website)":
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

        if label == "AI Insights":
            if s and s not in ("", "—") and "no insights" not in sl:
                return ("Available", "badge-ok")
            return ("Unavailable", "badge-muted")

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

    # Clear the page and show top-positioned progress indicator
    st.empty()

    # Create top-positioned spinner
    progress_container = st.empty()
    with progress_container:
        st.markdown("""
        <div style="position: fixed; top: 20px; left: 50%; transform: translateX(-50%);
                    z-index: 9999; background: rgba(255, 255, 255, 0.95);
                    padding: 1.5rem 3rem; border-radius: 30px;
                    box-shadow: 0 8px 32px rgba(31, 38, 135, 0.37);
                    backdrop-filter: blur(8px);
                    border: 1px solid rgba(255, 255, 255, 0.18);">
            <div style="display: flex; align-items: center; gap: 15px;">
                <div style="width: 30px; height: 30px; border: 4px solid #667eea;
                           border-top: 4px solid transparent; border-radius: 50%;
                           animation: spin 1s linear infinite;"></div>
                <div>
                    <div style="color: #333; font-weight: 700; font-size: 16px;">🔍 Analyzing Practice</div>
                    <div style="color: #666; font-size: 12px; margin-top: 2px;">Generating comprehensive audit report...</div>
                </div>
            </div>
        </div>
        <style>
            @keyframes spin { 0% { transform: rotate(0deg); } 100% { transform: rotate(360deg); } }
        </style>
        """, unsafe_allow_html=True)

    # Initialize variables with fallback values
    soup = None
    load_time = 0
    place_id = None
    details = None
    comprehensive_analysis = None
    final = st.session_state.final

    # Start timer for timeout protection
    audit_start_time = time.time()
    AUDIT_TIMEOUT = 60  # 60 seconds maximum

    try:
        # Step 1: Fetch website HTML with timeout
        with st.spinner("Fetching website..."):
            soup, load_time = fetch_html(website)

        # Step 2: Get Google Places data with timeout
        if time.time() - audit_start_time < AUDIT_TIMEOUT:
            with st.spinner("Analyzing location..."):
                place_id = find_best_place_id(clinic_name, address, website)
                details = places_details(place_id) if place_id else None

        # Step 3: Run LLM analysis with timeout
        if time.time() - audit_start_time < AUDIT_TIMEOUT and HAS_CLAUDE and CLAUDE_API_KEY and soup:
            with st.spinner("Running AI analysis..."):
                try:
                    comprehensive_analysis = stream_llm_analysis_with_progress(soup, website, clinic_name, [])
                except Exception as e:
                    st.warning(f"AI analysis failed: {str(e)[:100]}. Continuing with basic analysis...")
        elif time.time() - audit_start_time >= AUDIT_TIMEOUT:
            st.warning("⚠️ Analysis timeout reached. Generating report with available data...")

    except Exception as e:
        st.error(f"Error during analysis: {str(e)[:100]}. Generating report with available data...")
        # Continue with fallback values

    try:
        # 1) Overview
        overview = {
            "Practice Name": clinic_name or "Search limited",
            "Address": address or "Search limited",
            "Phone": phone or "Search limited",
            "Website": website or "Search limited",
        }

        # 2) Visibility
        wh_str, wh_checks = website_health(website, soup, load_time)
        social_data = social_presence_from_site(soup)

        # Enhance social data with LLM insights
        if comprehensive_analysis and comprehensive_analysis.get("social_media"):
            social_llm = comprehensive_analysis["social_media"]
            if social_llm.get("links"):
                # Merge LLM-detected links with existing data
                if isinstance(social_data, dict):
                    social_data["links"] = {**social_data.get("links", {}), **social_llm["links"]}
                    social_data["platforms"] = list(set((social_data.get("platforms", []) + social_llm.get("platforms", []))))

        appears = appears_on_page1_for_dentist_near_me(website, clinic_name, address)

        # Format social media display with hyperlinks
        if isinstance(social_data, dict):
            if social_data.get("links") or social_data.get("platforms"):
                social_display = format_social_media_with_links(social_data)
            else:
                social_display = social_data.get("summary", "None")
        else:
            social_display = str(social_data)

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

        # Get AI insights for online visibility
        visibility_ai_insights = ""
        if comprehensive_analysis and comprehensive_analysis.get("social_media", {}).get("visibility_insights"):
            insights = comprehensive_analysis["social_media"]["visibility_insights"]
            # Format as bullet points for dataframe display
            if isinstance(insights, str):
                    # Clean up the insights string and ensure proper bullet point formatting
                    insights = insights.strip()

                    # If insights already contain bullet points, use them directly
                    if "•" in insights and "\\n" in insights:
                        # Replace escaped newlines with actual newlines
                        visibility_ai_insights = insights.replace("\\n", "\n")
                    elif "•" in insights:
                        # Split by bullet points and rejoin with newlines
                        bullet_parts = insights.split("•")
                        bullet_points = []
                        for part in bullet_parts:
                            part = part.strip()
                            if part and len(part) > 5:
                                bullet_points.append(f"• {part}")
                        visibility_ai_insights = "\n".join(bullet_points[:3])
                    else:
                        # Split by common delimiters and format as bullets
                        bullet_points = []
                        if "-" in insights:
                            lines = insights.split("-")
                        elif "." in insights:
                            lines = insights.split(".")
                        else:
                            lines = [insights]

                        for line in lines:
                            line = line.strip()
                            if line and len(line) > 5:  # Skip very short fragments
                                bullet_points.append(f"• {line}")

                        visibility_ai_insights = "\n".join(bullet_points[:3])  # Limit to 3 points

                    # Fallback to default insights if nothing was extracted
                    if not visibility_ai_insights.strip():
                        visibility_ai_insights = "• Optimize Google My Business profile\n• Build local SEO citations\n• Create regular social media content"

        visibility = {
            "GBP Completeness (estimate)": gbp_score,
            "GBP Signals": gbp_signals,
            "Search Visibility (Page 1?)": appears,
            "Website Health Score": wh_str,
            "Website Health Checks": wh_checks,
            "Social Media Presence": social_display,
            "AI Insights": visibility_ai_insights if visibility_ai_insights else "• Optimize Google My Business profile\n• Build local SEO citations\n• Create regular social media content"
        }

        # 3) Reputation
        rating_str, review_count_out, reviews = rating_and_reviews(details)
        # Use ONLY LLM for ALL reputation data extraction
        if HAS_CLAUDE and CLAUDE_API_KEY and reviews:
            sentiment_summary, top_pos_str, top_neg_str = analyze_review_texts(reviews)

            # Use LLM to extract rating information
            llm_ratings = extract_ratings_with_llm(reviews, details)
            all_time_rating = llm_ratings.get("all_time_avg", "Search limited")
            recent_rating = llm_ratings.get("recent_avg", "Search limited")
            review_count_llm = llm_ratings.get("total_count", "Search limited")

            # Get additional LLM insights from comprehensive analysis
            key_insights = ""
            if comprehensive_analysis and comprehensive_analysis.get("reputation"):
                reputation_data = comprehensive_analysis["reputation"]
                key_insights = reputation_data.get("advice", "") or reputation_data.get("sentiment", "")
        else:
            # If LLM not available, all fields show search limited
            sentiment_summary, top_pos_str, top_neg_str = "Search limited", "Search limited", "Search limited"
            all_time_rating = recent_rating = review_count_llm = "Search limited"
            key_insights = "Search limited"

        reputation = {
            "Google Reviews (All-time Avg)": all_time_rating,
            "Google Reviews (Recent 10 Avg)": recent_rating,
            "Total Google Reviews": review_count_llm,
            "Sentiment Highlights": sentiment_summary,
            "Top Positive Themes": top_pos_str,
            "Top Negative Themes": top_neg_str,
        }

        # Add key insights if available
        if key_insights:
            reputation["AI Insights"] = key_insights

        # 4) Marketing - Enhanced comprehensive analysis
        # Get comprehensive LLM marketing analysis from cached result
        marketing_insights = ""
        if comprehensive_analysis and comprehensive_analysis.get("marketing"):
            marketing_data = comprehensive_analysis["marketing"]
            marketing_insights = marketing_data.get("key_recommendations", "") or marketing_data.get("advertising_advice", "")

        # Enhanced marketing analysis
        photos_on_website = media_count_from_site(soup) if soup else "Search limited"
        photos_in_google = photos_count_from_places(details) if details else "Search limited"
        advertising_tools = advertising_signals(soup) if soup else "Search limited"

        # New comprehensive marketing metrics
        conversion_analysis = analyze_website_conversion_elements(soup) if soup else "Search limited"
        content_strategy = analyze_content_marketing(soup, website) if soup else "Search limited"
        local_seo_status = analyze_local_seo_signals(soup, final.get('address', '')) if soup else "Search limited"

        # Generate AI-powered marketing insights
        ai_insights = generate_marketing_insights(
            soup,
            website,
            final.get('practice_name', ''),
            social_data,
            photos_in_google if isinstance(photos_in_google, int) else 0,
            advertising_tools
        ) if soup else "Enable Claude AI for detailed marketing insights"

        marketing = {
            "Website Content Strategy": content_strategy,
            "Conversion Optimization": conversion_analysis,
            "Local SEO Signals": local_seo_status,
            "Photos/Videos on Website": photos_on_website,
            "Google My Business Photos": photos_in_google,
            "Marketing & Analytics Tools": advertising_tools,
            "AI Marketing Strategy Insights": ai_insights
        }

        # Add legacy LLM insights if available (fallback)
        if marketing_insights and not ai_insights.startswith("Enable Claude"):
            marketing["Additional Insights"] = marketing_insights

        # 5) Experience - Enhanced with LLM analysis
        appointment_channels = appointment_channels_from_site(soup, website)
        hours = office_hours_from_places(details)
        insurance_info = enhanced_insurance_from_site(soup, website)

        # Generate AI insights for patient experience
        patient_insights = generate_patient_experience_insights(appointment_channels, insurance_info, hours)

        experience = {
            "Appointment Options Available": appointment_channels,
            "Office Hours (as mentioned in Website)": hours,
            "Insurance Acceptance": insurance_info,
            "AI Insights": patient_insights,
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
        insurance_clear = isinstance(insurance_info, str) and insurance_info not in ["Search limited", "Unclear"]

        smile, vis_score, rep_score, exp_score = compute_smile_score(
            wh_pct, social_data, rating_val, reviews_total, appointment_channels, hours_present, insurance_clear, accessibility_present=False
        )

        # Build scores dictionary for report
        scores = {
            "overall": smile,
            "visibility": vis_score,
            "reputation": rep_score,
            "experience": exp_score,
        }

        # Generate the static HTML report
        report_html = build_static_report_html(
            final, overview, visibility, reputation, marketing, experience, scores, reviews
        )

        # Set a flag to indicate report is ready
        st.session_state.report_ready = True
        st.session_state.report_html = report_html

        # Trigger a rerun to display the report at the top
        st.rerun()

    except Exception as e:
        st.error(f"Report generation failed: {str(e)[:100]}")
    finally:
        # Always clear the progress indicator
        try:
            progress_container.empty()
        except:
            pass



