from src.workflow.workflow import CreateWorkflow

workflow = CreateWorkflow()
graph = workflow.compile()
if __name__ == "__main__":
    # results = runable.invoke(initial_state())
    # try:
    #     print(results['post_response'])
    # except Exception as e:
    #     print("Error during workflow execution:", str(e))
    #     print(results['error'])
    pass