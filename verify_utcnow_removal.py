import os
import ast

def check_for_utcnow(directory):
    print(f"Checking {directory} for datetime.utcnow()...")
    for root, _, files in os.walk(directory):
        for file in files:
            if file.endswith(".py"):
                path = os.path.join(root, file)
                try:
                    with open(path, "r", encoding="utf-8") as f:
                        tree = ast.parse(f.read(), filename=path)
                        for node in ast.walk(tree):
                            if isinstance(node, ast.Attribute) and node.attr == 'utcnow':
                                if isinstance(node.value, ast.Name) and node.value.id == 'datetime':
                                    print(f"❌ Found datetime.utcnow() in {path}:{node.lineno}")
                                    return False
                except Exception as e:
                    print(f"⚠️ Could not parse {path}: {e}")
    print(f"✅ No datetime.utcnow() found in {directory}")
    return True

if __name__ == "__main__":
    src_ok = check_for_utcnow("src")
    alembic_ok = check_for_utcnow("alembic/versions")
    
    if src_ok and alembic_ok:
        print("\n🎉 Verification Successful: No datetime.utcnow() found!")
        exit(0)
    else:
        print("\n❌ Verification Failed: Found datetime.utcnow() usage.")
        exit(1)
