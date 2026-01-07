import logging
import sys
import os
from pprint import pprint

# Ensure src is in path
sys.path.append(os.getcwd())

from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import StateGraph
from langgraph.types import Command

from src.flow.engines.content.content_engine import create_content_engine
from src.flow.states.wrext import WREXT

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def test_content_engine():
    print("="*50)
    print("TESTING CONTENT ENGINE")
    print("="*50)

    # 1. Setup Engine with Memory Checkpointer
    # We need memory to handle the interrupt/resume flow
    checkpointer = MemorySaver()
    
    # We need to re-compile the app with the checkpointer to enable thread persistence
    # The create_content_engine function returns a compiled app, so we might need to modify it or 
    # extract the graph. 
    # However, usually we can just pass checkpointer to compile. 
    # Let's inspect create_content_engine in src/flow/engines/content/content_engine.py
    # It returns graph.compile(). We might need to monkeypatch or adjust it, 
    # but for now let's try to see if we can set the checkpointer on the graph before compiling 
    # or if we need to modify the factory function.
    
    # Actually, looking at the code, create_content_engine returns graph.compile() without arguments.
    # To test interrupts properly with state persistence, we really want a checkpointer.
    # But let's try to run it. If it doesn't have a checkpointer, 'interrupt' might just pause execution 
    # and we can resume if we are inside the same process? 
    # LangGraph's `interrupt` usually raises GraphInterrupt.
    # To resume, we usually need a thread_id configuration and a checkpointer.
    
    # Solution: We will recreate the graph locally with a checkpointer for this test
    # by importing the nodes and structure, effectively "unwrapping" create_content_engine 
    # OR we can modify create_content_engine to accept a checkpointer. 
    # Given I can't easily change the function signature without affecting other things potentially,
    # I will modify the create_content_engine slightly to accept an optional checkpointer if the user allows,
    # but for a test script, I'll essentially simulate what create_content_engine does but with a checkpointer.
    
    from src.flow.engines.content.generation.outline import generate_outline
    from src.flow.engines.content.generation.content import generate_content
    from src.flow.engines.content.review.outline import review_outline
    from src.flow.engines.content.review.content.content_review import review_content
    from langgraph.graph import START, END

    graph = StateGraph(WREXT)
    graph.add_node("generate_outline", generate_outline)
    graph.add_node("review_outline", review_outline)
    graph.add_node("generate_content", generate_content)
    graph.add_node("review_content", review_content())

    graph.add_edge(START, "generate_outline")
    graph.add_edge("generate_outline", "review_outline")
    graph.add_edge("review_outline", "generate_content")
    graph.add_edge("generate_content", "review_content")
    graph.add_edge("review_content", END)

    app = graph.compile(checkpointer=checkpointer)

    # 2. Define Input
    thread_config = {"configurable": {"thread_id": "test_thread_1"}}
    
    initial_state = {
        "serp_payload": {
            "query": "benefits of meditation for stress" # Simple query for testing
        },
        "content": {}
    }

    print(f"\n[1] Starting Engine with query: '{initial_state['serp_payload']['query']}'")
    
    # 3. Run until interrupt (Outline Review)
    # We use stream to see what happens, but invoke is also fine.
    # Since we expect an interrupt, we can iterate.
    
    current_state = None
    try:
        # Initial run
        for event in app.stream(initial_state, config=thread_config):
            for key, value in event.items():
                print(f"   -> Node '{key}' completed.")
                if key == "generate_outline":
                    print("      (Outline generated)")
    except Exception as e:
        # In isolated environments without LangGraph API, interrupt might raise specific exceptions
        # But with MemorySaver, it should just stop and save state.
        pass

    # 4. Check status
    snapshot = app.get_state(thread_config)
    print(f"\n[2] Execution Paused at: {snapshot.next}")
    
    # --- DEBUG: Show Outline ---
    current_values = snapshot.values
    if "content" in current_values and "outline" in current_values["content"]:
        print("\n" + "-"*30)
        print("Generated Outline:")
        print("-"*30)
        pprint(current_values["content"]["outline"])
        print("-"*30 + "\n")
    # ---------------------------
    
    if "review_outline" in snapshot.next or not snapshot.next:
        # Depending on how interrupt is implemented, it might pause INSIDE review_outline
        # or after it yields.
        # The 'interrupt' function in LangGraph logic usually halts correctly.
        
        # Let's inspect the payload if available (tasks)
        if snapshot.tasks:
            print("   -> Task interrupted as expected.")
            if snapshot.tasks[0].interrupts:
                 print(f"   -> Interrupt value: {snapshot.tasks[0].interrupts}")
    
    # 5. Resume with User Decision
    print("\n[3] Waiting for user input (approve/reject/comment)...")
    
    user_input = input("Enter decision (approve/reject): ").strip()
    
    if user_input.lower() == "approve":
        resume_payload = Command(resume="approve")
    elif user_input.lower() == "reject":
        reason = input("Enter rejection reason: ")
        resume_payload = Command(resume={"action": "reject", "reason": reason})
    else:
        # Default fallback or custom payload
        resume_payload = Command(resume=user_input)
    
    print(f"   -> Resuming with payload: {resume_payload.resume}")

    final_output = None
    for event in app.stream(resume_payload, config=thread_config):
        for key, value in event.items():
            print(f"   -> Node '{key}' completed.")
            if key == "generate_content":
                print("      (Content generated)")
                # Show partial result if available
                # pprint(value)
            if key == "review_content":
                print("      (Content reviewed)")
            
            # Handle recursive interrupts (e.g. if rejected and loop back)
            if key == "__interrupt__":
                print("   -> ⚠️ Workflow Interrupted Again!")
                snapshot = app.get_state(thread_config)
                print(f"      Tasks: {snapshot.tasks}")
                return # Exit this simplifed test run
            
            final_output = value

    # 6. Verify Results
    print("\n" + "="*50)
    print("VERIFICATION OF CONTENT RESULTS")
    print("="*50)
    
    final_snapshot = app.get_state(thread_config)
    content_state = final_snapshot.values.get("content", {})
    
    if "final_content" in content_state:
        print("✅ Final Content Generated!")
        fc = content_state["final_content"]
        print(f"   Title: {fc.get('title')}")
        print(f"   Word Count: {fc.get('word_count')}")
        print(f"   Body Length: {len(fc.get('body_markdown', ''))} chars")
        
        print("\n" + "-"*30)
        print("Generated Content Body Preview (First 500 chars):")
        print("-"*30)
        print(fc.get('body_markdown', '')[:500] + "...")
        print("-"*30 + "\n")
    else:
        print("❌ Final Content MISSING")
        pprint(content_state)

    if "review" in content_state:
        print("✅ Content Review Present!")
        metrics = content_state["review"].get("readability_metrics", {})
        print(f"   Readability Score (Flesch): {metrics.get('flesch_reading_ease')}")
    else:
        print("❌ Content Review MISSING")

if __name__ == "__main__":
    test_content_engine()
