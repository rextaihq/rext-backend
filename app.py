import streamlit as st
import yaml
import os
import requests
import json


CONFIG_PATH = "config.yaml"

# Load existing config
def load_config(path=CONFIG_PATH):
    if os.path.exists(path):
        with open(path, 'r') as file:
            return yaml.safe_load(file)
    return {}

# Save config
def save_config(data, path=CONFIG_PATH):
    with open(path, 'w') as file:
        yaml.dump(data, file)

st.title("Blog Post Automation")

# Language codes
language_dict = {
    "Arabic": "ar", "Chinese": "zh", "Dutch": "nl", "English": "en", "French": "fr",
    "German": "de", "Greek": "el", "Hindi": "hi", "Italian": "it", "Japanese": "ja",
    "Malayalam": "ml", "Marathi": "mr", "Norwegian": "no", "Portuguese": "pt",
    "Romanian": "ro", "Russian": "ru", "Spanish": "es", "Swedish": "sv",
    "Tamil": "ta", "Telugu": "te", "Ukrainian": "uk"
}

# Country codes
country_dict = {
    "Australia": "au", "Brazil": "br", "Canada": "ca", "China": "cn", "Egypt": "eg",
    "France": "fr", "Germany": "de", "Greece": "gr", "Hong Kong": "hk", "India": "in",
    "Ireland": "ie", "Italy": "it", "Japan": "jp", "Netherlands": "nl", "Norway": "no",
    "Pakistan": "pk", "Peru": "pe", "Philippines": "ph", "Portugal": "pt", "Romania": "ro",
    "Russian Federation": "ru", "Singapore": "sg", "Spain": "es", "Sweden": "se",
    "Switzerland": "ch", "Taiwan": "tw", "Ukraine": "ua", "United Kingdom": "gb",
    "United States": "us"
}

st.header("Set the Parameters")

# Category Selection
categories = st.selectbox(
    "Select Category", 
    ["general", "world", "nation", "business", "technology", "entertainment", "sports", "science", "health"]
)

# Country Selection
selected_country = st.selectbox("Select Country", list(country_dict.keys()))
country_code = country_dict[selected_country]

# Language Selection
selected_language = st.selectbox("Select Language", list(language_dict.keys()))
language_code = language_dict[selected_language]

# RSS Feed Control
user_choice = st.selectbox(
    "Do you want to add WordPress feed or use default feed?",
    ['yes', 'no']
)

feed_urls = []
rss_dict = {}

if user_choice == 'yes':
    feed_input = st.text_input("Enter the Feed URLs (comma-separated)")
    if feed_input:
        feed_urls = [url.strip() for url in feed_input.split(',')]
        for i, url in enumerate(feed_urls):
            rss_dict[f"UserFeed{i+1}"] = url

# Submit button
if st.button("Submit data"):
    config_data = load_config()

    # Update GNews section
    config_data['GNews'] = {
        'url': "https://gnews.io/api/v4/top-headlines",
        'category': categories,
        'country': country_code,
        'language': language_code
    }

    # Update RSS feeds
    if feed_urls:
        config_data['rss_sources'] = rss_dict

    # Save locally as YAML
    save_config(config_data)

    # Prepare payload for API (excluding URL for GNews)
    api_payload = {
        "category": categories,
        "country": country_code,
        "language": language_code,
        "rss_sources": [
            {"title": name, "url": url}
            for name, url in rss_dict.items()
        ] if rss_dict else None
    }

    try:
    #     requests.post(
    # "http://127.0.0.1:2024/api/workflow/configure",
    # headers={
    #   "Content-Type": "application/json"
    # },
    # json=null
# )
        response = requests.post(
            "http://127.0.0.1:2024/api/workflow/configure",
            headers={"Content-Type": "application/json"},
            data=json.dumps(api_payload)
        )
        if response.status_code == 200:
            st.success("✅ Configuration sent to API and saved locally!")
            st.write("API Response:")
            st.json(response.json())
        else:
            st.error(f"❌ API returned status code {response.status_code}")
            st.text(response.text)



    except Exception as e:
        st.error(f"❌ Failed to send data to API: {str(e)}")

    # Show final config
    # st.write("Final Configuration (YAML):")
    # st.write(config_data)
    st.write(api_payload)



# res = requests.get(
#     "http://127.0.0.1:2024/api/workflow/status"
# )
# print(res.json())