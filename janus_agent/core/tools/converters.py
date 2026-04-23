"""工具格式转换器。

提供将 MCP 工具元数据、本地工具定义等转换为 OpenAI function‑calling 格式的纯函数。
模块不持有状态，所有转换均为无副作用映射。
"""

from typing import Any, Dict, List, Optional, Union


def mcp_tool_to_openai(tool: Union[Dict[str, Any], Any]) -> Optional[Dict[str, Any]]:
    """将单个 MCP 工具对象转换为 OpenAI function‑calling 格式。

    MCP 工具通常包含 name、description、inputSchema 字段。本函数兼容 dict
    和对象两种表示，提取必要信息并按 OpenAI 要求的 ``{"type": "function", "function": {...}}`` 输出。

    Args:
        tool: MCP 返回的工具信息（dict 或包含同名属性的对象）。

    Returns:
        OpenAI 格式的工具描述字典；若缺少必要字段则返回 None。
    """
    # 统一提取 name、description、inputSchema
    if isinstance(tool, dict):
        name = tool.get("name")
        description = tool.get("description", "")
        input_schema = tool.get("inputSchema", {})
    elif hasattr(tool, "name"):
        name = getattr(tool, "name", None)
        description = getattr(tool, "description", "")
        input_schema = getattr(tool, "inputSchema", {})
    else:
        return None

    if not name:
        return None

    return {
        "type": "function",
        "function": {
            "name": name,
            "description": description,
            "parameters": input_schema,
        },
    }


def mcp_tools_list_to_openai(tools: List[Any]) -> List[Dict[str, Any]]:
    """将整个 MCP 工具列表转换为 OpenAI 格式的描述列表。

    Args:
        tools: MCP 原始工具列表，元素为 dict 或对象。

    Returns:
        JSON‑safe 的工具描述列表，可直接传递给 LLM。
    """
    converted = []
    for tool in tools:
        openai_tool = mcp_tool_to_openai(tool)
        if openai_tool:
            converted.append(openai_tool)
    return converted


# 常用工具参数名映射（LLM 通用参数 "input" -> 实际参数名）
_INPUT_PARAM_MAP: Dict[str, str] = {
    "browser_navigate": "url",
    "execute_code": "code",
    "note_create": "title",
    "note_search": "query",
    "terminal_run": "command",
    "knowledge_search_cve": "query",
}


def adapt_tool_arguments(tool_name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
    """智能参数适配：将 LLM 通用的 'input' 参数转换为工具预期的参数名。

    某些 LLM 在调用工具时可能将单一参数命名为 'input'，而非工具定义的参数名。
    本函数根据预定义映射表进行替换，使工具调用正确执行。

    Args:
        tool_name: 目标工具名称。
        arguments: 原始参数字典（可能包含 'input' 键）。

    Returns:
        适配后的参数字典，原字典不会被修改。
    """
    # 只在参数只有一个且名为 'input' 且可映射时进行转换
    if len(arguments) == 1 and "input" in arguments:
        real_param = _INPUT_PARAM_MAP.get(tool_name)
        if real_param:
            # 返回新字典，避免副作用
            return {real_param: arguments["input"]}
    return arguments