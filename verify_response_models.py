import os
import ast

def find_response_mismatches(directory):
    mismatches = {}
    
    for root, dirs, files in os.walk(directory):
        for file in files:
            if file.endswith('.py'):
                filepath = os.path.join(root, file)
                rel_path = os.path.relpath(filepath, directory)
                
                with open(filepath, 'r', encoding='utf-8') as f:
                    content = f.read()
                    
                try:
                    tree = ast.parse(content)
                    has_success_import = any(
                        isinstance(node, ast.ImportFrom) and node.module == 'src.utils.response_utils' and 
                        any(alias.name == 'success' for alias in node.names)
                        for node in tree.body
                    )
                    
                    file_mismatches = []
                    
                    for node in ast.walk(tree):
                        if isinstance(node, (ast.AsyncFunctionDef, ast.FunctionDef)):
                            target_decorator = None
                            for decorator in node.decorator_list:
                                if isinstance(decorator, ast.Call) and \
                                   isinstance(decorator.func, ast.Attribute) and \
                                   decorator.func.attr in ['get', 'post', 'put', 'patch', 'delete']:
                                    
                                    response_model = next((kw for kw in decorator.keywords if kw.arg == 'response_model'), None)
                                    if response_model:
                                        # Check if it contains SuccessResponse
                                        model_str = ast.unparse(response_model.value)
                                        if 'SuccessResponse' in model_str:
                                            target_decorator = decorator
                                            break
                            
                            if target_decorator:
                                # This function should return success(...)
                                # Check all return statements in this function
                                returns = [n for n in ast.walk(node) if isinstance(n, ast.Return)]
                                if not returns:
                                    # Might be a function that doesn't return (error) or yields?
                                    continue
                                
                                for ret in returns:
                                    if ret.value:
                                        ret_str = ast.unparse(ret.value)
                                        allowed_wrappers = ['success(', 'error(', 'created(', 'accepted(', 'paginated_success(']
                                        if not any(wrapper in ret_str for wrapper in allowed_wrappers):
                                            file_mismatches.append({
                                                "function": node.name,
                                                "line": ret.lineno,
                                                "type": "missing_wrapper",
                                                "content": ret_str
                                            })
                                
                                if not has_success_import:
                                    file_mismatches.append({
                                        "function": node.name,
                                        "line": node.lineno,
                                        "type": "missing_import"
                                    })
                    
                    if file_mismatches:
                        mismatches[rel_path] = file_mismatches
                        
                except Exception as e:
                    # print(f"Error parsing {filepath}: {e}")
                    pass
                    
    return mismatches

if __name__ == "__main__":
    routes_dir = r"c:\Users\Saad\Documents\GitHub\rext-backend\src\api\routes"
    mismatches = find_response_mismatches(routes_dir)
    
    for file, ms in mismatches.items():
        print(f"\n{file}:")
        for m in ms:
            if m['type'] == 'missing_wrapper':
                print(f"  - L{m['line']}: Missing success() wrapper in '{m['function']}' returning '{m['content']}'")
            else:
                print(f"  - L{m['line']}: Missing 'success' import for '{m['function']}'")
