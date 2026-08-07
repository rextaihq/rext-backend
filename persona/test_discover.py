import json
import os
import sys

# Ensure persona directory is in python path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from discover import discover_personas_from_url

def run_test():
    # Pass the main website domain (or any target URL given by your user)
    target_url = "https://rankinggrow.com/"
    output_json_file = os.path.join(os.path.dirname(__file__), "persona_output.json")

    print(f"[+] Starting advertools crawl & persona analysis for: {target_url}...")
    
    personas = discover_personas_from_url(target_url)

    with open(output_json_file, "w", encoding="utf-8") as f:
        json.dump(personas, f, indent=4, ensure_ascii=False)

    print(f"[✔] Discovery Complete!")
    print(f"[✔] Total Personas Found: {len(personas)}")
    print(f"[✔] Output saved successfully to: {output_json_file}")

if __name__ == "__main__":
    run_test()