import streamlit as st
import asyncio
from src.flow.engines.wrext import create_wrext_engine

st.set_page_config(page_title="Keyword Difficulty Tester", layout="wide")

st.title("Keyword Difficulty Testing Tool")

st.write("Enter your query and country code (e.g., `us`, `pk`, `in`)")

# -----------------------------
# Input Section
# -----------------------------
query = st.text_input("Keyword / Query", value="wordpress backup solutions")
country = st.text_input("Country Code", value="us")

if st.button("Run Test"):
    if not query or not country:
        st.error("Please enter both query and country code.")
    else:
        with st.spinner("Running..."):
            graph = create_wrext_engine()
            result = asyncio.run(
                graph.ainvoke(
                    {
                        "serp_payload": {
                            "query": query,
                            "country": country
                        }
                    }
                )
            )

        st.success("Done!")
        st.subheader("Result Output")
        st.json(result)
