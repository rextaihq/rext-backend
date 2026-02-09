import os
import re

def audit_routes(directory):
    pattern = re.compile(r'@require_permissions\(.*?\)\s+.*?async def\s+(\w+)\((.*?)\)', re.DOTALL)
    
    for root, dirs, files in os.walk(directory):
        for file in files:
            if file.endswith('.py') and 'routes' in root:
                path = os.path.join(root, file)
                with open(path, 'r', encoding='utf-8') as f:
                    content = f.read()
                    
                matches = re.finditer(r'@require_permissions\((.*?)\)\s+(?:@.*?\s+)*async def\s+(\w+)\((.*?)\)', content, re.DOTALL)
                for match in matches:
                    args_str = match.group(1)
                    func_name = match.group(2)
                    params_str = match.group(3)
                    
                    # Check if workspace_scoped is explicitly False
                    is_global = 'workspace_scoped=False' in args_str
                    
                    # Check if workspace_id is in parameters
                    has_workspace_id = 'workspace_id' in params_str
                    
                    if not is_global and not has_workspace_id:
                        print(f"MISMATCH FOUND: {path}")
                        print(f"  Function: {func_name}")
                        print(f"  Decorator args: {args_str.strip()}")
                        print(f"  Params: {params_str.strip().split(',')[0]}...")
                        print("-" * 20)

if __name__ == "__main__":
    audit_routes('d:/work/rext-backend/src/api/routes')
