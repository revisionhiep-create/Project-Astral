"""Test script for shared memory system"""
import sys
import os
import json
import re

# Fix Windows console encoding
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding='utf-8')

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

# Direct test without full imports to avoid dependency issues
DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")
MEMORY_FILE = os.path.join(DATA_DIR, "memory", "shared_memory.json")
SUMMARY_FILE = os.path.join(DATA_DIR, "memory", "shared_summary.txt")

def test_shared_memory():
    """Test the shared memory system."""
    print("=== Testing Shared Memory System ===\n")

    # Test 1: Load memory
    print("Test 1: Loading shared memory...")
    try:
        with open(MEMORY_FILE, "r", encoding="utf-8") as f:
            history = json.load(f)
        print(f"✓ Loaded {len(history)} messages from shared_memory.json")

        if history:
            print(f"\nLast message:")
            last_msg = history[-1]
            print(f"  Role: {last_msg.get('role')}")
            print(f"  Username: {last_msg.get('username', 'N/A')}")
            print(f"  Content: {last_msg['parts'][0][:100]}...")
            print(f"  Timestamp: {last_msg.get('timestamp')}")
    except Exception as e:
        print(f"✗ Failed to load: {e}")
        return

    # Test 2: Format for router simulation
    print("\n\nTest 2: Simulating format for router...")
    formatted = []
    for msg in history[-10:]:  # Last 10 messages
        original_content = msg["parts"][0] if msg["parts"] else ""

        if msg["role"] == "user" and msg.get("username"):
            username = msg["username"]
            formatted.append(f"[{username}]: {original_content[:80]}...")
        elif msg["role"] == "model":
            cleaned = re.sub(r'\[🔍\d*\]', '', original_content)
            cleaned = re.sub(r'\[💡\d*\]', '', cleaned)
            formatted.append(f"[Astral]: {cleaned[:80]}...")

    print(f"✓ Formatted {len(formatted)} messages")
    print(f"\nLast 3 formatted messages:")
    for msg in formatted[-3:]:
        print(f"  {msg}")

    # Test 3: Load summary
    print("\n\nTest 3: Loading summary...")
    try:
        if os.path.exists(SUMMARY_FILE):
            with open(SUMMARY_FILE, "r", encoding="utf-8") as f:
                summary_text = f.read().strip()
            print(f"✓ Summary exists ({len(summary_text)} chars)")
            print(f"\nSummary preview:")
            print(summary_text[:200] + "...")
        else:
            print("✗ No summary file found")
    except Exception as e:
        print(f"✗ Failed to load summary: {e}")

    # Test 4: Check for GemGem messages
    print("\n\nTest 4: Checking for GemGem messages...")
    gemgem_count = sum(1 for msg in history if msg.get("username") == "GemGem")
    print(f"✓ Found {gemgem_count} messages from GemGem")

    # Test 5: Check for Astral messages
    print("\n\nTest 5: Checking for Astral messages...")
    astral_user_count = sum(1 for msg in history if msg.get("username") == "Astral" and msg.get("role") == "user")
    astral_model_count = sum(1 for msg in history if msg.get("role") == "model")
    print(f"✓ Found {astral_user_count} messages from Astral (as user)")
    print(f"✓ Found {astral_model_count} messages from Astral (as model)")

    print("\n=== All tests completed! ===")

if __name__ == "__main__":
    test_shared_memory()
