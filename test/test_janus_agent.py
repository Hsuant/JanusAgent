#!/usr/bin/env python3
"""JanusAgent 集成测试（独立脚本，无 pytest）。

前提：
1. sandbox 服务已启动（默认 http://127.0.0.1:8000）。
2. 已设置 LLM API 密钥等环境变量（推荐在 .env 中配置）。

运行方式：直接在项目根目录执行 python test_agent_integration.py
"""

import asyncio
import logging
import sys
import time

# 尝试加载 .env（如果 python-dotenv 已安装）
from dotenv import load_dotenv
load_dotenv()

from janus_agent.core.agent import JanusAgent

# ---------- 日志配置 ----------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    stream=sys.stdout,
)
logger = logging.getLogger("integration_test")


# ---------- 测试用例定义 ----------
async def test_connection(agent: JanusAgent) -> bool:
    """1. 基础连接与简单回复。"""
    logger.info("===== 测试 1: 基础连接 =====")
    resp = await agent.run("你好，请简单介绍一下你自己。")
    if not resp.success:
        logger.error("失败: %s", resp.final_output)
        return False
    logger.info("✅ 成功，回复摘要: %s", resp.final_output[:100])
    return True


async def test_note_create_and_read(agent: JanusAgent) -> bool:
    """2. 创建笔记并读取验证。"""
    logger.info("===== 测试 2: 笔记创建与读取 =====")
    title = f"集成测试笔记_{int(time.time())}"
    task = (
        f"请创建一个标题为 '{title}'、内容为'这是集成测试内容'的笔记。"
        "然后搜索该标题的笔记并列出结果。"
    )
    resp = await agent.run(task)
    if not resp.success:
        logger.error("失败: %s", resp.final_output)
        return False
    if title not in resp.final_output:
        logger.error("回复中未找到标题 '%s'", title)
        return False
    logger.info("✅ 笔记创建/读取成功")
    return True


async def test_browser(agent: JanusAgent) -> bool:
    """3. 浏览器工具 - 导航到 blog.devnest.top。"""
    logger.info("===== 测试 3: 浏览器工具 =====")
    task = "使用浏览器打开 https://blog.devnest.top 并告诉我 HTTP 状态码。"
    resp = await agent.run(task)
    if not resp.success:
        logger.error("失败: %s", resp.final_output)
        return False
    if "200" not in resp.final_output:
        logger.error("回复中未包含状态码 200")
        return False
    logger.info("✅ 浏览器工具测试成功")
    return True


async def test_code_execution(agent: JanusAgent) -> bool:
    """4. 代码执行。"""
    logger.info("===== 测试 4: 代码执行 =====")
    code = "print('Hello from Sandbox')"
    task = f"执行以下 Python 代码并返回输出:\n{code}"
    resp = await agent.run(task)
    if not resp.success:
        logger.error("失败: %s", resp.final_output)
        return False
    if "Hello from Sandbox" not in resp.final_output:
        logger.error("未找到预期输出，实际: %s", resp.final_output)
        return False
    logger.info("✅ 代码执行测试成功")
    return True


async def test_consecutive_sessions(agent: JanusAgent) -> bool:
    """5. 连续会话（多轮对话）。"""
    logger.info("===== 测试 5: 连续会话 =====")
    session_id = "integration_test_memory"
    tasks = [
        "记住我的名字是‘测试员’。",
        "我刚才说我的名字是什么？",
        "现在用 Python 计算 2+3 并告诉我结果。",
    ]
    for i, task in enumerate(tasks, 1):
        logger.info("执行任务 %d: %s", i, task)
        resp = await agent.run(task, session_id=session_id)
        if not resp.success:
            logger.error("任务 %d 失败: %s", i, resp.final_output)
            return False
        logger.info("  回复: %s", resp.final_output[:100])
    logger.info("✅ 连续会话测试成功")
    return True


# ---------- 测试运行器 ----------
async def main():
    logger.info("初始化 JanusAgent（连接 sandbox 与 LLM）...")
    agent = JanusAgent(config_dir="../config")
    await agent.initialize()

    # 测试套件：名称与函数
    tests = [
        ("基础连接", test_connection),
        ("笔记创建与读取", test_note_create_and_read),
        ("浏览器工具", test_browser),
        ("代码执行", test_code_execution),
        ("连续会话", test_consecutive_sessions),
    ]

    passed = 0
    failed = 0
    errors = []

    start_time = time.perf_counter()
    for name, test_func in tests:
        test_start = time.perf_counter()
        try:
            ok = await test_func(agent)
        except Exception as exc:
            logger.error("测试 '%s' 发生未捕获异常: %s", name, exc)
            ok = False
        elapsed = time.perf_counter() - test_start

        if ok:
            passed += 1
            logger.info("   ✅ 耗时 %.2f 秒", elapsed)
        else:
            failed += 1
            errors.append(name)
            logger.warning("   ❌ 耗时 %.2f 秒", elapsed)

    total_time = time.perf_counter() - start_time

    # 最终报告
    logger.info("=" * 50)
    logger.info("集成测试完成。总耗时: %.2f 秒", total_time)
    logger.info("通过: %d / 失败: %d", passed, failed)
    if errors:
        logger.error("失败列表: %s", ", ".join(errors))
    else:
        logger.info("🎉 所有测试通过！")

    await agent.close()
    logger.info("Agent 已关闭")

    # 根据结果决定退出码
    sys.exit(0 if failed == 0 else 1)


if __name__ == "__main__":
    asyncio.run(main())