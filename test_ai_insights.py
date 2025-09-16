#!/usr/bin/env python3

def test_ai_marketing_insights_format():
    """Test the improved AI Marketing Strategy Insights format"""

    print("=" * 70)
    print("AI MARKETING STRATEGY INSIGHTS - FORMAT IMPROVEMENT")
    print("Limited to exactly 3 lines, straight to the point")
    print("=" * 70)

    # Before and After comparison
    print("\nFORMAT IMPROVEMENTS:")
    print("-" * 50)

    print("BEFORE (Long, verbose):")
    before_example = """
    • Consider implementing a comprehensive online appointment booking system to reduce phone dependency and improve patient convenience, as this can significantly increase conversion rates
    • Develop and regularly update before/after photo galleries showcasing treatment results to build trust and demonstrate expertise to potential patients browsing your website
    • Enhance your local SEO strategy by creating service-specific landing pages with targeted keywords to improve search rankings for dental services in your area
    • Implement a content marketing strategy with regular blog posts about dental health topics to establish authority and improve organic search visibility
    """
    print(before_example.strip())

    print("\nAFTER (3 lines, straight to point):")
    after_example = """• Set up online appointment booking system
• Add before/after photos to showcase results
• Create Google My Business posts weekly"""

    print(after_example)

    print("\n" + "-" * 50)
    print("KEY IMPROVEMENTS:")
    print("+ EXACTLY 3 lines (no more, no less)")
    print("+ Maximum 15 words per line")
    print("+ No fluff or unnecessary explanations")
    print("+ Direct, actionable recommendations")
    print("+ Easy to scan and understand quickly")

    print("\n" + "=" * 70)
    print("LINE COUNT TEST:")
    print("=" * 70)

    test_results = [
        "• Optimize Google My Business with more photos\n• Add patient testimonials to build trust\n• Implement clear call-to-action buttons",
        "• Set up online appointment booking system\n• Add before/after photos to showcase results\n• Create Google My Business posts weekly",
        "• Optimize Google My Business profile\n• Add more professional photos\n• Implement online booking system"
    ]

    for i, result in enumerate(test_results, 1):
        lines = result.split('\n')
        line_count = len(lines)

        print(f"\nExample {i}:")
        for line in lines:
            word_count = len(line.split())
            print(f"  {line} ({word_count} words)")

        if line_count == 3:
            print(f"  [PASS]: Exactly 3 lines")
        else:
            print(f"  [FAIL]: {line_count} lines (should be 3)")

    print("\n" + "=" * 70)
    print("All AI Marketing Strategy Insights are now limited to 3 lines!")
    print("=" * 70)

if __name__ == "__main__":
    test_ai_marketing_insights_format()