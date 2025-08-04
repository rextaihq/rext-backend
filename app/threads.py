# thread_tab.py

import streamlit as st
from langgraph.types import Command

def thread_tab(client):
    st.title("🧵 Thread Manager")

    thread_action = st.radio("Select Thread Operation", [
        "Create Thread",
        "Start Run on Thread",
        "Stream Run (with Interrupt Handling)",
        "Get Thread by ID",
        "Delete Thread"
    ])

    if thread_action == "Create Thread":
        st.subheader("🆕 Create a New Thread")
        if st.button("Create Thread"):
            try:
                thread = client.threads.create()
                st.success(f"Thread created! ID: {thread.thread_id}")
                st.json(thread)
            except Exception as e:
                st.error(f"Failed to create thread: {str(e)}")

    elif thread_action == "Stream Run (with Interrupt Handling)":
        st.subheader("📡 Stream Run with Interrupt Support")
        thread_id = st.text_input("Thread ID")
        assistant_id = st.text_input("Assistant ID")

        if st.button("Stream Run") and thread_id and assistant_id:
            try:
                processed_nodes = set()
                node_containers = {}

                for mode, chunk in client.runs.stream(
                    thread_id=thread_id,
                    assistant_id=assistant_id,
                    input={},
                    stream_mode=["updates", "messages"],
                    metadata={"name": "streamed_run"},
                    on_completion="delete",
                    stream_resumable=True,
                    checkpoint_during=True
                ):
                    if mode == "messages":
                        for node_id, msg in chunk.data.items():
                            st.subheader(f"🗨️ Message from {node_id}")
                            st.json(msg)

                    elif mode == "updates":
                        for node_id, node_data in chunk.items():
                            if node_id == "__interrupt__":
                                st.warning("⛔ Interrupt Occurred")
                                st.json(node_data)

                                resume_val = st.text_input("🔁 Resume Input", key="resume_input")
                                if st.button("Resume Run"):
                                    for m2, c2 in client.runs.stream(
                                        thread_id=thread_id,
                                        assistant_id=assistant_id,
                                        input=Command(resume=resume_val),
                                        stream_mode=["updates", "messages"],
                                        stream_resumable=True,
                                        checkpoint_during=True
                                    ):
                                        if m2 == "messages":
                                            for nid, m in c2.data.items():
                                                st.json(m)
                                        elif m2 == "updates":
                                            for nid, d in c2.items():
                                                st.success(f"✅ Resumed Node: {nid}")
                                                st.json(d)
                                return

                            if node_id not in processed_nodes:
                                processed_nodes.add(node_id)
                                st.info(f"📦 Processing Node: {node_id}")
                                st.json(node_data)

            except Exception as e:
                st.error(f"Streaming failed: {str(e)}")

    elif thread_action == "Get Thread by ID":
        st.subheader("🔍 Get Thread Info")
        thread_id = st.text_input("Thread ID")
        if st.button("Fetch Thread") and thread_id:
            try:
                thread = client.threads.get(thread_id)
                st.success("Thread fetched successfully!")
                st.json(thread)
            except Exception as e:
                st.error(f"Fetch failed: {str(e)}")

    elif thread_action == "Delete Thread":
        st.subheader("🗑️ Delete a Thread")
        thread_id = st.text_input("Thread ID to delete")
        if st.button("Delete Thread") and thread_id:
            try:
                client.threads.delete(thread_id=thread_id)
                st.success(f"Thread {thread_id} deleted successfully.")
            except Exception as e:
                st.error(f"Delete failed: {str(e)}")
