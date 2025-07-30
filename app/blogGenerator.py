import streamlit as st

def blog_generator_tab(client):
    st.title("📝 BlogPost Generator")
    st.info("Select an assistant to generate blog posts.")

    # list down all the assistants
    try:
        assistants = client.assistants.search()
        if assistants:
            user_sel_assistent = st.selectbox("Select Assistant", options=[a['name'] for a in assistants], key="assistant_select")

            assistent_id = ([a for a in assistants if a['name'] == user_sel_assistent][0]['assistant_id'])

            if user_sel_assistent:
                thread_choice = st.selectbox("Select Thread", options=["Existing Threads","New Thread"], key="thread_choice")

                if thread_choice == "New Thread":
                    if st.button("Create New Thread"):
                        thread = client.threads.create()
                        st.success(f"New thread created with ID: {thread['thread_id']}")
                        thread_id = thread['thread_id']
                else:
                    thread = client.threads.search()
                    thread_id = st.selectbox("Select Existing Thread", options=[t['thread_id'] for t in thread], key="existing_thread_select")

            if user_sel_assistent and thread_id:
                st.subheader("Generate Blog Post")


                if st.button("Generate Blog Post"):
                    try:
                        for chunk in client.runs.stream(
                            thread_id=thread_id,
                            assistant_id=assistent_id,
                            input={},
                            stream_mode=["values"],
                            metadata={"name":"my_run"},
                            # feedback_keys=["my_feedback_key_1","my_feedback_key_2"],
                            # webhook="https://my.fake.webhook.com",
                            # multitask_strategy="interrupt"
                        
                        ):
                            if(chunk.event == "values"):
                                # st.write("Response:", chunk.data)
                                for msg in chunk.data:
                                    st.write("Response:", msg)

                                st.write("Chunks:", chunk.data)
                                st.write("chunks length:", len(chunk.data))

                    except Exception as e:
                        st.error(f"Failed to generate blog post: {str(e)}")
                    finally:
                        client.threads.delete(thread_id=thread_id)

        else:
            st.warning("No assistants found.")
    except Exception as e:
        st.error(f"Failed to load assistants: {str(e)}")