import streamlit as st
from typing import Dict
from src.states.State import URLCONFIF

def set_configuration(client):
    def select_assistant(key):
        assistants = client.assistants.search()
        if not assistants:
            st.warning("No assistants found.")
            return None, None
        names = [a['name'] for a in assistants]
        selected_name = st.selectbox("Select Assistant", names, key=f"assistant_select_{key}")
        selected_id = next((a['assistant_id'] for a in assistants if a['name'] == selected_name), None)
        return selected_name, selected_id
    
    assistant_name, assistant_id = select_assistant(1)
    assisant = client.assistants.get(assistant_id=assistant_id)
    # st.json(assisant)

    if assisant['config']:
        config = URLCONFIF(
            category=assisant['config']['category'],
            country=assisant['config']['country'],
            language=assisant['config']['language'],
            WP_URL=assisant['config']['WP_URL']

        )

        st.json(config)
    if assistant_id:
        st.header(f"{assistant_name} Configuration Settings")

        # Supported countries
        country_options = {
            "Australia": "au", "Brazil": "br", "Canada": "ca", "China": "cn", "Egypt": "eg",
            "France": "fr", "Germany": "de", "Greece": "gr", "Hong Kong": "hk", "India": "in",
            "Ireland": "ie", "Italy": "it", "Japan": "jp", "Netherlands": "nl", "Norway": "no",
            "Pakistan": "pk", "Peru": "pe", "Philippines": "ph", "Portugal": "pt", "Romania": "ro",
            "Russian Federation": "ru", "Singapore": "sg", "Sweden": "se", "Switzerland": "ch",
            "Taiwan": "tw", "Ukraine": "ua", "United Kingdom": "gb", "United States": "us"
        }

        # Supported languages
        language_options = {
            "Arabic": "ar", "Chinese": "zh", "Dutch": "nl", "English": "en", "French": "fr",
            "German": "de", "Greek": "el", "Hindi": "hi", "Italian": "it", "Japanese": "ja",
            "Malayalam": "ml", "Marathi": "mr", "Norwegian": "no", "Portuguese": "pt",
            "Romanian": "ro", "Russian": "ru", "Spanish": "es", "Swedish": "sv", "Tamil": "ta",
            "Telugu": "te", "Ukrainian": "uk"
        }

        selected_country_name = st.selectbox("Country", list(country_options.keys()), key="country_select")
        selected_language_name = st.selectbox("Language", list(language_options.keys()), key="language_select")

        # Optional: Add some sample or default keyword list
        category_list = ["AI", "Technology", "Finance", "Health", "Education", "Climate"]
        selected_category = st.selectbox("Keyword / Category", category_list, key="category")

        # Initialize feed URLs in session state (list of dicts with name & url)
        if "feed_entries" not in st.session_state:
            st.session_state.feed_entries = [{"name": "", "url": ""}]

        st.write("### WordPress Feed URLs")
        for i, entry in enumerate(st.session_state.feed_entries):
            name_key = f"feed_name_{i}"
            url_key = f"feed_url_{i}"
            entry["name"] = st.text_input(f"Feed Name {i+1}", value=entry["name"], key=name_key)
            entry["url"] = st.text_input(f"Feed URL {i+1}", value=entry["url"], key=url_key)

        if st.button("➕ Add another feed"):
            st.session_state.feed_entries.append({"name": "", "url": ""})

        # Save Button
        if st.button("✅ Save Configuration", key="save_config"):
            # Build dictionary from cleaned entries
            wordpress_feeds: Dict[str, str] = {}
            for entry in st.session_state.feed_entries:
                name = entry["name"].strip()
                url = entry["url"].strip()
                if name and url:
                    wordpress_feeds[name] = url

            # Construct config object
            config_obj = URLCONFIF(
                country=country_options[selected_country_name],
                language=language_options[selected_language_name],
                category=selected_category,
                WP_URL=wordpress_feeds
            )

            # Convert to dict to store in assistant (or keep as model if needed)
            config_dict = config_obj.dict()
            config_dict["assistant_id"] = assistant_id
            config_dict["assistant_name"] = assistant_name

            client.assistants.update(assistant_id=assistant_id, config=config_dict)

            st.success("✅ Configuration saved!")
            st.json(config_dict)
