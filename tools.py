import os 
from pathlib import Path

# functions
def read_file(filepath):
    with open(filepath, 'r') as f:
        content = f.read()
    return content

def get_file_structure(directory=None):
    
    base = Path(__file__).resolve().parent
    if directory is None:
        target = base
    else:
        target = (base / directory).resolve()
    structure = []

    for root, dirs, files in os.walk(target):
        dirs[:] = [d for d in dirs if d not in (".venv", "__pycache__", ".git")]

        for file in files:
            full_path = Path(root) / file
            relative_path = full_path.relative_to(base)
            structure.append(str(relative_path))

    return "\n".join(structure)

def search_codebase(query, directory=None, max_results=30):
    base = Path(__file__).resolve().parent
    if directory is None:
        target = base
    else:
        target = (base / directory).resolve()

    EXCLUDE_FILES = {
        "main.py", "main_mcp.py", "mcp_server.py", "tools.py",
        "uv.lock", "pyproject.toml", ".gitignore", ".python-version"
    }
    EXCLUDE_EXTENSIONS = {".lock", ".log"}

    matches = []
    truncated = False

    for root, dirs, files in os.walk(target):
        dirs[:] = [d for d in dirs if d not in (".venv", "__pycache__", ".git")]

        for file in files:
            if file in EXCLUDE_FILES or Path(file).suffix in EXCLUDE_EXTENSIONS:
                continue

            full_path = Path(root) / file
            try:
                with open(full_path, "r", encoding="utf-8") as f:
                    for line_number, line in enumerate(f, start=1):
                        if query in line:
                            relative_path = full_path.relative_to(base)
                            matches.append(f"{relative_path}:{line_number}: {line.strip()}")

                            if len(matches) >= max_results:
                                truncated = True
                                break
            except (UnicodeDecodeError, PermissionError):
                continue

            if truncated:
                break
        if truncated:
            break

    if not matches:
        return f"No matches found for '{query}'."

    result = "\n".join(matches)
    if truncated:
        result += f"\n... (truncated at {max_results} matches — use a more specific search term for full results)"
    return result

# if __name__ == "__main__":
#     print(search_codebase("def "))

# if __name__ == "__main__":
#     print(get_file_structure("folder"))

# if __name__ == "__main__":
#     print(read_file("main.py"))