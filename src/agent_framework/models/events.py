"""Data models for ReAct step execution traces, lifecycle events, and streaming chunks."""

from typing import Any

from pydantic import BaseModel, Field

from agent_framework.models.response import LLMResponse
from agent_framework.models.tool import ToolCall, ToolCallResult


class AgentStep(BaseModel):
    """Execution state and trace of a single step in a multi-step ReAct loop."""

    step_number: int = Field(..., description="1-indexed step sequence number")
    thought: str | None = Field(default=None, description="Model's internal reasoning or thought text")
    tool_calls: list[ToolCall] = Field(default_factory=list, description="Tool calls generated in this step")
    tool_results: list[ToolCallResult] = Field(default_factory=list, description="Execution results of tool calls")
    is_final: bool = Field(default=False, description="Whether this step concluded the interaction")
    latency_ms: float = Field(default=0.0, description="Step execution duration in milliseconds")


class AgentRunResult(BaseModel):
    """Complete execution trajectory and outcome of an Agent run."""

    content: str = Field(..., description="Final assistant response text")
    session_id: str = Field(..., description="Active session ID")
    steps: list[AgentStep] = Field(default_factory=list, description="Chronological trace of all execution steps")
    total_steps: int = Field(default=1, description="Total number of steps executed")
    total_latency_ms: float = Field(default=0.0, description="Total runtime duration in milliseconds")
    is_max_steps_reached: bool = Field(default=False, description="True if stopped by reaching max_steps limit")
    llm_response: LLMResponse = Field(..., description="Final raw LLM response object")


class StreamChunk(BaseModel):
    """Chunk of streaming token or tool call delta emitted from LLMProvider."""

    content: str = Field(default="", description="Incremental text token delta")
    tool_call_chunk: dict[str, Any] | None = Field(
        default=None,
        description="Incremental tool call information if emitted in chunk",
    )
    is_finished: bool = Field(default=False, description="True if this is the final closing chunk of the stream")
