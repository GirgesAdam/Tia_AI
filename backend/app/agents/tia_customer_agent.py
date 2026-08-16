from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from langchain_core.messages import AIMessage, BaseMessage, SystemMessage
from langgraph.graph import START, MessagesState, StateGraph
from langgraph.prebuilt import ToolNode, tools_condition

from app.agents.llm_runtime import invoke_model
from app.agents.model_provider import active_model_label, build_chat_model
from app.agents.prompts.customer_service import build_customer_service_system_prompt
from app.agents.tools.clinic_tools import AgentToolContext, build_clinic_tools
from app.core.config import settings


def _extract_text(message: AIMessage) -> str:
    if isinstance(message.content, str):
        return message.content.strip()

    parts: list[str] = []
    if isinstance(message.content, list):
        for block in message.content:
            if isinstance(block, str):
                parts.append(block)
                continue
            if not isinstance(block, dict):
                continue
            text = block.get("text") or block.get("content")
            if isinstance(text, str):
                parts.append(text)

    return "\n".join(part.strip() for part in parts if part.strip()).strip()


def run_tia_customer_agent(
    *,
    history: list[BaseMessage],
    tool_context: AgentToolContext,
    operational_context: str | None = None,
    allowed_tool_names: set[str] | None = None,
) -> tuple[str, str]:
    timezone_name = tool_context.workspace.timezone
    try:
        tz = ZoneInfo(timezone_name)
    except ZoneInfoNotFoundError:
        timezone_name = "Africa/Cairo"
        tz = ZoneInfo(timezone_name)

    system_prompt = build_customer_service_system_prompt(
        clinic_name=tool_context.workspace.name,
        timezone_name=timezone_name,
        local_now=datetime.now(tz),
    )

    internal_messages: list[SystemMessage] = []
    if operational_context:
        internal_messages.append(
            SystemMessage(
                content=(
                    "INTERNAL OPERATIONAL CONTEXT FROM EARLIER TOOL CALLS. "
                    "This is hidden from the customer. Use it only to resolve references "
                    "to options already shown. Never print internal IDs. If the customer "
                    "selects a shown slot, use the exact hidden IDs and start_local value; "
                    "the write tool revalidates before commit.\n"
                    f"{operational_context}"
                )
            )
        )

    all_tools = build_clinic_tools(tool_context)
    if allowed_tool_names is None:
        tools = all_tools
    else:
        tools = [
            tool
            for tool in all_tools
            if tool.name in allowed_tool_names
        ]

    # Safety net: the handoff tool should always be available.
    if not any(tool.name == "escalate_to_human" for tool in tools):
        tools.extend(tool for tool in all_tools if tool.name == "escalate_to_human")

    model = build_chat_model().bind_tools(tools)

    def call_model(state: MessagesState) -> dict[str, list[AIMessage]]:
        response = invoke_model(
            lambda: model.invoke(
                [
                    SystemMessage(content=system_prompt),
                    *internal_messages,
                    *state["messages"],
                ]
            )
        )
        return {"messages": [response]}

    builder = StateGraph(MessagesState)
    builder.add_node("agent", call_model)
    builder.add_node(
        "tools",
        ToolNode(
            tools,
            handle_tool_errors=(ValueError, RuntimeError),
        ),
    )
    builder.add_edge(START, "agent")
    builder.add_conditional_edges("agent", tools_condition)
    builder.add_edge("tools", "agent")
    graph = builder.compile()

    result = graph.invoke(
        {"messages": history},
        config={"recursion_limit": settings.agent_recursion_limit},
    )

    final_message = result["messages"][-1]
    if not isinstance(final_message, AIMessage):
        raise RuntimeError("Agent finished without an AI response.")

    reply = _extract_text(final_message)
    if not reply:
        raise RuntimeError("Agent returned an empty response.")

    return reply, active_model_label()
