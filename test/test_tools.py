import asyncio
from tools import BrowserTool, TerminalTool, NoteTool, CodeExecutor

async def main():
    # 1. 浏览器工具
    async with BrowserTool() as browser:
        result = await browser.navigate("https://www.baidu.com")
        content = await browser.get_content()
        print(f"页面标题: {content['title']}")

    # 2. 终端工具
    with TerminalTool() as term:
        result = term.execute("dir -a")
        print(f"命令输出: {result['output'][:200]}")

    # 3. 笔记工具
    note_tool = NoteTool()
    note = note_tool.create(
        title="测试笔记",
        content="这是一条测试内容。",
        tags=["test", "demo"]
    )
    print(f"创建笔记: {note.note_id}")

    # 4. 代码执行器
    async with CodeExecutor() as executor:
        result = await executor.execute("print('Hello, World!')")
        print(f"执行结果: {result['stdout']}")

if __name__ == "__main__":
    asyncio.run(main())