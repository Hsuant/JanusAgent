"""Agent 图节点实现模块。

提供决策节点（调用 LLM）和工具执行节点（调用工具管理器），
并处理 LLM 响应的多格式解析和工具消息兼容性转换。
"""

import uuid
import json
import re
import logging
from typing import Any, Dict, List, Optional, Tuple

from langchain_core.messages import (
    AIMessage,
    BaseMessage,
    HumanMessage,
    SystemMessage,
    ToolMessage,
)

from janus_agent.core.state import AgentState
from janus_agent.llm.loader import LLMChain
from janus_agent.core.tools.manager import ToolManager

logger = logging.getLogger(__name__)


async def agent_node(
    state: AgentState,
    llm_chain: LLMChain,
    tool_manager: ToolManager,
    system_prompt: str,
) -> Dict[str, Any]:
    """决策节点：调用 LLM 分析当前状态并决定下一步行动。

    功能：
        1. 处理工具消息兼容性（转换 ToolMessage 为 HumanMessage）。
        2. 调用 LLMChain 生成回复。
        3. 解析 LLM 回复（优先原生 tool_calls，其次文本解析）。
        4. 更新消息历史、迭代计数、final_output 等状态。

    Args:
        state: 当前 Agent 状态。
        llm_chain: LLM 调用链实例。
        tool_manager: 工具管理器（预留，本节点可能不直接使用）。
        system_prompt: 系统提示词文本。

    Returns:
        状态更新字典，包含 messages、iteration_count、final_output、observation 等。
    """
    messages: List[BaseMessage] = list(state.get("messages", []))
    iteration_count = state.get("iteration_count", 0) + 1
    max_iterations = state.get("max_iterations", 10)
    final_output = state.get("final_output", "")
    observation = state.get("observation", "")

    # 如果已经生成最终答案，直接跳过
    if final_output:
        return {"iteration_count": iteration_count}

    # 1. 构造调用消息列表
    #    首次调用时，确保系统提示词位于最前
    if not any(isinstance(m, SystemMessage) for m in messages):
        messages.insert(0, SystemMessage(content=system_prompt))

    #    如果有观察结果，追加到消息历史
    if observation:
        messages.append(HumanMessage(content=f"观察结果: {observation}"))

    #    工具消息兼容性转换：将 ToolMessage 合并为 HumanMessage
    messages = _convert_tool_messages_for_llm(messages)

    # 2. 调用 LLM
    try:
        response: AIMessage = await llm_chain.generate(messages)
    except Exception as e:
        logger.error("LLM 调用失败: %s", e)
        error_msg = AIMessage(content=f"LLM 调用失败: {str(e)}")
        return {
            "messages": [error_msg],
            "iteration_count": iteration_count,
            "final_output": str(e),  # 标记为结束
            "observation": "",
        }

    # 3. 解析 LLM 响应，提取工具调用或最终答案
    thought = ""
    tool_calls = []
    parsed_final = ""

    if response.tool_calls:
        # 优先使用模型原生返回的 tool_calls
        for tc in response.tool_calls:
            # tc 可能是 dict 或对象，统一为 dict
            tc_dict = tc if isinstance(tc, dict) else tc.dict()
            tool_calls.append({
                "id": tc_dict.get("id", str(uuid.uuid4())),
                "name": tc_dict.get("name", ""),
                "args": tc_dict.get("args", {}),
            })
    else:
        # 未返回工具调用，尝试从文本内容中解析
        thought, parsed_tool_calls, parsed_final = _parse_llm_response(
            response.content
        )
        if parsed_tool_calls:
            tool_calls = [
                {
                    "id": str(uuid.uuid4()),
                    "name": tc["name"],
                    "args": tc["args"],
                }
                for tc in parsed_tool_calls
            ]
        else:
            # 无工具调用，将解析到的 final_output（或整个内容）作为最终答案
            parsed_final = parsed_final or response.content.strip()

    # 4. 构建返回的状态更新
    updates: Dict[str, Any] = {
        "iteration_count": iteration_count,
        "observation": "",  # 清空观察，等待新的执行结果
    }

    if tool_calls:
        # 存在工具调用：构造带 tool_calls 的 AIMessage
        aimessage = AIMessage(
            content=response.content if response.content else "",
            tool_calls=tool_calls,
        )
        updates["messages"] = [aimessage]
        updates["final_output"] = ""  # 确保不提前结束
        logger.info("决策: 工具调用 -> %s", [tc["name"] for tc in tool_calls])
    else:
        # 无工具调用：视为最终答案
        # 如果迭代数已达上限，强制标记 final_output 结束
        if iteration_count >= max_iterations:
            parsed_final = parsed_final or "已达到最大迭代次数，生成默认回答。"
        aimessage = AIMessage(content=response.content if response.content else "")
        updates["messages"] = [aimessage]
        updates["final_output"] = parsed_final
        logger.info("决策: 最终答案 -> %s", parsed_final[:100])

    return updates


async def tool_node(
    state: AgentState,
    tool_manager: ToolManager,
) -> Dict[str, Any]:
    """执行节点：执行最后一条 AIMessage 中指定的工具调用。

    必须确保被调用时上一条消息包含 tool_calls。

    Args:
        state: 当前 Agent 状态。
        tool_manager: 统一工具管理器实例。

    Returns:
        状态更新字典，包含 ToolMessage 和 observation、tool_results。
    """
    messages = state.get("messages", [])
    if not messages:
        return {"observation": "无消息历史，无法执行工具"}

    last_message = messages[-1]
    if not isinstance(last_message, AIMessage) or not last_message.tool_calls:
        logger.warning("tool_node 被调用但最后一条消息无 tool_calls")
        return {"observation": "无待执行的工具调用"}

    tool_calls = last_message.tool_calls
    tool_messages: List[ToolMessage] = []
    tool_results = state.get("tool_results", [])
    observations = []
    tool_results_batch = []

    for tc in tool_calls:
        # 兼容 dict 和对象格式
        if isinstance(tc, dict):
            tool_name = tc.get("name", "")
            tool_args = tc.get("args", {})
            call_id = tc.get("id", "")
        else:
            tool_name = tc.name
            tool_args = tc.args
            call_id = tc.id

        try:
            result_content = await tool_manager.call_tool(tool_name, tool_args)
            # 构造 ToolMessage
            tool_msg = ToolMessage(
                content=json.dumps({"result": result_content}, ensure_ascii=False),
                tool_call_id=call_id,
            )
            tool_messages.append(tool_msg)
            observations.append(f"{tool_name}: {result_content[:200]}")
            tool_results_batch.append({
                "tool": tool_name,
                "args": tool_args,
                "result": result_content,
                "success": True,
                "call_id": call_id,
            })
        except Exception as e:
            error_str = str(e)
            logger.error("工具执行失败: %s - %s", tool_name, error_str)
            tool_msg = ToolMessage(
                content=json.dumps({"error": error_str}, ensure_ascii=False),
                tool_call_id=call_id,
            )
            tool_messages.append(tool_msg)
            observations.append(f"{tool_name} 失败: {error_str}")
            tool_results_batch.append({
                "tool": tool_name,
                "args": tool_args,
                "error": error_str,
                "success": False,
                "call_id": call_id,
            })

    # 更新 observation 以供下一轮决策注入
    observation = "\n".join(observations)
    return {
        "messages": tool_messages,
        "observation": observation,
        "tool_results": tool_results + tool_results_batch,
    }


# ----------------- 内部辅助函数 -----------------

def _convert_tool_messages_for_llm(messages: List[BaseMessage]) -> List[BaseMessage]:
    """将消息列表中的 ToolMessage 转换为 HumanMessage，以兼容不支持 tool 角色的 LLM。

    将所有散落的 ToolMessage 收集并合并为一条 HumanMessage，放置于列表末尾。

    Args:
        messages: 原始消息列表。

    Returns:
        转换后的消息列表。
    """
    converted = []
    tool_results_text = []

    for msg in messages:
        if isinstance(msg, ToolMessage):
            # 尝试提取可读信息
            try:
                data = json.loads(msg.content)
                result = data.get("result", data)
                tool_name = data.get("tool", "工具")
            except Exception:
                tool_name = "工具"
                result = msg.content
            tool_results_text.append(f"{tool_name} 执行结果：{result}")
        elif isinstance(msg, (SystemMessage, HumanMessage, AIMessage)):
            converted.append(msg)
        else:
            # 未知类型转为 HumanMessage
            converted.append(HumanMessage(content=str(msg)))

    if tool_results_text:
        combined = "\n".join(tool_results_text)
        converted.append(HumanMessage(content=combined))

    return converted


def _parse_llm_response(content: str) -> Tuple[str, List[Dict[str, Any]], str]:
    """解析 LLM 文本响应，提取思考、工具调用和最终答案。

    按优先级尝试 JSON → XML → ReAct 格式，最后取 Final Output。

    Args:
        content: LLM 返回的原始文本。

    Returns:
        (thought, tool_calls, final_output) 三元组。
    """
    # 1. JSON 格式
    tool_calls = _try_parse_json_format(content)
    if tool_calls:
        return "", tool_calls, ""

    # 2. XML 格式
    tool_calls = _try_parse_xml_format(content)
    if tool_calls:
        return "", tool_calls, ""

    # 3. ReAct 格式
    thought, tool_calls, final_output = _try_parse_react_format(content)
    if tool_calls:
        return thought, tool_calls, ""

    # 4. 纯文本 Final Output
    final_output = _extract_final_output(content) or content.strip()
    return thought, [], final_output


def _try_parse_json_format(content: str) -> List[Dict[str, Any]]:
    """从文本中提取 JSON 格式的工具调用。"""
    # 匹配可能的 JSON 块
    json_pattern = r'\{[^{}]*"tool_calls"[^{}]*\}|\{[^{}]*"name"[^{}]*"args"[^{}]*\}'
    matches = re.findall(json_pattern, content, re.DOTALL)
    for match in matches:
        try:
            data = json.loads(match)
        except json.JSONDecodeError:
            continue
        result = []
        if "tool_calls" in data:
            for tc in data["tool_calls"]:
                if "name" in tc:
                    result.append({"name": tc["name"], "args": tc.get("args", {})})
        elif "name" in data:
            result.append({"name": data["name"], "args": data.get("args", {})})
        if result:
            return result
    return []


def _try_parse_xml_format(content: str) -> List[Dict[str, Any]]:
    """解析 <invoke name="..."> 格式。"""
    invoke_pattern = r'<invoke\s+name="([^"]+)"\s*>(.*?)</invoke>'
    matches = re.findall(invoke_pattern, content, re.DOTALL | re.IGNORECASE)
    tool_calls = []
    for tool_name, params_block in matches:
        args = {}
        param_pattern = r'<parameter\s+name="([^"]+)"\s*>(.*?)</parameter>'
        for pname, pval in re.findall(param_pattern, params_block, re.DOTALL):
            try:
                pval = json.loads(pval.strip())
            except json.JSONDecodeError:
                pval = pval.strip()
            args[pname] = pval
        tool_calls.append({"name": tool_name, "args": args})
    return tool_calls


def _try_parse_react_format(content: str) -> Tuple[str, List[Dict[str, Any]], str]:
    """解析 ReAct 格式（Thought/Action/Action Input/Final Output）。"""
    lines = content.split("\n")
    thought = ""
    tool_calls = []
    final_output = ""
    has_action = False

    i = 0
    while i < len(lines):
        line = lines[i].strip()
        if line.startswith("Thought:"):
            thought = line[8:].strip()
        elif line.startswith("Action:"):
            has_action = True
            tool_name = line[7:].strip()
            args = {}
            if i + 1 < len(lines) and lines[i + 1].strip().startswith("Action Input:"):
                input_str = lines[i + 1].strip()[13:].strip()
                try:
                    args = json.loads(input_str)
                except json.JSONDecodeError:
                    args = {"input": input_str}
                i += 1
            tool_calls.append({"name": tool_name, "args": args})
        elif line.startswith("Final Output:"):
            # 支持两种标记，但只有无工具调用时才生效
            final_output = line.split(":", 1)[1].strip()
        i += 1

    if has_action:
        # 存在工具调用时，忽略 Final Output
        return thought, tool_calls, ""
    return thought, [], final_output


def _extract_final_output(content: str) -> str:
    """提取 'Final Output:' 后的文本，若不存在返回空。"""
    for line in content.split("\n"):
        if line.strip().startswith("Final Output:"):
            return line.strip()[13:].strip()
    return ""