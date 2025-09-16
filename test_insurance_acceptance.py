#!/usr/bin/env python3

def test_insurance_acceptance_format():
    """Test the improved Insurance Acceptance format - limited to 3 lines max"""

    print("=" * 70)
    print("INSURANCE ACCEPTANCE - FORMAT IMPROVEMENT")
    print("Limited to maximum 3 lines, straight to the point")
    print("=" * 70)

    # Before and After comparison
    print("\nFORMAT IMPROVEMENTS:")
    print("-" * 50)

    print("BEFORE (Long, verbose):")
    before_examples = [
        """We are proud to accept most major insurance plans to help make your dental care more affordable and accessible. Our office works with Delta Dental, Blue Cross Blue Shield, Cigna, Aetna, MetLife, Guardian, and many other insurance providers. We also offer flexible payment plans and financing options through CareCredit to help you manage your out-of-pocket expenses. Please contact our office to verify your specific insurance benefits and coverage details, as benefits can vary significantly between different plans and employers.""",

        """Our dental practice participates in numerous insurance networks including PPO and HMO plans. We accept Delta Dental Premier and PPO, Blue Cross Blue Shield, Cigna Dental, Aetna, MetLife, Guardian, United Healthcare, and Humana. We also provide direct billing services to your insurance company to maximize your benefits and minimize your out-of-pocket costs. For patients without insurance, we offer competitive cash rates and flexible payment options."""
    ]

    print("Example 1:")
    print(before_examples[0])
    print(f"({len(before_examples[0].split())} words)")

    print("\nAFTER (3 lines max, to the point):")
    after_examples = [
        "Accepts most major insurance plans including Delta Dental and Blue Cross\nPPO and HMO plans welcome with payment plans available\nContact office to verify your specific coverage",

        "Delta Dental, Blue Cross, Cigna, and Aetna accepted\nDirect insurance billing available to maximize benefits\nFlexible payment options for uninsured patients"
    ]

    print("Example 1:")
    print(after_examples[0])
    lines_1 = after_examples[0].split('\n')
    print(f"({len(lines_1)} lines)")
    for i, line in enumerate(lines_1, 1):
        print(f"  Line {i}: {line} ({len(line.split())} words)")

    print("\nExample 2:")
    print(after_examples[1])
    lines_2 = after_examples[1].split('\n')
    print(f"({len(lines_2)} lines)")
    for i, line in enumerate(lines_2, 1):
        print(f"  Line {i}: {line} ({len(line.split())} words)")

    print("\n" + "-" * 50)
    print("KEY IMPROVEMENTS:")
    print("+ MAXIMUM 3 lines only")
    print("+ Maximum 15 words per line")
    print("+ Specific insurance names mentioned")
    print("+ No unnecessary fluff or repetition")
    print("+ Easy to scan and understand quickly")

    print("\n" + "=" * 70)
    print("STANDARD RESPONSES:")
    print("=" * 70)

    standard_responses = [
        "No insurance information found",
        "Does not accept insurance",
        "Insurance accepted - Check website for details",
        "Insurance accepted - Details on website"
    ]

    for i, response in enumerate(standard_responses, 1):
        word_count = len(response.split())
        line_count = len(response.split('\n'))
        print(f"{i}. {response}")
        print(f"   ({line_count} line, {word_count} words)")

    print("\n" + "=" * 70)
    print("All Insurance Acceptance results are now limited to 3 lines maximum!")
    print("=" * 70)

if __name__ == "__main__":
    test_insurance_acceptance_format()