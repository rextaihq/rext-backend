# import streamlit as st
# import asyncio
# import sys
# import os

# sys.path.append(os.path.abspath(os.path.dirname(__file__)))

# from src.flow.engines.wrext import create_wrext_engine

# st.set_page_config(page_title="Keyword Difficulty Tester", layout="wide")
# st.title("Keyword Difficulty Testing Tool")
# st.write("Enter your query and country code (us, pk, in)")

# query = st.text_input("Keyword / Query", value="wordpress backup solutions")
# country = st.text_input("Country Code", value="us")

# # -----------------------------
# # SAFE ASYNC RUNNER
# # -----------------------------
# async def run_kd(query, country):
#     graph = create_wrext_engine()
#     return await graph.ainvoke(
#         {
#             "serp_payload": {
#                 "query": query,
#                 "country": country
#             }
#         }
#     )

# if st.button("Run Test"):
#     if not query or not country:
#         st.error("Please enter both query and country code.")
#     else:
#         with st.spinner("Running keyword difficulty..."):
#             result = asyncio.run(run_kd(query, country))

#         st.success("Done!")
#         st.subheader("Keyword Difficulty Result")
#         st.json(result["seo_result"]["keyword_difficulty"])
import streamlit as st
import asyncio
import sys
import os

sys.path.append(os.path.abspath(os.path.dirname(__file__)))

from src.flow.engines.wrext import create_wrext_engine

st.set_page_config(page_title="Keyword Difficulty Tester", layout="wide")
st.title("Keyword Difficulty Testing Tool")
st.write("Enter your query and country code (us, pk, in)")

query = st.text_input("Keyword / Query", value="wordpress speed optimization service")
country = st.text_input("Country Code", value="us")

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

def show_kd_card(kd_data):
    keyword = kd_data["keyword"]
    volume = kd_data["monthly_search_volume"]
    score = kd_data["difficulty_score"]
    level = kd_data["difficulty_level"]
    signals = kd_data["difficulty_signals"]

    # Color map for difficulty level
    level_color = {
        "easy": "#4CAF50",        # Green
        "medium": "#FFEB3B",      # Yellow
        "hard": "#FF9800",        # Orange
        "very_hard": "#F44336"    # Red
    }
    color = level_color.get(level, "#CCCCCC")  # Default gray

    # HTML card
    card_html = f"""
    <div style="
        background-color:#1E1E1E; 
        padding:20px; 
        border-radius:15px; 
        color:white; 
        max-width:800px;
        box-shadow: 0 4px 12px rgba(0,0,0,0.3);
        margin-bottom: 20px;
    ">
        <h3 style="margin-bottom:5px;">Keyword: <span style='color:{color}'>{keyword}</span></h3>
        <p style="margin:0;">Monthly Search Volume: <b>{volume}</b></p>
        <p style="margin:0;">Difficulty Score: <b>{score}</b> (<span style='color:{color}'>{level}</span>)</p>
        <hr style="border-color:#444;">
        <div style="display:flex; justify-content:space-between;">
            <div style="flex:1; text-align:center; padding:10px;">Link Difficulty<br><b>{signals.get("link_difficulty",0)}</b></div>
            <div style="flex:1; text-align:center; padding:10px;">SERP Feature<br><b>{signals.get("serp_feature_pressure",0)}</b></div>
            <div style="flex:1; text-align:center; padding:10px;">Freshness<br><b>{signals.get("freshness_pressure",0)}</b></div>
            <div style="flex:1; text-align:center; padding:10px;">On-Page<br><b>{signals.get("onpage_pressure",0)}</b></div>
            <div style="flex:1; text-align:center; padding:10px;">Brand<br><b>{signals.get("brand_dominance",0)}</b></div>
        </div>
    </div>
    """
    st.markdown(card_html, unsafe_allow_html=True)

# -----------------------------
if st.button("Run Test"):
    if not query or not country:
        st.error("Please enter both query and country code.")
    else:
        with st.spinner("Running keyword difficulty..."):
            result = asyncio.run(run_kd(query, country))

        st.success("Done!")
        st.subheader("Keyword Difficulty Result")
        kd_data = result["seo_result"]["keyword_difficulty"]
        show_kd_card(kd_data)
