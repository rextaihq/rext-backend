import ast
import os


def analyze_endpoints(directory):
    total_endpoints = 0
    refactored_endpoints = 0
    missing_by_file = {}

    for root, dirs, files in os.walk(directory):
        if "__pycache__" in root or ".pytest_cache" in root:
            continue

        for file in files:
            if file.endswith(".py") and file != "__init__.py":
                filepath = os.path.join(root, file)
                rel_path = os.path.relpath(filepath, directory)
                with open(filepath, "r", encoding="utf-8") as f:
                    content = f.read()

                    try:
                        tree = ast.parse(content)
                        for node in ast.walk(tree):
                            if isinstance(node, (ast.AsyncFunctionDef, ast.FunctionDef)):
                                for decorator in node.decorator_list:
                                    is_router_call = False
                                    if isinstance(decorator, ast.Call):
                                        if isinstance(decorator.func, ast.Attribute):
                                            if decorator.func.attr in [
                                                "get",
                                                "post",
                                                "put",
                                                "patch",
                                                "delete",
                                            ]:
                                                if (
                                                    isinstance(decorator.func.value, ast.Name)
                                                    and decorator.func.value.id == "router"
                                                ):
                                                    is_router_call = True

                                    if is_router_call:
                                        total_endpoints += 1
                                        has_response_model = any(
                                            keyword.arg == "response_model"
                                            for keyword in decorator.keywords
                                        )
                                        if has_response_model:
                                            refactored_endpoints += 1
                                        else:
                                            if rel_path not in missing_by_file:
                                                missing_by_file[rel_path] = []
                                            missing_by_file[rel_path].append(node.name)
                    except Exception:
                        pass

    return total_endpoints, refactored_endpoints, missing_by_file


if __name__ == "__main__":
    routes_dir = r"c:\Users\Saad\Documents\GitHub\rext-backend\src\api\routes"
    total, refactored, missing = analyze_endpoints(routes_dir)

    print(f"Total: {total}, Refactored: {refactored}, Missing: {total - refactored}")
    print("\nMissing endpoints by file:")
    for file, funcs in missing.items():
        print(f"{file}: {len(funcs)} endpoints")
        for f in funcs:
            print(f"  - {f}")
