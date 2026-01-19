import streamlit as st
import asyncio
import sys
import os

sys.path.append(os.path.abspath(os.path.dirname(__file__)))

from src.flow.engines.wrext import create_wrext_engine

st.set_page_config(page_title="Keyword Difficulty Tester", layout="wide")
st.title("Keyword Difficulty Testing Tool")
st.write("Enter your query and country code (us, pk, in)")

query = st.text_input("Keyword / Query", value="wordpress backup solutions")
country = st.text_input("Country Code", value="us")

# -----------------------------
# SAFE ASYNC RUNNER
# -----------------------------
async def run_kd(query, country):
    graph = create_wrext_engine()
    return await graph.ainvoke(
        {
            "serp_payload": {
                "query": query,
                "country": country
            }
        }
    )

if st.button("Run Test"):
    if not query or not country:
        st.error("Please enter both query and country code.")
    else:
        with st.spinner("Running keyword difficulty..."):
            result = asyncio.run(run_kd(query, country))

        st.success("Done!")
        st.subheader("Keyword Difficulty Result")
        st.json(result["seo_result"]["keyword_difficulty"])
