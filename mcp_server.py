from mcp.server.fastmcp import FastMCP
from tools import read_file, get_file_structure, search_codebase
from typing import Optional

mcp = FastMCP("ErrorLens")

@mcp.tool()
def read_file_tool(filepath: str) -> str:
    """Reads and returns the full contents of a file given its path."""
    return read_file(filepath)

@mcp.tool()
def get_file_structure_tool(directory: Optional[str] = None) -> str:
    """Lists all files in the project, optionally scoped to a subfolder."""
    return get_file_structure(directory)

@mcp.tool()
def search_codebase_tool(query: str, directory: Optional[str] = None) -> str:
    """Searches all files for a keyword, returning matching file paths and line numbers."""
    return search_codebase(query, directory)

if __name__ == "__main__":
    mcp.run()