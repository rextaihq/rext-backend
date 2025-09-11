import streamlit as st
from src.states.State import URLCONFIF

def run_wait_tab(client):
    st.title("📝 BlogPost Generator (Wait for Execution)")
    st.info("Run the workflow and wait until execution completes.")

    def select_assistant(key):
        assistants = client.assistants.search()
        if not assistants:
            st.warning("No assistants found.")
            return None, None
        names = [a['name'] for a in assistants]
        selected_name = st.selectbox("Select Assistant", names,key=f"Run and wait {key}")
        selected_id = next((a['assistant_id'] for a in assistants if a['name'] == selected_name), None)
        return selected_name, selected_id

    def select_thread():
        threads = client.threads.search()
        return st.selectbox("Select Thread", [t['thread_id'] for t in threads],key="selectbox")
    
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

    def run_and_wait(thread_id, assistant_id, resume_value={},checkpoint=None):
        with st.spinner("Running the workflow... Please wait."):
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
            try:
                result = client.runs.wait(
                    thread_id=thread_id,
                    assistant_id=assistant_id,
                    input={"config":config.model_dump() },
                    checkpoint=checkpoint,
                    metadata={"source": "run_wait_tab"},
                    command={"resume": resume_value} if resume_value else {},
                    multitask_strategy="interrupt",
                    checkpoint_during=True
                )

                st.success("✅ Workflow completed.")

                # Check if there's an interrupt in the result
                if "__interrupt__" in result:
                    st.warning("⚠️ Workflow was interrupted.")

                    # Extract interrupt data
                    interrupt_data = result["__interrupt__"][0]  # assuming only one
                    interrupt_id = interrupt_data["id"]
                    name = interrupt_data["value"]["name"]
                    message = interrupt_data["value"]["value"]

                    # Show to user
                    st.subheader("🛑 Interrupt Triggered")
                    st.markdown(f"**Checkpoint Name:** `{name}`")
                    st.markdown(f"**Checkpoint Message:**")
                    st.code(message)

                    # Optionally capture user response
                    user_response = st.text_input("Enter your response to resume", key="resume_input_wait")

                    if st.button("Resume Workflow"):
                        result2 = client.runs.wait(
                            thread_id=thread_id,
                            assistant_id=assistant_id,
                            input={},
                            metadata={"source": "run_wait_tab"},
                            command={"resume": user_response},
                            checkpoint={
                                "thread_id": thread_id,
                                "checkpoint_id": interrupt_id,
                                "checkpoint_ns": name
                            },
                            multitask_strategy="interrupt",
                            checkpoint_during=True
                        )
                        st.success("✅ Workflow resumed and completed.")
                        st.subheader("📄 Final Output After Resume")
                        st.json(result2)

                else:
                    st.subheader("📄 Final Run Output")
                    st.json(result)
            except Exception as e:
                st.error(f"❌ Failed to run workflow: {e}")

    # === UI Flow ===
    option = st.selectbox("Select Option", ["New", "Resume"])

    name, assistant_id = select_assistant(key=1)  # Keep only this one

    if assistant_id:
        if option == "New":
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
                    run_and_wait(thread_id, assistant_id)
                except Exception as e:
                    st.error(f"❌ Failed to generate blog post: {str(e)}")

        elif option == 'Resume':
            st.write("Resume your workflow")
            # Removed duplicate select_assistant here
            thread_id = select_thread()
            thread_data = client.threads.get(thread_id)

            if thread_data['status'] == "interrupted":
                st.success("Thread is interrupted, ready to resume.")
                checkpoint_id, checkpoint_ns, resume_input = handle_interrupt(thread_data)

                if st.button("Submit"):
                    try:
                        run_and_wait(
                            thread_id,
                            assistant_id,  # Reuse original assistant_id
                            checkpoint={
                                "thread_id": thread_id,
                                "checkpoint_ns": checkpoint_ns,
                                "checkpoint_id": checkpoint_id
                            },
                            resume_value=resume_input
                        )
                    except Exception as e:
                        st.error(f"❌ Failed to resume workflow: {str(e)}")


        # else:
        #     thread_id = select_thread()

        # if thread_id and st.button("Run and Wait"):
        #     run_and_wait(thread_id, assistant_id, resume_value=resume_data)
