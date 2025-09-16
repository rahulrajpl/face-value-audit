import requests
import os

# Test script to validate reverse address search functionality
PLACES_API_KEY = "AIzaSyAWsdRuSFofp4_x-yXYvjDG1X2DNcWYFhw"

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
            print(f"API request failed with status code: {response.status_code}")
            return False, address

        data = response.json()
        print(f"API Response Status: {data.get('status')}")

        if data.get("status") == "OK" and data.get("results"):
            # Get the first result (most accurate)
            result = data["results"][0]
            validated_address = result.get("formatted_address", address)
            print(f"Original Address: {address}")
            print(f"Validated Address: {validated_address}")
            return True, validated_address
        else:
            print(f"Address validation failed. Status: {data.get('status')}")
            return False, address

    except Exception as e:
        print(f"Exception occurred: {str(e)}")
        return False, address

def test_addresses():
    """Test various addresses to validate the reverse address search functionality"""
    test_addresses = [
        "123 Main Street, New York, NY 10001",
        "1600 Amphitheatre Parkway, Mountain View, CA",
        "invalid address xyz 123",
        "350 Fifth Avenue, New York, NY 10118",  # Empire State Building
        "Dental Clinic, 456 Oak Street, Los Angeles, CA"
    ]

    print("=" * 60)
    print("TESTING REVERSE ADDRESS SEARCH FUNCTIONALITY")
    print("=" * 60)

    for i, address in enumerate(test_addresses, 1):
        print(f"\n--- Test {i} ---")
        is_valid, validated = validate_address_with_geocoding(address)
        print(f"Valid: {is_valid}")
        if is_valid:
            print("[SUCCESS] Address validation successful")
        else:
            print("[FAILED] Address validation failed")
        print("-" * 40)

if __name__ == "__main__":
    test_addresses()