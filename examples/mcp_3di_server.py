"""
3Di Warps MCP Server — excerpt from production system.

Exposes deterministic .wrs analysis tools to Claude Code and Claude Desktop
via the Model Context Protocol. All tools read from the WarpsLib2022 module
library on disk — no database or API keys required.

This is the bridge between Claude's full reasoning capability and the
domain-specific deterministic tools. Instead of building a chatbot that
*contains* Claude, this gives Claude direct access to the tools — so you
get multi-file reasoning AND structured analysis in a single conversation.

10 tools + 2 resources. Start: py -3 mcp_3di_server.py
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from fastmcp import FastMCP

from knowledge.module_lookup import (
    lookup_module as _lookup_module,
    list_matches as _list_matches,
    find_module as _find_module,
)
from knowledge.wrs_analysis import analyze_from_name as _analyze_from_name
from knowledge.wrs_eval import evaluate_plystack_from_name as _evaluate_from_name
from knowledge.wrs_graph import (
    get_module_dependencies as _get_deps,
    get_graph_summary as _get_graph_summary,
)
from knowledge.wrs_modifier import modify_from_name as _modify_from_name

mcp = FastMCP("3di-warps")


# ---------------------------------------------------------------------------
# Tools — each wraps an existing Python function with an MCP-visible name
# and a docstring tuned for Claude (tells it WHEN to use, WHAT it returns).
# ---------------------------------------------------------------------------

@mcp.tool(name="lookup_module")
def lookup_module_tool(module_name: str) -> str:
    """Look up a specific .wrs module from the WarpsLib2022 library by name.
    Returns the full parsed content: variables, tape groups, plies, stoppers,
    curves, scarfing definitions, etc.
    """
    return _lookup_module(module_name)


@mcp.tool(name="list_modules")
def list_modules_tool(partial_name: str) -> str:
    """Search for .wrs modules by partial name."""
    matches = _list_matches(partial_name)
    if matches:
        return f"Found {len(matches)} modules:\n" + "\n".join(f"  - {m}" for m in matches)
    return f"No modules found matching '{partial_name}'."


@mcp.tool(name="read_wrs_raw")
def read_wrs_raw_tool(module_name: str) -> str:
    """Read the raw XML content of a .wrs module file. Use this when you need to
    reason about the actual XML structure rather than the parsed summary.
    """
    filepath = _find_module(module_name)
    if not filepath:
        return f"Module '{module_name}' not found."
    with open(filepath, "r", encoding="utf-8") as f:
        return f.read()


@mcp.tool(name="analyze_wrs")
def analyze_wrs_tool(module_name: str, variables: dict | None = None) -> str:
    """Analyze a .wrs plystack for buffer gaps, symmetry issues, and anomalies.
    Optional variables for PFG cross-reference: {"DPI": 12600, "Tier": 760}
    """
    return _analyze_from_name(module_name, variables)


@mcp.tool(name="evaluate_plystack")
def evaluate_plystack_tool(module_name: str, variables: dict) -> str:
    """Evaluate which plies are active for given input variables.
    Returns a numbered table of active plies with materials and widths.
    Example variables: {"DPI": 12600, "IsRAW": 1, "Tier": 760, "IsGenoa": 1}
    """
    return _evaluate_from_name(module_name, variables)


@mcp.tool(name="module_dependencies")
def module_dependencies_tool(module_name: str, direction: str = "both") -> str:
    """Show FileGroup dependency graph as a Mermaid diagram.
    direction: 'downstream', 'upstream', or 'both'.
    """
    return _get_deps(module_name, direction)


@mcp.tool(name="graph_summary")
def graph_summary_tool() -> str:
    """Overview of most-connected modules across all 264 .wrs files."""
    return _get_graph_summary()


@mcp.tool(name="preview_wrs_change")
def preview_wrs_change_tool(module_name: str, operations: list[dict]) -> str:
    """Preview a change to a .wrs module. Returns a unified diff.
    Operations: set_attr, insert_ply, remove_element, set_condition, move_element.
    Example: [{"op": "insert_ply", "after": "OffShr1", "label": "Buf", "width": "0.05"}]
    """
    return _modify_from_name(module_name, operations, dry_run=True)


@mcp.tool(name="apply_wrs_change")
def apply_wrs_change_tool(module_name: str, operations: list[dict]) -> str:
    """Apply a previously previewed change. Auto-backup before writing."""
    return _modify_from_name(module_name, operations, dry_run=False)


# ---------------------------------------------------------------------------
# Resources — domain knowledge Claude can read on demand
# ---------------------------------------------------------------------------

@mcp.resource("warps://context")
def get_context() -> str:
    """3Di Warps domain reference — tape groups, DPI thresholds, PFG specs."""
    context_path = os.path.join(
        os.path.dirname(__file__), "knowledge", "source_data", "Warps", "CONTEXT.md",
    )
    with open(context_path, "r", encoding="utf-8") as f:
        return f.read()


if __name__ == "__main__":
    mcp.run()
