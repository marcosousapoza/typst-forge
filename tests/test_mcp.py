from __future__ import annotations

import asyncio
import os
import sys
import tempfile
import unittest
from pathlib import Path

from mcp import Client
from mcp.client.stdio import StdioServerParameters, stdio_client


ROOT = Path(__file__).resolve().parents[1]


class TypstForgeMcpTest(unittest.TestCase):
    def test_stdio_server_lists_and_calls_tools(self) -> None:
        async def exercise_server() -> None:
            with tempfile.TemporaryDirectory() as tempdir:
                registry = str(Path(tempdir) / "registry")
                env = os.environ.copy()
                env["PYTHONPATH"] = str(ROOT / "src")
                server = StdioServerParameters(
                    command=sys.executable,
                    args=["-m", "typst_forge.mcp"],
                    env=env,
                    cwd=ROOT,
                )
                async with Client(stdio_client(server)) as client:
                    tools = await client.list_tools()
                    names = {tool.name for tool in tools.tools}
                    self.assertEqual(
                        names,
                        {"init_project", "install", "update", "remove", "list", "status", "bump"},
                    )

                    result = await client.call_tool("list", {"registry_root": registry})
                    self.assertFalse(result.is_error)
                    self.assertEqual(result.structured_content["result"], [])

        asyncio.run(exercise_server())
