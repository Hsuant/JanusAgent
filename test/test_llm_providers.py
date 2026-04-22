from dotenv import load_dotenv
load_dotenv()  # 默认加载当前目录的 .env 文件

from janus_agent.llm import LLMLoader, LLMMessage, get_prompt_manager
import asyncio

import os
print("CUSTOMIZE_BASE_URL:", os.getenv("CUSTOMIZE_BASE_URL"))
print("CUSTOMIZE_API_KEY:", os.getenv("CUSTOMIZE_API_KEY"))

async def main():
    # 加载配置
    loader = LLMLoader()
    chain = loader.create_llm_chain()

    # 获取系统提示词
    prompt_mgr = get_prompt_manager()
    system_prompt = prompt_mgr.get_pentest_agent_prompt()

    # 构建消息
    messages = [
        LLMMessage(role="system", content=system_prompt),
        LLMMessage(role="user", content="你是什么模型？"),
    ]

    # 调用 LLM
    response = await chain.generate(messages)
    print(response.content)

# 运行异步函数
if __name__ == "__main__":
    asyncio.run(main())