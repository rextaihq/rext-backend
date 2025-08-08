# assistant_tab.py

import streamlit as st

def assistant_tab(client):
    st.title("🤖 Assistant Dashboard")
    
    assistant_action = st.radio("Choose an action", [
        "Create Assistant", 
        "Search Assistant", 
        "Show All Assistants", 
        "Update Assistant", 
        "Delete Assistant",
        "Get Assistant by ID"
    ])

    if assistant_action == "Create Assistant":
        st.subheader("🔧 Create a New Assistant")
        name = st.text_input("Assistant Name")
        description = st.text_area("Assistant Description")
        graph_id = st.text_input("Graph ID", value="agent")
        submit = st.button("Create Assistant")

        if submit and name:
            try:
                assistant = client.assistants.create(
                    graph_id=graph_id,
                    name=name,
                    description=description
                )
                st.success(f"Assistant created successfully! ID: {assistant['assistant_id']}")
                st.json(assistant)
            except Exception as e:
                st.error(f"Failed to create assistant: {str(e)}")

    elif assistant_action == "Search Assistant":
        st.subheader("🔍 Search Assistant by Name")
        search_query = st.text_input("Enter assistant name")
        if st.button("Search") and search_query:
            try:
                results = client.assistants.search(name=search_query)
                if results:
                    for a in results:
                        st.json(a)
                else:
                    st.warning("No assistants found.")
            except Exception as e:
                st.error(f"Search failed: {str(e)}")

    elif assistant_action == "Show All Assistants":
        st.subheader("📋 All Assistants")
        try:
            all_assistants = client.assistants.search()
            st.json(all_assistants)
        except Exception as e:
            st.error(f"Failed to load assistants: {str(e)}")

    elif assistant_action == "Update Assistant":
        st.subheader("✏️ Update Assistant")
        assistant_id = st.text_input("Assistant ID to update")
        new_name = st.text_input("New Name (optional)")
        new_description = st.text_area("New Description (optional)")
        if st.button("Update"):
            try:
                updated = client.assistants.update(
                    assistant_id=assistant_id,
                    name=new_name if new_name else None,
                    description=new_description if new_description else None
                )
                st.success("Assistant updated successfully!")
                st.json(updated)
            except Exception as e:
                st.error(f"Update failed: {str(e)}")

    elif assistant_action == "Delete Assistant":
        st.subheader("❌ Delete Assistant")
        delete_id = st.text_input("Assistant ID to delete")
        if st.button("Delete"):
            try:
                client.assistants.delete(delete_id)
                st.success(f"Assistant {delete_id} deleted.")
            except Exception as e:
                st.error(f"Deletion failed: {str(e)}")

    elif assistant_action == "Get Assistant by ID":
        st.subheader("🔎 Get Assistant by ID")
        id_input = st.text_input("Assistant ID")
        if st.button("Fetch"):
            try:
                assistant = client.assistants.get(id_input)
                st.json(assistant)
            except Exception as e:
                st.error(f"Fetch failed: {str(e)}")
