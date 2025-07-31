import streamlit as st
from langgraph.types import Command

def blog_generator_tab(client):
    st.title("📝 BlogPost Generator")
    st.info("Select an assistant to generate blog posts.")

    option = st.selectbox("Select Option: ",["New","Resume"])
    if option=='New':
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
                            node_containers = {}  # For dynamically displaying each node
                            processed_nodes = set()  # Track already seen nodes

                            for mode, chunk in client.runs.stream(
                                thread_id=thread_id,
                                assistant_id=assistent_id,
                                input={},
                                stream_mode=["updates", "messages"],
                                metadata={"name": "my_run"},
                                on_completion='delete',
                                stream_resumable=True,
                                checkpoint_during=True
                                
                            ):
                                if mode == "updates" and "__interrupt__" in chunk:
                                    interrupt_data = chunk["__interrupt__"]
                                    st.warning(f"⚠️ Interrupt:")
                                    if interrupt_data[0]['value']:                    
                                        st.header(interrupt_data[0]['value']['name'])
                                        st.write(interrupt_data[0]['value']['value'])
                                        # Ask your user via Streamlit UI for a response
                                        resume_value = st.text_input("Select Articles", key="resume_input")

                                        if len(resume_value)>0:
                                            # Now resume the run with the user's input
                                            for mode2, chunk2 in client.runs.stream(
                                                thread_id=thread_id,
                                                assistant_id=assistent_id,
                                                input=Command(resume=resume_value),
                                                stream_mode=["updates", "messages"],
                                                stream_resumable=True,
                                                checkpoint_during=True
                                            ):
                                                if mode2=="messages":
                                                    for node_id, msg in chunk2.data.items():
                                                        st.json(msg)
                                                elif mode2=="updates":
                                                    if node_id not in processed_nodes:
                                                        processed_nodes.add(node_id)
                                                        with st.expander(f"✅ Node Completed: {node_id}"):
                                                            st.json(chunk2.data[node_id])
                                        break  # Exit this primary loop so resumed run starts fresh
                                elif mode=='updates':
                                    for node in chunk:
                                        if node not in processed_nodes:
                                            processed_nodes.add(node)

                                            if node == 'interrupt':
                                                st.warning("❗️Interrupt Occur")
                                                st.write(chunk[node])
                                            else:
                                                with st.expander(f"🔄 Processing Node: {node}", expanded=True):
                                                        st.write("Processing...")
                                                
                                            node_containers[node] = st.expander(f"✅ Node Completed: {node}", expanded=False)
                                            with node_containers[node]:
                                                st.json(chunk[node])

                        except Exception as e:
                            st.error(f"❌ Failed to generate blog post: {str(e)}")

                        # finally:
                        #     client.threads.delete(thread_id=thread_id)
            else:
                st.warning("No assistants found.")
        except Exception as e:
            st.error(f"Failed to load assistants: {str(e)}")
    elif option=='Resume':
        st.write("Resue the workflow")

        assistants = client.assistants.search()
        if assistants:
                user_sel_assistent = st.selectbox("Select Assistant", options=[a['name'] for a in assistants], key="assistant_select")

                assistent_id = ([a for a in assistants if a['name'] == user_sel_assistent][0]['assistant_id'])

        thread = client.threads.search()
        thread_id = st.selectbox("Select Thread", options=[t['thread_id'] for t in thread], key="existing_thread_select")

        thread_data = client.threads.get(thread_id)

        st.json(thread_data['interrupts']['2e7fcc73-5559-9146-e712-f6755a0a1c69'][0]['value'])
        if (thread_data['status']=="interrupted"):
            st.write("Intrrrputed")

            data = thread_data['interrupts']['2e7fcc73-5559-9146-e712-f6755a0a1c69'][0]['ns'][0]
            st.write("Checkpoiner id: ",data.split(":")[1])
            st.write("Checkpoiner Node: ",data.split(":")[0])
            # enter the checkpointer id

            checkpointer_id = st.text_input("Enter Checkpoint Id: ")
            checkpoint_ns = st.text_input("Enter Node Name: ")
            
            resume_input = st.text_input("Enter Your Response")
            if st.button("Resume"):
                node_containers = {}  # For dynamically displaying each node
                processed_nodes = set()  # Track already seen nodes
                for mode, chunk in client.runs.stream(
                                    thread_id=thread_id,
                                    assistant_id=assistent_id,
                                    checkpoint = {
                                        "thread_id":thread_id,
                                        "checkpoint_ns":checkpoint_ns,
                                        "checkpoint_id":checkpointer_id
                                    },
                                    input={},
                                    command={
                                         "resume": resume_input
                                         },
                                    
                                    stream_mode=["updates", "messages"],
                                    metadata={"name": "my_run"},
                                    # on_completion='delete',
                                    stream_resumable=True,
                                    checkpoint_during=True,   
                                ):
                                    if mode == "updates" and "__interrupt__" in chunk:
                                        interrupt_data = chunk["__interrupt__"]
                                        st.warning(f"⚠️ Interrupt:")
                                        if interrupt_data[0]['value']:                    
                                            st.header(interrupt_data[0]['value']['name'])
                                            st.write(interrupt_data[0]['value']['value'])
                                            # Ask your user via Streamlit UI for a response
                                            resume_value = st.text_input("Select Articles", key="resume_input")

                                            if len(resume_value)>0:
                                                # Now resume the run with the user's input
                                                for mode2, chunk2 in client.runs.stream(
                                                    thread_id=thread_id,
                                                    assistant_id=assistent_id,
                                                    input=Command(resume=resume_value),
                                                    stream_mode=["updates", "messages"],
                                                    stream_resumable=True,
                                                    checkpoint_during=True
                                                ):
                                                    if mode2=="messages":
                                                        for node_id, msg in chunk2.data.items():
                                                            st.json(msg)
                                                    elif mode2=="updates":
                                                        if node_id not in processed_nodes:
                                                            processed_nodes.add(node_id)
                                                            with st.expander(f"✅ Node Completed: {node_id}"):
                                                                st.json(chunk2.data[node_id])
                                            break  # Exit this primary loop so resumed run starts fresh
                                    elif mode=='updates':
                                        for node in chunk:
                                            if node not in processed_nodes:
                                                processed_nodes.add(node)

                                                if node == 'interrupt':
                                                    st.warning("❗️Interrupt Occur")
                                                    st.write(chunk[node])
                                                else:
                                                    with st.expander(f"🔄 Processing Node: {node}", expanded=True):
                                                            st.write("Processing...")
                                                    
                                                node_containers[node] = st.expander(f"✅ Node Completed: {node}", expanded=False)
                                                with node_containers[node]:
                                                    st.json(chunk[node])

        