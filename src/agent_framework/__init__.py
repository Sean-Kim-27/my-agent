"""Autonomous AI Agent Framework."""

from agent_framework.agent.agent import Agent
from agent_framework.agent.events import AgentCallbackHandler, ConsoleCallbackHandler
from agent_framework.auth.api_key import ApiKeyAuth
from agent_framework.auth.base import AuthenticationProvider, NoAuth
from agent_framework.auth.codex_oauth import CodexOAuthAuth, CodexOAuthToken
from agent_framework.config.settings import Settings, get_settings
from agent_framework.exceptions import (
    AgentError,
    AgentFrameworkError,
    AuthenticationError,
    ConfigurationError,
    LLMProviderError,
    MemoryError,
    OAuthAuthenticationError,
    ProviderTimeoutError,
    ProviderUnavailableError,
    RateLimitError,
    SessionError,
)
from agent_framework.llm.anthropic_provider import AnthropicProvider
from agent_framework.llm.base import LLMProvider
from agent_framework.llm.factory import create_llm_provider
from agent_framework.llm.nvidia_nim_provider import NvidiaNIMProvider
from agent_framework.llm.openai_compatible import OpenAICompatibleProvider
from agent_framework.llm.openai_provider import OpenAIProvider
from agent_framework.logging.logger import get_logger, mask_secrets
from agent_framework.memory.base import ConversationMemory
from agent_framework.memory.in_memory import InMemoryConversationMemory
from agent_framework.memory.session import SessionManager
from agent_framework.models.events import AgentRunResult, AgentStep, StreamChunk
from agent_framework.models.message import Message, MessageRole
from agent_framework.models.response import LLMResponse, ProviderCapabilities, TokenUsage
from agent_framework.models.tool import ToolCall, ToolCallResult, ToolDefinition
from agent_framework.tools.executor import ToolExecutor
from agent_framework.tools.registry import ToolRegistry
from agent_framework.tools.schema import generate_tool_definition, python_type_to_json_schema

__version__ = "0.3.0"

__all__ = [
    "Agent",
    "AgentCallbackHandler",
    "AgentError",
    "AgentFrameworkError",
    "AgentRunResult",
    "AgentStep",
    "ApiKeyAuth",
    "AnthropicProvider",
    "AuthenticationError",
    "AuthenticationProvider",
    "CodexOAuthAuth",
    "CodexOAuthToken",
    "ConfigurationError",
    "ConsoleCallbackHandler",
    "ConversationMemory",
    "InMemoryConversationMemory",
    "LLMProvider",
    "LLMProviderError",
    "LLMResponse",
    "MemoryError",
    "Message",
    "MessageRole",
    "NoAuth",
    "NvidiaNIMProvider",
    "OAuthAuthenticationError",
    "OpenAICompatibleProvider",
    "OpenAIProvider",
    "ProviderCapabilities",
    "ProviderTimeoutError",
    "ProviderUnavailableError",
    "RateLimitError",
    "SessionError",
    "SessionManager",
    "Settings",
    "StreamChunk",
    "TokenUsage",
    "ToolCall",
    "ToolCallResult",
    "ToolDefinition",
    "ToolExecutor",
    "ToolRegistry",
    "create_llm_provider",
    "generate_tool_definition",
    "get_logger",
    "get_settings",
    "mask_secrets",
    "python_type_to_json_schema",
]
