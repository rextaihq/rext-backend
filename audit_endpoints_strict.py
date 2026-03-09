import os
import ast

def analyze_endpoints_strict(directory):
    total_endpoints = 0
    refactored_endpoints = 0
    generic_endpoints = 0 # response_model=dict or missing
    missing_by_file = {}

    for root, dirs, files in os.walk(directory):
        if '__pycache__' in root or '.pytest_cache' in root:
            continue
            
        for file in files:
            if file.endswith('.py') and file != '__init__.py':
                filepath = os.path.join(root, file)
                rel_path = os.path.relpath(filepath, directory)
                with open(filepath, 'r', encoding='utf-8') as f:
                    content = f.read()
                    
                    try:
                        tree = ast.parse(content)
                        for node in ast.walk(tree):
                            if isinstance(node, (ast.AsyncFunctionDef, ast.FunctionDef)):
                                for decorator in node.decorator_list:
                                    is_router_call = False
                                    if isinstance(decorator, ast.Call):
                                        if isinstance(decorator.func, ast.Attribute):
                                            if decorator.func.attr in ['get', 'post', 'put', 'patch', 'delete']:
                                                if isinstance(decorator.func.value, ast.Name) and decorator.func.value.id == 'router':
                                                    is_router_call = True
                                    
                                    if is_router_call:
                                        total_endpoints += 1
                                        response_model_keyword = next((keyword for keyword in decorator.keywords if keyword.arg == 'response_model'), None)
                                        
                                        is_properly_refactored = False
                                        if response_model_keyword:
                                            # Check if it's dict
                                            if isinstance(response_model_keyword.value, ast.Name) and response_model_keyword.value.id == 'dict':
                                                pass
                                            else:
                                                is_properly_refactored = True
                                        
                                        if is_properly_refactored:
                                            refactored_endpoints += 1
                                        else:
                                            generic_endpoints += 1
                                            if rel_path not in missing_by_file:
                                                missing_by_file[rel_path] = []
                                            missing_by_file[rel_path].append(node.name)
                    except Exception:
                        pass

    return total_endpoints, refactored_endpoints, missing_by_file

if __name__ == "__main__":
    routes_dir = r"c:\Users\Saad\Documents\GitHub\rext-backend\src\api\routes"
    total, refactored, missing = analyze_endpoints_strict(routes_dir)
    
    print(f"Total Endpoints: {total}")
    print(f"Properly Refactored (Typed): {refactored}")
    print(f"Generic/Untyped (Missing): {total - refactored}")
    print("\nMissing/Generic endpoints by file:")
    for file, funcs in missing.items():
        print(f"{file}: {len(funcs)} endpoints")
        # for f in funcs:
        #     print(f"  - {f}")
