import streamlit as st
from streamlit_option_menu import option_menu
from langgraph_sdk import get_sync_client
from app.assisant import assistant_tab
from app.blogGenerator import blog_generator_tab

# Set full-width layout
st.set_page_config(layout="wide")

# Initialize LangGraph client
client = get_sync_client(
    url="http://127.0.0.1:2024",
    api_key="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"
)

# Main horizontal menu
selected = option_menu("Main Menu", ["Assistant", 'BlogPost Generator', 'Configuration'], 
            icons=['robot', 'pencil', 'gear'],
            menu_icon="cast", default_index=0, orientation="horizontal")

# Load Assistant Tab
if selected == "Assistant":
    assistant_tab(client)

# BlogPost Generator Tab
elif selected == "BlogPost Generator":
    # client.threads.delete(thread_id='71fb8a2b-c0ba-4487-8cde-25297fd72a26')
    blog_generator_tab(client)

# Configuration Tab
elif selected == "Configuration":
    st.title("⚙️ Configuration")
    st.write("Set up API keys, endpoints, and preferences here.")
