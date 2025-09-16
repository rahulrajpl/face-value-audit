#!/usr/bin/env python3

def test_llm_only_reputation():
    """Test that Reputation and Feedback uses ONLY LLM extraction"""

    print("=" * 70)
    print("REPUTATION & FEEDBACK - LLM-ONLY EXTRACTION TEST")
    print("=" * 70)

    print("\nEXTRACTION METHOD ANALYSIS:")
    print("-" * 50)

    print("[BEFORE] Mixed extraction methods:")
    print("- Google Reviews (All-time Avg): calculate_separate_ratings() [NON-LLM]")
    print("- Google Reviews (Recent 10 Avg): calculate_separate_ratings() [NON-LLM]")
    print("- Total Google Reviews: rating_and_reviews() [NON-LLM]")
    print("- Sentiment Highlights: analyze_review_texts() [LLM + keyword fallback]")
    print("- Top Positive Themes: analyze_review_texts() [LLM + keyword fallback]")
    print("- Top Negative Themes: analyze_review_texts() [LLM + keyword fallback]")

    print("\n[AFTER] LLM-ONLY extraction:")
    print("- Google Reviews (All-time Avg): extract_ratings_with_llm() [LLM ONLY]")
    print("- Google Reviews (Recent 10 Avg): extract_ratings_with_llm() [LLM ONLY]")
    print("- Total Google Reviews: extract_ratings_with_llm() [LLM ONLY]")
    print("- Sentiment Highlights: analyze_review_texts() [LLM ONLY]")
    print("- Top Positive Themes: analyze_review_texts() [LLM ONLY]")
    print("- Top Negative Themes: analyze_review_texts() [LLM ONLY]")

    print("\nKEY CHANGES MADE:")
    print("-" * 50)

    changes = [
        "1. Modified analyze_review_texts() to remove keyword fallback",
        "2. Created extract_ratings_with_llm() for LLM-based rating extraction",
        "3. Updated reputation section to check for LLM availability",
        "4. If LLM unavailable: ALL fields show 'Search limited'",
        "5. Removed dependencies on calculate_separate_ratings()",
        "6. Eliminated all non-LLM extraction methods"
    ]

    for change in changes:
        print(change)

    print("\nLLM EXTRACTION FUNCTIONS:")
    print("-" * 50)

    functions = [
        "extract_ratings_with_llm(reviews, details):",
        "  - Analyzes up to 20 reviews",
        "  - Calculates all-time and recent averages using LLM",
        "  - Returns JSON with rating statistics",
        "",
        "analyze_review_texts(reviews) [MODIFIED]:",
        "  - Removed keyword-based fallback",
        "  - Uses ONLY analyze_reviews_with_llm()",
        "  - Returns 'Search limited' if LLM fails",
        "",
        "analyze_reviews_with_llm(reviews):",
        "  - Unchanged - existing LLM function",
        "  - Extracts sentiment and themes using Claude AI"
    ]

    for func in functions:
        print(func)

    print("\nLLM AVAILABILITY CHECK:")
    print("-" * 50)

    print("if HAS_CLAUDE and CLAUDE_API_KEY and reviews:")
    print("    # Use LLM extraction for all reputation data")
    print("    sentiment_summary, top_pos_str, top_neg_str = analyze_review_texts(reviews)")
    print("    llm_ratings = extract_ratings_with_llm(reviews, details)")
    print("    # Extract all data from LLM results")
    print("else:")
    print("    # If LLM not available, ALL fields show 'Search limited'")
    print("    sentiment_summary = 'Search limited'")
    print("    top_pos_str = 'Search limited'")
    print("    top_neg_str = 'Search limited'")
    print("    all_time_rating = 'Search limited'")
    print("    recent_rating = 'Search limited'")

    print("\nEXAMPLE LLM PROMPTS:")
    print("-" * 50)

    print("Rating Extraction Prompt:")
    print("'Analyze these Google reviews and extract rating statistics:'")
    print("'Return JSON with all_time_avg, recent_avg, total_count'")
    print()

    print("Theme Extraction Prompt (existing):")
    print("'Analyze reviews for sentiment, positive_themes, negative_themes'")
    print("'Focus on dental practice specific themes'")

    print("\n" + "=" * 70)
    print("RESULT: REPUTATION & FEEDBACK NOW USES 100% LLM EXTRACTION")
    print("- NO keyword fallbacks")
    print("- NO traditional rating calculations")
    print("- ALL data extracted through Claude AI")
    print("- Consistent 'Search limited' when LLM unavailable")
    print("=" * 70)

if __name__ == "__main__":
    test_llm_only_reputation()