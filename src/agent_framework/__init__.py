"""Autonomous AI Agent Framework."""

from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as _pkg_version

from agent_framework.agent.agent import Agent
from agent_framework.agent.events import AgentCallbackHandler, ConsoleCallbackHandler
from agent_framework.agent.runtime import RunContext, RunState
from agent_framework.auth.api_key import ApiKeyAuth
from agent_framework.auth.base import AuthenticationProvider, NoAuth
from agent_framework.auth.codex_oauth import CodexOAuthAuth, CodexOAuthToken
from agent_framework.config.settings import Settings, get_settings
from agent_framework.exceptions import (
    AgentError,
    AgentFrameworkError,
    AuthenticationError,
    ConfigurationError,
    FallbackExhaustedError,
    LLMProviderError,
    MemoryError,
    OAuthAuthenticationError,
    ProviderAuthenticationError,
    ProviderCapabilityError,
    ProviderTimeoutError,
    ProviderUnavailableError,
    RateLimitError,
    SessionError,
)
from agent_framework.llm.anthropic_provider import AnthropicProvider
from agent_framework.llm.base import LLMProvider
from agent_framework.llm.factory import create_llm_provider, create_provider_runtime
from agent_framework.llm.nvidia_nim_provider import NvidiaNIMProvider
from agent_framework.llm.openai_compatible import OpenAICompatibleProvider
from agent_framework.llm.openai_provider import OpenAIProvider
from agent_framework.llm.runtime import ProviderRuntime
from agent_framework.logging.logger import get_logger, mask_secrets
from agent_framework.memory.base import ConversationMemory
from agent_framework.memory.in_memory import InMemoryConversationMemory
from agent_framework.memory.session import SessionManager
from agent_framework.models.events import AgentRunResult, AgentStep, StreamChunk
from agent_framework.models.message import Message, MessageRole
from agent_framework.models.response import (
    LLMResponse,
    ModelMetadata,
    ProviderCapabilities,
    ProviderTimeouts,
    TokenUsage,
)
from agent_framework.models.tool import (
    ToolArtifact,
    ToolCall,
    ToolCallResult,
    ToolDefinition,
    ToolExecutionContext,
    ToolPolicyDecision,
    ToolRiskLevel,
)
from agent_framework.tools.builtin import (
    WebFetchError,
    WebFetchResult,
    extract_text_from_html,
    register_builtin_tools,
    register_file_tools,
    register_terminal_tools,
    register_web_tools,
)
from agent_framework.tools.executor import ToolExecutor
from agent_framework.tools.policy import (
    AllowAllPolicy,
    DefaultToolPolicy,
    ToolPolicy,
    ToolPolicyError,
)
from agent_framework.tools.registry import ToolRegistry, ToolRegistryError
from agent_framework.tools.schema import generate_tool_definition, python_type_to_json_schema

try:
    __version__ = _pkg_version("agent-framework")
except PackageNotFoundError:  # source checkout without installation
    __version__ = "0.0.0+local"

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
    "FallbackExhaustedError",
    "InMemoryConversationMemory",
    "LLMProvider",
    "LLMProviderError",
    "LLMResponse",
    "MemoryError",
    "Message",
    "MessageRole",
    "ModelMetadata",
    "NoAuth",
    "NvidiaNIMProvider",
    "OAuthAuthenticationError",
    "OpenAICompatibleProvider",
    "OpenAIProvider",
    "ProviderAuthenticationError",
    "ProviderCapabilities",
    "ProviderCapabilityError",
    "ProviderRuntime",
    "ProviderTimeoutError",
    "ProviderTimeouts",
    "ProviderUnavailableError",
    "RateLimitError",
    "RunContext",
    "RunState",
    "SessionError",
    "SessionManager",
    "Settings",
    "StreamChunk",
    "TokenUsage",
    "AllowAllPolicy",
    "DefaultToolPolicy",
    "ToolArtifact",
    "ToolCall",
    "ToolCallResult",
    "ToolDefinition",
    "ToolExecutionContext",
    "ToolExecutor",
    "ToolPolicy",
    "ToolPolicyDecision",
    "ToolPolicyError",
    "ToolRegistry",
    "ToolRegistryError",
    "ToolRiskLevel",
    "WebFetchError",
    "WebFetchResult",
    "extract_text_from_html",
    "register_builtin_tools",
    "register_file_tools",
    "register_terminal_tools",
    "register_web_tools",
    "create_llm_provider",
    "create_provider_runtime",
    "generate_tool_definition",
    "get_logger",
    "get_settings",
    "mask_secrets",
    "python_type_to_json_schema",
]
