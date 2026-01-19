import streamlit as st
import asyncio
import pandas as pd
import time
from src.flow.engines.serp.serp_engine import create_serp_engine
from src.flow.states.wrext import WREXT

# Page configuration
st.set_page_config(
    page_title="Content Automation Engine Prototype",
    page_icon="🚀",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom CSS for better aesthetics
st.markdown("""
    <style>
    .main {
        background-color: #0e1117;
    }
    .stMetric {
        background-color: #1e2130;
        padding: 15px;
        border-radius: 10px;
        border: 1px solid #3e4255;
    }
    .stAlert {
        border-radius: 10px;
    }
    .stButton>button {
        width: 100%;
        border-radius: 5px;
        height: 3em;
        background-color: #ff4b4b;
        color: white;
    }
    </style>
    """, unsafe_allow_html=True)

st.title("🚀 Content Automation Engine")
st.markdown("### Prototype: SERP Analysis & Smart Scraper")

# Sidebar for inputs
with st.sidebar:
    st.header("Search Configuration")
    query = st.text_input("Enter Search Query", placeholder="e.g., best ai coding assistants 2025")
    country = st.selectbox("Country", ["us", "gb", "ca", "au", "in"], index=0)
    
    st.divider()
    st.header("Scraper Settings")
    threshold = st.slider("Relevance Threshold", 0.0, 1.0, 0.3)
    
    run_button = st.button("Run Flow")

async def run_flow(query, country):
    flow = create_serp_engine()
    
    initial_state: WREXT = {
        "serp_payload": {
            "query": query,
            "country": country
        }
    }
    
    # Track progress using a container
    status_container = st.container()
    with status_container:
        st.subheader("Execution Trace")
        progress_bar = st.progress(0)
        status_text = st.empty()
        node_status = st.empty()
        
    start_time = time.time()
    final_state = {}
    
    try:
        # Use streaming to see each node execution
        # stream_mode="updates" yields dicts like {node_name: {state_updates}}
        step_count = 0
        total_estimated_steps = 6 # fetch, normalize, extract, scrape_flow (which has scrape, filter)
        
        async for event in flow.astream(initial_state, stream_mode="updates", subgraphs=True):
            step_count += 1
            progress = min(step_count / total_estimated_steps, 0.95)
            progress_bar.progress(progress)
            
            # When subgraphs=True, event is a tuple (namespace, data)
            # namespace is a list of graph names, data is the update dict
            if isinstance(event, tuple):
                namespace, data = event
                node_data = data
            else:
                node_data = event

            for node_name, output in node_data.items():
                status_text.info(f"Running node: **{node_name}**")
                
                # Show a small preview of what the node produced
                with status_container:
                    with st.expander(f"Node: {node_name} completed", expanded=False):
                        st.write(f"Namespace: {namespace if 'namespace' in locals() else 'root'}")
                        st.write("State Updates:")
                        st.json({k: "(data...)" if isinstance(v, (list, dict)) and len(str(v)) > 200 else v 
                                for k, v in output.items()})
                
                # Merge updates into final_state to return at the end
                final_state.update(output)
        
        end_time = time.time()
        duration = end_time - start_time
        
        progress_bar.progress(1.0)
        status_text.success(f"✅ Flow completed in {duration:.2f} seconds!")
        
        return final_state
    except Exception as e:
        st.error(f"Error running flow: {str(e)}")
        return None

if run_button and query:
    # Run the async flow
    with st.spinner("Processing..."):
        result = asyncio.run(run_flow(query, country))
    
    if result:
        st.divider()
        
        # Tabs for different views
        tab1, tab2, tab3, tab4 = st.tabs(["📊 SERP Analysis", "🏢 Competitors", "📄 Scraped Content", "🎯 Relevant Chunks"])
        
        with tab1:
            st.header("Normalized SERP Results")
            serp_norm = result.get("serp_normalized", {})
            if serp_norm:
                # Metrics
                col1, col2, col3 = st.columns(3)
                col1.metric("Total Results", serp_norm.get("stats", {}).get("organic_count", 0))
                col2.metric("Unique Domains", serp_norm.get("domain_stats", {}).get("unique_domains", 0))
                col3.metric("Recent Content", serp_norm.get("freshness", {}).get("recent", 0))
                
                # Table
                df_results = pd.DataFrame(serp_norm.get("normalize_results", []))
                if not df_results.empty:
                    st.dataframe(df_results[["position", "title", "domain", "url"]], use_container_width=True)
                
                # Questions
                if serp_norm.get("questions"):
                    st.subheader("People Also Ask")
                    for q in serp_norm["questions"]:
                        st.write(f"- {q}")
            else:
                st.warning("No normalized SERP data found.")

        with tab2:
            st.header("Competitor Landscape")
            competitors = result.get("competitors", [])
            if competitors:
                df_comp = pd.DataFrame(competitors)
                st.dataframe(df_comp, use_container_width=True)
            else:
                st.warning("No competitor data found.")

        with tab3:
            st.header("Scraped Documents")
            scrape_context = result.get("scrape_context", [])
            if scrape_context:
                for doc in scrape_context:
                    with st.expander(f"📄 {doc.metadata.get('domain')} - {doc.metadata.get('url')[:50]}..."):
                        st.write(f"**Status:** {doc.metadata.get('status')}")
                        st.text_area("Content Preview", doc.page_content[:1000] + "...", height=200)
                        if doc.metadata.get("links_detail"):
                            st.write(f"**Internal Links Found:** {len(doc.metadata['links_detail'])}")
            else:
                st.warning("No scraped content found.")

        with tab4:
            st.header("Semantically Relevant Chunks")
            relevant_context = result.get("relevant_context", [])
            if relevant_context:
                st.info(f"Found {len(relevant_context)} chunks matching your query above the threshold.")
                for i, item in enumerate(relevant_context):
                    score = item.get("score", 0)
                    color = "green" if score > 0.6 else "orange"
                    st.markdown(f"#### Chunk {i+1} (Score: :{color}[{score:.4f}])")
                    st.markdown(f"**Source:** {item.get('metadata', {}).get('url')}")
                    st.info(item.get("chunk"))
                    st.divider()
            else:
                st.warning("No relevant chunks found. Try lowering the threshold.")

elif run_button and not query:
    st.warning("Please enter a search query first.")

# Footer
st.divider()
st.caption("Content Automation Engine Prototype | Built with Streamlit & LangGraph")
