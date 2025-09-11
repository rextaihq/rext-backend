import streamlit as st
from src.states.State import URLCONFIF


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
        all_interrupts = thread_data.get('interrupts', {})
        if not all_interrupts:
            st.warning("No interrupts found.")
            return None, None, None

        # Flatten all interrupts into a list
        flattened_interrupts = []
        for key, data_list in all_interrupts.items():
            for interrupt in data_list:
                flattened_interrupts.append({
                    "interrupt_key": key,
                    "id": interrupt.get("id"),
                    "value": interrupt.get("value")
                })

        # Display each interrupt
        for i, interrupt in enumerate(flattened_interrupts):
            st.markdown(f"### Interrupt {i+1} (Key: {interrupt['interrupt_key']})")
            st.write("Interrupt ID:", interrupt['id'])
            # Handle value being either string or dict
            value = interrupt['value']
            if isinstance(value, dict):
                node_output = value.get('value', '')
                checkpoint_ns = value.get('name', interrupt['id'])
            else:
                node_output = value
                checkpoint_ns = interrupt['id']

            st.markdown(f"Checkpoint Namespace: {checkpoint_ns}")
            st.code(f"Node Output Message:\n{node_output}")

        # Let user select which interrupt to respond to
        selected_index = st.selectbox("Select Interrupt to respond to:", range(len(flattened_interrupts)), format_func=lambda x: f"{flattened_interrupts[x]['id']}")
        
        selected_interrupt = flattened_interrupts[selected_index]
        resume_input = st.text_input("Enter Your Response")

        selected_value = selected_interrupt['value']
        if isinstance(selected_value, dict):
            checkpoint_ns = selected_value.get('name', selected_interrupt['id'])
        else:
            checkpoint_ns = selected_interrupt['id']

        return selected_interrupt['id'], checkpoint_ns, resume_input

    def stream_run(thread_id, assistant_id, checkpoint=None, resume_value=None):
        assisant = client.assistants.get(assistant_id=assistant_id)

        config = URLCONFIF(
            category=assisant['config']['category'],
            country=assisant['config']['country'],
            language=assisant['config']['language'],
            WP_URL=assisant['config']['WP_URL'],
            keyword=assisant['config']['keyword'],
            similarity_threshold=assisant['config']['similarity_threshold']
        )

        st.write(config.model_dump())
        processed_nodes = set()

        for mode, chunk in client.runs.stream(
            thread_id=thread_id,
            assistant_id=assistant_id,
            checkpoint=checkpoint,
            input={"config":config.model_dump()},
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