# simple_app.py
import streamlit as st
import requests
st.title("Blog Post Automation")


if st.button("Generate Blog Post"):
    response = requests.get(
            "http://127.0.0.1:2024/api/workflow/status"
    )
    if response.status_code == 200:
        data = response.json()
        st.write("Workflow Status:", data.get("status", "No status available"))
    else:
        st.error("Failed to fetch workflow status. Please check the server.")
