#!/usr/bin/env python3
"""
MCP Sandbox 客户端连接测试。

测试内容：
1. 连接 Sandbox 服务器（HTTP 或 STDIO）
2. 获取服务器提供的工具列表
3. 执行 Python 代码
4. 浏览器导航并获取内容
5. 创建并检索笔记
6. 搜索 CVE 知识库

使用方法：
    python test_sandbox_client.py --mode http --url http://127.0.0.1:8000
    python test_sandbox_client.py --mode stdio --cmd "python -m mcp.servers.sandbox"
"""

import asyncio
import argparse
import logging
import sys
from typing import Optional

from janus_mcp import MCPClient, MCPClientConfig, MCPClientError

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


class SandboxClientTester:
    """Sandbox 客户端测试器。

    封装测试用例，提供清晰的控制台输出。
    """

    def __init__(self, config: MCPClientConfig) -> None:
        """初始化测试器。

        Args:
            config: 客户端配置对象。
        """
        self.config = config
        self.client: Optional[MCPClient] = None

    async def run_all_tests(self) -> None:
        """运行所有测试用例。"""
        print("\n" + "=" * 60)
        print("MCP Sandbox 客户端连接测试")
        print("=" * 60)

        try:
            # 1. 连接测试
            await self.test_connect()

            # 2. 工具列表测试
            await self.test_list_tools()

            # 3. 代码执行测试
            await self.test_execute_code()

            # 4. 浏览器导航测试
            await self.test_browser_navigate()

            # 5. 笔记功能测试
            await self.test_note_operations()

            # 6. 知识库检索测试
            await self.test_knowledge_search()

            print("\n✅ 所有测试通过！")

        except MCPClientError as e:
            logger.error("MCP 客户端错误: %s", e)
            print(f"\n❌ 测试失败: {e}")
            sys.exit(1)
        except Exception as e:
            logger.exception("未预期的错误")
            print(f"\n❌ 未预期的错误: {e}")
            sys.exit(1)
        finally:
            if self.client:
                await self.client.disconnect()

    async def test_connect(self) -> None:
        """测试 1：连接服务器。"""
        print("\n📡 测试 1: 连接 Sandbox 服务器")
        print("-" * 40)

        self.client = MCPClient(self.config)
        await self.client.connect()
        print(f"✅ 成功连接到服务器 (传输模式: {self.config.transport})")

    async def test_list_tools(self) -> None:
        """测试 2：获取工具列表。"""
        print("\n🔧 测试 2: 获取工具列表")
        print("-" * 40)

        tools = await self.client.list_tools()
        tool_names = [tool.get("name") for tool in tools if tool.get("name")]

        print(f"服务器提供 {len(tools)} 个工具:")
        for i, name in enumerate(tool_names[:10], 1):  # 只显示前10个
            print(f"  {i:2d}. {name}")
        if len(tool_names) > 10:
            print(f"  ... 还有 {len(tool_names) - 10} 个工具")

        # 验证核心工具存在
        expected_tools = ["execute_code", "browser_navigate", "note_create", "knowledge_search_cve"]
        missing = [t for t in expected_tools if t not in tool_names]
        if missing:
            raise MCPClientError(f"缺少核心工具: {missing}")

        print("✅ 核心工具均存在")

    async def test_execute_code(self) -> None:
        """测试 3：执行 Python 代码。"""
        print("\n🐍 测试 3: 执行 Python 代码")
        print("-" * 40)

        # 简单代码执行
        code1 = "print('Hello from Sandbox!')"
        result1 = await self.client.execute_code(code1)
        print(f"执行 '{code1}':")
        print(f"  结果: {result1}")

        # 带状态保持的代码执行
        code2 = "x = 42\nprint(f'x = {x}')"
        result2 = await self.client.execute_code(code2, session_id="test_session")
        print(f"执行状态代码 (session_id=test_session):")
        print(f"  结果: {result2}")

        # 复用会话
        code3 = "print(f'x * 2 = {x * 2}')"
        result3 = await self.client.execute_code(code3, session_id="test_session")
        print(f"复用会话执行 '{code3}':")
        print(f"  结果: {result3}")

        stdout_list = result3.get("result", [])
        stdout_text = "".join(stdout_list)
        if "84" in stdout_text:
            print("✅ 代码执行及会话复用正常")
        else:
            raise MCPClientError(f"代码执行结果异常，预期包含 '84'，实际: {stdout_text}")

    async def test_browser_navigate(self) -> None:
        """测试 4：浏览器导航。"""
        print("\n🌐 测试 4: 浏览器导航")
        print("-" * 40)

        url = "https://example.com"
        nav_result = await self.client.browser_navigate(url)
        print(f"导航到 {url}:")
        print(f"  状态码: {nav_result.get('status_code')}")
        print(f"  标题: {nav_result.get('title')}")

        # 获取内容
        content_result = await self.client.sandbox.browser_get_content()
        text_preview = content_result.get("text", "")[:100]
        print(f"页面内容预览: {text_preview}...")

        if nav_result.get("success"):
            print("✅ 浏览器导航正常")
        else:
            raise MCPClientError("浏览器导航失败")

    async def test_note_operations(self) -> None:
        """测试 5：笔记创建与检索。"""
        print("\n📝 测试 5: 笔记操作")
        print("-" * 40)

        # 创建笔记
        create_result = await self.client.note_create(
            title="测试笔记",
            content="这是一条通过 MCP 客户端创建的测试笔记。",
            tags=["test", "mcp", "sandbox"]
        )
        note_id = create_result.get("note_id")
        print(f"创建笔记: ID = {note_id}")

        # 搜索笔记
        search_result = await self.client.sandbox.note_search("MCP", limit=5)
        found = any(r.get("note_id") == note_id for r in search_result.get("results", []))
        print(f"搜索 'MCP' 是否找到刚创建的笔记: {'是' if found else '否'}")

        if note_id and found:
            print("✅ 笔记创建和检索正常")
        else:
            raise MCPClientError("笔记操作异常")

    async def test_knowledge_search(self) -> None:
        """测试 6：CVE 知识库检索。"""
        print("\n📚 测试 6: CVE 知识库检索")
        print("-" * 40)

        query = "log4j"
        result = await self.client.knowledge_search_cve(query, limit=3)
        count = result.get("count", 0)
        print(f"搜索 '{query}' 找到 {count} 条相关 CVE")

        if count > 0:
            first = result.get("results", [])[0]
            print(f"  第一条: {first.get('cve_id')} - {first.get('severity')}")
            print("✅ 知识库检索正常")
        else:
            # 知识库可能为空，不算失败，仅警告
            print("⚠️ 知识库可能为空，跳过验证")


def parse_args() -> argparse.Namespace:
    """解析命令行参数。"""
    parser = argparse.ArgumentParser(description="MCP Sandbox 客户端测试")
    parser.add_argument(
        "--mode",
        choices=["http", "stdio"],
        default="http",
        help="传输模式 (默认: http)"
    )
    parser.add_argument(
        "--url",
        default="http://127.0.0.1:8000",
        help="HTTP 模式的服务器 URL (默认: http://127.0.0.1:8000)"
    )
    parser.add_argument(
        "--cmd",
        default="python -m janus_mcp.servers.sandbox",
        help="STDIO 模式的服务器启动命令"
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=60.0,
        help="请求超时时间（秒）"
    )
    return parser.parse_args()


def build_config(args: argparse.Namespace) -> MCPClientConfig:
    """根据命令行参数构建配置。

    Args:
        args: 解析后的参数。

    Returns:
        MCPClientConfig: 客户端配置对象。
    """
    if args.mode == "http":
        return MCPClientConfig(
            transport="http",
            server_url=args.url,
            timeout=args.timeout,
            debug=True,
        )
    else:  # stdio
        # 解析命令字符串，拆分为命令和参数
        cmd_parts = args.cmd.split()
        server_command = cmd_parts[0]
        server_args = cmd_parts[1:] if len(cmd_parts) > 1 else []
        return MCPClientConfig(
            transport="stdio",
            server_command=server_command,
            server_args=server_args,
            timeout=args.timeout,
            debug=True,
        )


async def main() -> None:
    """主函数。"""
    args = parse_args()
    config = build_config(args)

    print(f"\n启动测试: 模式={args.mode}, 目标={args.url if args.mode == 'http' else args.cmd}")

    tester = SandboxClientTester(config)
    await tester.run_all_tests()


if __name__ == "__main__":
    asyncio.run(main())