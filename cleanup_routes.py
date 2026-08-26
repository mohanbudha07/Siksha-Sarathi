import ast
from pathlib import Path

FILE = Path("app.py")

OLD_FUNCTIONS = {
    "home",
    "register",
    "login",
    "student_dashboard",
    "notes",
    "teacher_dashboard",
    "upload_notes",
    "performance",
    "ai_assistant",
    "ask_ai",
    "predict",
    "quiz",
    "admin_dashboard",
    "logout",
}

source = FILE.read_text()

tree = ast.parse(source)

ranges = []

for node in tree.body:
    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
        if node.name in OLD_FUNCTIONS:
            ranges.append((node.lineno, node.end_lineno, node.name))

lines = source.splitlines()

for start, end, name in sorted(ranges, reverse=True):
    print(f"Removing old route: {name} (lines {start}-{end})")
    del lines[start - 1:end]

FILE.write_text("\n".join(lines) + "\n")

print()
print("Old Jinja route functions removed.")
