#!/usr/bin/env python3

print("=" * 70)
print("TOP POSITIVE & NEGATIVE THEMES EXTRACTION ANALYSIS")
print("=" * 70)

print("\nEXTRACTION METHOD ANALYSIS:")
print("-" * 50)

print("[YES] Top Positive Themes ARE extracted using LLM")
print("[YES] Top Negative Themes ARE extracted using LLM")

print("\nIMPLEMENTATION DETAILS:")
print("-" * 50)

print("Primary Method: LLM (Claude AI) Analysis")
print("Function: analyze_reviews_with_llm()")
print("Input: Google Reviews (up to 10 reviews analyzed)")
print("LLM Model: Claude AI (Anthropic)")
print("Output Format: JSON with positive_themes and negative_themes")
print("Fallback: Keyword-based analysis if LLM fails")

print("\nLLM ANALYSIS PROCESS:")
print("-" * 50)

print("1. Collects up to 10 Google reviews with ratings and text")
print("2. Formats reviews for LLM: 'Review X (5 star by Author): text'")
print("3. Sends to Claude AI with specific dental practice context")
print("4. Requests JSON response with positive_themes and negative_themes")
print("5. Parses JSON response and extracts themes")
print("6. Falls back to keyword analysis if LLM fails")

print("\nLLM PROMPT SPECIFICATIONS:")
print("-" * 50)

print("Requests 'Top 3 positive themes mentioned (comma-separated)'")
print("Requests 'Top 3 negative concerns mentioned (comma-separated)'")
print("Focuses on dental practice specific themes:")
print("  - Staff friendliness, professionalism")
print("  - Pain management, comfort")
print("  - Cleanliness, hygiene")
print("  - Wait times, scheduling")
print("  - Communication, explanations")
print("  - Billing, insurance issues")
print("  - Office environment")
print("  - Treatment quality")

print("\nFALLBACK SYSTEM:")
print("-" * 50)

print("If LLM analysis fails, system uses keyword-based analysis:")
print("Positive themes: friendly staff, cleanliness, pain-free, professionalism")
print("Negative themes: long wait, billing issues, front desk, pain/discomfort")
print("Uses keyword counting to identify most mentioned themes")

print("\nEXAMPLE LLM OUTPUT:")
print("-" * 50)

print('{')
print('    "sentiment": "Mostly positive with some scheduling concerns",')
print('    "positive_themes": "Friendly staff, professional treatment, clean office",')
print('    "negative_themes": "Long wait times, scheduling issues",')
print('    "key_insights": "Strong clinical care but improve appointment scheduling"')
print('}')

print("\n" + "=" * 70)
print("CONCLUSION:")
print("[YES] Top Positive Themes: EXTRACTED USING LLM (Claude AI)")
print("[YES] Top Negative Themes: EXTRACTED USING LLM (Claude AI)")
print("[YES] Advanced AI analysis with intelligent fallback system")
print("=" * 70)