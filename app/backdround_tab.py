import streamlit as st
from src.states.State import URLCONFIF
def run_background_tab(client):
    st.title("📝 BlogPost Generator (Background)")
    st.info("Generate blog posts asynchronously in the background.")

    option = st.selectbox("Select Option:", ["New", "Resume"])

    def select_assistant():
        assistants = client.assistants.search()
        if not assistants:
            st.warning("No assistants found.")
            return None, None
        names = [a['name'] for a in assistants]
        selected_name = st.selectbox("Select Assistant", names)
        selected_id = next((a['assistant_id'] for a in assistants if a['name'] == selected_name), None)
        return selected_name, selected_id

    def select_thread():
        threads = client.threads.search()
        return st.selectbox("Select Thread", [t['thread_id'] for t in threads])

    def background_run(thread_id, assistant_id):
        with st.spinner("Starting background run..."):
            assisant = client.assistants.get(assistant_id=assistant_id)
            # assinstant_config = assisant['config']
            config = URLCONFIF(
                category=assisant['config']['category'],
                country=assisant['config']['country'],
                language=assisant['config']['language'],
                WP_URL=assisant['config']['WP_URL']

            )
            st.write(config)
            # try:
            #     assisant = client.assistants.get(assistant_id=assistant_id)
            #     run_data = client.runs.create(
            #         thread_id=thread_id,
            #         assistant_id=assistant_id,
            #         input={"config":config},
            #         metadata={"name": "blog_generation_run"},
            #         webhook=None,  # Optional: Set your webhook URL
            #         multitask_strategy="interrupt",
            #         stream_resumable=True,
            #         checkpoint_during=True
            #     )
            #     run_id = run_data["run_id"]
            #     st.success(f"✅ Background run started. Run ID: `{run_id}`")
            #     st.success(run_data)
            #     st.session_state["run_id"] = run_id
            # except Exception as e:
            #     st.error(f"❌ Failed to start background run: {e}")

    def show_run_metadata(thread_id, run_id):
        try:
            run_data = client.runs.get(thread_id=thread_id, run_id=run_id)
            st.subheader("📄 Run Metadata")
            st.json(run_data)
        except Exception as e:
            st.error(f"❌ Could not fetch run metadata: {e}")

    # === New Run ===
    if option == "New":
        name, assistant_id = select_assistant()
        if assistant_id:
            thread_option = st.selectbox("Thread Option", ["New Thread", "Existing Thread"])
            thread_id = None

            if thread_option == "New Thread":
                if st.button("Create New Thread"):
                    thread = client.threads.create()
                    st.success(f"✅ New Thread Created: `{thread['thread_id']}`")
                    thread_id = thread['thread_id']
            else:
                thread_id = select_thread()

            if thread_id and st.button("Start Background Task"):
                background_run(thread_id, assistant_id)

    # === Resume ===
    elif option == "Resume":
        thread_id = select_thread()
        run_id = st.text_input("Enter Background Run ID")

        if run_id and st.button("Show Run Metadata"):
            show_run_metadata(thread_id, run_id)
