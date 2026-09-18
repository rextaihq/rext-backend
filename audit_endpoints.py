import ast
import os
import re


def analyze_endpoints(directory):
    total_endpoints = 0
    refactored_endpoints = 0
    missing_endpoints = []

    route_decorator_regex = re.compile(r"@router\.(get|post|put|patch|delete)\(")

    for root, dirs, files in os.walk(directory):
        if "__pycache__" in root or ".pytest_cache" in root:
            continue

        for file in files:
            if file.endswith(".py") and file != "__init__.py":
                filepath = os.path.join(root, file)
                with open(filepath, "r", encoding="utf-8") as f:
                    content = f.read()

                    try:
                        tree = ast.parse(content)
                        for node in ast.walk(tree):
                            if isinstance(node, ast.AsyncFunctionDef) or isinstance(
                                node, ast.FunctionDef
                            ):
                                for decorator in node.decorator_list:
                                    # Check for router decorators
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
                                            missing_endpoints.append(f"{filepath} ({node.name})")
                    except SyntaxError:
                        # Fallback to regex if AST fails (e.g. for some weird reasons)
                        matches = route_decorator_regex.findall(content)
                        total_endpoints += len(matches)

    return total_endpoints, refactored_endpoints, missing_endpoints


if __name__ == "__main__":
    routes_dir = r"c:\Users\Saad\Documents\GitHub\rext-backend\src\api\routes"
    total, refactored, missing = analyze_endpoints(routes_dir)

    print(f"Total Endpoints: {total}")
    print(f"Refactored (with response_model): {refactored}")
    print(f"Missing refactor: {total - refactored}")
    print("\nFirst 20 missing endpoints:")
    for m in missing[:20]:
        print(f" - {m}")
