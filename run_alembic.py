import subprocess
import sys

def run_alembic():
    try:
        result = subprocess.run(
            ["alembic", "upgrade", "head"],
            capture_output=True,
            text=True,
            check=True
        )
        print("STDOUT:")
        print(result.stdout)
    except subprocess.CalledProcessError as e:
        print("ERROR OCCURRED")
        print("STDOUT:")
        print(e.stdout)
        print("STDERR:")
        print(e.stderr)

if __name__ == "__main__":
    run_alembic()
