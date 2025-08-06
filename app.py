import streamlit as st
from streamlit_option_menu import option_menu
from langgraph_sdk import get_sync_client
from app.assisant import assistant_tab
from app.stream_tab import blog_generator_tab
from app.backdround_tab import run_background_tab
from app.runAndWait_tab import run_wait_tab
from app.configration import set_configuration
from app.threads import thread_tab
from dotenv import load_dotenv
import os
load_dotenv()

# Set full-width layout
st.set_page_config(layout="wide")

# Initialize LangGraph client
client = get_sync_client(
    url="http://localhost:8123/",

    # url = "http://127.0.0.1:2024",
    api_key=os.getenv('LANGSMITH_API_KEY')
)


# Main horizontal menu
selected = option_menu(
    "Main Menu",
    ["Assistant", "Configuration","BlogPost Generator", "Threads"],
    icons=["robot", "pencil", "list", "gear"],
    menu_icon="cast",
    default_index=0,
    orientation="horizontal"
)

# Load Assistant Tab
if selected == "Assistant":
    assistant_tab(client)

# BlogPost Generator Tab
elif selected == "BlogPost Generator":
    generator_mode = option_menu(
        "Select Blog Generator Mode",
        ["Run & Wait", "Stream", "Background"],
        icons=["play", "wifi", "clock"],
        menu_icon="cast",
        default_index=0,
        orientation="horizontal"
    )

    if generator_mode == "Stream":
        blog_generator_tab(client)
    elif generator_mode == "Background":
        run_background_tab(client=client)
    elif generator_mode == "Run & Wait":
        run_wait_tab(client=client)

# Threads Tab
elif selected == "Threads":
    thread_tab(client)

# Configuration Tab (optional stub)
elif selected == "Configuration":
    set_configuration(client=client)
