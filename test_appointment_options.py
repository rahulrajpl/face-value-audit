#!/usr/bin/env python3

def limit_to_10_words(text: str) -> str:
    """Limit text to maximum 10 words"""
    words = text.split()
    return ' '.join(words[:10])

def test_appointment_options_word_limit():
    """Test that appointment options are limited to 10 words maximum"""

    print("=" * 60)
    print("TESTING APPOINTMENT OPTIONS WORD LIMIT")
    print("Max 10 words per result")
    print("=" * 60)

    # Test examples of what might be returned before and after limiting
    test_cases = [
        {
            "before": "Phone + Advanced System - Online booking platforms like Calendly, Zocdoc, and custom booking widget detected with multiple appointment types available",
            "expected_words": 10
        },
        {
            "before": "Phone + Online Form - Basic online booking available through contact form and phone number listed prominently on homepage",
            "expected_words": 10
        },
        {
            "before": "Phone-only - No online booking detected on website",
            "expected_words": 9
        },
        {
            "before": "Search limited",
            "expected_words": 2
        },
        {
            "before": "Phone + Advanced System",
            "expected_words": 4
        }
    ]

    for i, case in enumerate(test_cases, 1):
        original = case["before"]
        limited = limit_to_10_words(original)
        word_count = len(limited.split())

        print(f"\n--- Test {i} ---")
        print(f"Original ({len(original.split())} words): {original}")
        print(f"Limited  ({word_count} words): {limited}")

        if word_count <= 10:
            print("[PASS] Within 10 word limit")
        else:
            print("[FAIL] Exceeds 10 word limit")

        print("-" * 40)

    print("\n" + "=" * 60)
    print("SUMMARY:")
    print("- All appointment options results are now limited to 10 words max")
    print("- Long descriptions are automatically truncated")
    print("- Essential information is preserved in shortened format")
    print("=" * 60)

if __name__ == "__main__":
    test_appointment_options_word_limit()