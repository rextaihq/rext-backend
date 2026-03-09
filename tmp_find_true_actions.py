import os, ast

ROUTES_DIR = r'c:\Users\Saad\Documents\GitHub\rext-backend\src\api\routes'

# ONLY things that truly return no data payload in the 'data' field.
# success() with no data argument results in data=None.
TRUE_ACTION_RETURNS = {
    '{}', 'none', 'true', 'false',
    'success()', 'error()', 'no_content()', 'accepted()',
    '{message}', # message is a top-level field in SuccessResponse, not in data
}

class ActionAudit(ast.NodeVisitor):
    def __init__(self, rel):
        self.rel = rel
        self.actions = []

    def visit_AsyncFunctionDef(self, node): self._check(node)
    def visit_FunctionDef(self, node): self._check(node)

    def _check(self, node):
        is_route = False
        has_rm = False
        for dec in node.decorator_list:
            if isinstance(dec, ast.Call):
                if isinstance(dec.func, ast.Attribute) and getattr(dec.func.value, 'id', '') == 'router':
                    is_route = True
                    for kw in dec.keywords:
                        if kw.arg == 'response_model': has_rm = True
            elif isinstance(dec, ast.Attribute) and getattr(dec.value, 'id', '') == 'router':
                is_route = True
        
        if not is_route or has_rm: return

        returns = []
        for n in ast.walk(node):
            if isinstance(n, ast.Return):
                if n.value is None: returns.append('none')
                elif isinstance(n.value, ast.Dict):
                    if not n.value.keys: returns.append('{}')
                    else:
                        keys = [k.value if isinstance(k, ast.Constant) else '?' for k in n.value.keys if k]
                        returns.append('{' + ', '.join(keys) + '}')
                elif isinstance(n.value, ast.Call):
                    func = n.value.func
                    name = func.attr if isinstance(func, ast.Attribute) else getattr(func, 'id', '')
                    # Check if it passes 'data' to success()
                    has_data_arg = False
                    for arg in n.value.args: has_data_arg = True # simple check
                    for kw in n.value.keywords:
                        if kw.arg == 'data': has_data_arg = True
                    if name == 'success' and not has_data_arg:
                        returns.append('success()')
                    else:
                        returns.append(f'{name}(...)')
                elif isinstance(n.value, ast.Constant): returns.append(str(n.value.value).lower())
                else: returns.append('other')

        if all(r in TRUE_ACTION_RETURNS for r in returns):
            self.actions.append({
                'file': self.rel,
                'line': node.lineno,
                'func': node.name,
                'returns': returns
            })

all_actions = []
for root, _, files in os.walk(ROUTES_DIR):
    for f in files:
        if f.endswith('.py'):
            with open(os.path.join(root, f), 'r', encoding='utf-8') as src:
                try:
                    tree = ast.parse(src.read())
                    v = ActionAudit(os.path.relpath(os.path.join(root, f), ROUTES_DIR))
                    v.visit(tree)
                    all_actions.extend(v.actions)
                except: pass

for a in all_actions:
    print(f"{a['file']}:{a['line']} {a['func']} {a['returns']}")
print(f"Total: {len(all_actions)}")
