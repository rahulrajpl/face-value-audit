import requests
from bs4 import BeautifulSoup

# Test script to demonstrate the updated address validation functionality
PLACES_API_KEY = "AIzaSyAWsdRuSFofp4_x-yXYvjDG1X2DNcWYFhw"

def validate_address_with_geocoding(address: str) -> tuple[bool, str]:
    """
    Validate an address using Google Geocoding API reverse search
    Returns (is_valid, validated_address)
    """
    if not address or not PLACES_API_KEY:
        return False, address

    try:
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
            result = data["results"][0]
            validated_address = result.get("formatted_address", address)
            return True, validated_address
        else:
            return False, address

    except Exception as e:
        print(f"Exception occurred: {str(e)}")
        return False, address

def test_updated_address_validation():
    """Test the updated address validation logic that only returns valid addresses"""
    print("=" * 70)
    print("TESTING UPDATED ADDRESS VALIDATION LOGIC")
    print("During prefill, addresses are now validated with Google Maps")
    print("Only validated addresses are returned - invalid ones are left empty")
    print("=" * 70)

    test_addresses = [
        "123 Main Street, New York, NY 10001",  # Valid address
        "invalid fake street xyz 99999",        # Invalid address
        "1600 Amphitheatre Parkway, Mountain View, CA",  # Valid Google HQ
        "random text not an address at all"     # Invalid
    ]

    for i, test_addr in enumerate(test_addresses, 1):
        print(f"\n--- Test {i}: {test_addr[:40]}{'...' if len(test_addr) > 40 else ''} ---")

        is_valid, validated = validate_address_with_geocoding(test_addr)

        if is_valid:
            print(f"[VALID] Address will be prefilled:")
            print(f"   Original: {test_addr}")
            print(f"   Validated: {validated}")
            prefill_result = validated  # This would be set in the form
        else:
            print(f"[INVALID] Address field will be left EMPTY")
            print(f"   User must manually enter address")
            prefill_result = ""  # Address field stays empty

        print(f"   Prefill Result: '{prefill_result}'")
        print("-" * 50)

    print("\n" + "=" * 70)
    print("SUMMARY:")
    print("- Valid addresses: Prefilled with Google Maps validated format")
    print("- Invalid addresses: Field left empty for manual entry")
    print("- Users can always verify and edit any prefilled address")
    print("=" * 70)

if __name__ == "__main__":
    test_updated_address_validation()