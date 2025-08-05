import streamlit as st
from langgraph.types import Command

def blog_generator_tab(client):
    st.title("📝 BlogPost Generator")
    st.info("Select an assistant to generate blog posts.")

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

    def handle_interrupt(thread_data):
        interrupt_key = list(thread_data['interrupts'].keys())[0]
        data_list = thread_data['interrupts'][interrupt_key]
        latest = data_list[0]

        checkpoint_id = latest['id']
        checkpoint_ns = latest['value']['name']
        node_output = latest['value']['value']

        st.write("Checkpoint ID:", checkpoint_id)
        st.write("Checkpoint Namespace:", checkpoint_ns)
        st.write("Node Output Message:", node_output)

        user_checkpoint_id = st.text_input("Enter Checkpoint ID:", value=checkpoint_id)
        user_checkpoint_ns = st.text_input("Enter Node Name (namespace):", value=checkpoint_ns)
        resume_input = st.text_input("Enter Your Response")
        return user_checkpoint_id, user_checkpoint_ns, resume_input


    def stream_run(thread_id, assistant_id, checkpoint=None, resume_value=None):
        assisant = client.assistants.get(assistant_id=assistant_id)
        assinstant_config = assisant['config']
        processed_nodes = set()
        node_containers = {}

        for mode, chunk in client.runs.stream(
            thread_id=thread_id,
            assistant_id=assistant_id,
            checkpoint=checkpoint,
            input={"config":assinstant_config},
            command={"resume": resume_value} if resume_value else {},
            stream_mode=["updates", "messages"],
            stream_resumable=True,
            checkpoint_during=True,
        ):
            # st.write("Mode",mode)

            # ==============Streaming the respone tring=============

            # if mode.startswith("messages/"):
            #     stream_type = mode.split("/", 1)[1]
            #     if stream_type == "metadata":
            #         st.write("Meta Data")
            #         # st.write(chunk)
            #         # msg_id = chunk.get("message_id")
            #         # node = chunk.get("langgraph_node")
            #         # set up a new chat bubble, store metadata, etc.
            #     elif stream_type == "partial":
            #         # with st.chat_message("assistant"):
            #         # st.write_stream(stream_respone(chunk))
            #         for chunk_data in chunk:
            #             # st.write(chunk_data.get("content")[-1])
            #             print(chunk_data.get("content"),end="|",flush=True)

            # ==============Streaming the respone tring=============
            
            
            if mode == "updates" and "__interrupt__" in chunk:
                interrupt_data = chunk["__interrupt__"][0]
                st.warning("⚠️ Interrupt")
                # Extract interrupt data
                interrupt_id = interrupt_data["id"]
                name = interrupt_data["value"]["name"]
                message = interrupt_data["value"]["value"]

                    # Show to user
                st.subheader("🛑 Interrupt Triggered")
                st.markdown(f"**Checkpoint Name:** `{name}`")
                st.markdown(f"**Checkpoint Message:**")
                st.code(message)

            elif mode == "messages":
                for node in chunk:
                    if node not in processed_nodes:
                        processed_nodes.add(node)
                        with st.expander(f"📩 Message from Node: {node}"):
                            st.json(chunk[node])
                            # st.write_stream(node)

            elif mode == "updates":
                for node in chunk:
                    if node not in processed_nodes:
                        processed_nodes.add(node)
                        with st.expander(f"✅ Node Completed: {node}"):
                            st.json(chunk[node])

    # Option: New
    if option == 'New':
        name, assistent_id = select_assistant()
        if assistent_id:
            thread_choice = st.selectbox("Select Thread", ["New Thread", "Existing Threads"])
            thread_id = None

            if thread_choice == "New Thread":
                if st.button("Create New Thread"):
                    thread = client.threads.create()
                    st.success(f"New thread created with ID: {thread['thread_id']}")
                    thread_id = thread['thread_id']
            else:
                thread_id = select_thread()

            if thread_id and st.button("Generate Blog Post"):
                try:
                    stream_run(thread_id, assistent_id)
                except Exception as e:
                    st.error(f"❌ Failed to generate blog post: {str(e)}")

    # Option: Resume
    elif option == 'Resume':
        st.write("Resume your workflow")
        name, assistent_id = select_assistant()
        thread_id = select_thread()
        thread_data = client.threads.get(thread_id)

        if thread_data['status'] == "interrupted":
            st.success("Thread is interrupted, ready to resume.")
            checkpoint_id, checkpoint_ns, resume_input = handle_interrupt(thread_data)

            if st.button("Submit"):
                try:
                    stream_run(
                        thread_id,
                        assistent_id,
                        checkpoint={
                            "thread_id": thread_id,
                            "checkpoint_ns": checkpoint_ns,
                            "checkpoint_id": checkpoint_id
                        },
                        resume_value=resume_input
                    )
                except Exception as e:
                    st.error(f"❌ Failed to resume run: {str(e)}")