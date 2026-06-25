"""
Core Dialectic Agent implementation.

This agent uses tools to gather context from the memory system
and synthesize responses to queries about a peer.
"""

import json
import logging
import re
import time
from collections.abc import AsyncIterator, Callable
from typing import Any, cast

from nanoid import generate as generate_nanoid

from src import crud
from src.config import ConfiguredModelSettings, ReasoningLevel, settings
from src.dependencies import tracked_db
from src.dialectic import prompts
from src.embedding_client import embedding_client
from src.llm import (
    HonchoLLMCallResponse,
    StreamingResponseWithMetadata,
    honcho_llm_call,
)
from src.llm.types import LLMTelemetryContext
from src.schemas import DialecticTraceCreate
from src.telemetry import prometheus_metrics
from src.telemetry.events import (
    DialecticCompletedEvent,
    DialecticPhaseMetrics,
    EmbeddingCallPurpose,
    emit,
)
from src.telemetry.logging import (
    accumulate_metric,
    log_performance_metrics,
    log_token_usage_metrics,
)
from src.telemetry.prometheus.metrics import DialecticComponents, TokenTypes
from src.utils.agent_tools import (
    DIALECTIC_TOOLS,
    DIALECTIC_TOOLS_MINIMAL,
    create_tool_executor,
    search_memory,
)
from src.utils.formatting import format_new_turn_with_timestamp
from src.utils.types import embedding_call_purpose

logger = logging.getLogger(__name__)

_DOC_ID_PATTERN = re.compile(r"\[id:([a-zA-Z0-9_-]+)\]")


def extract_doc_ids_from_messages(messages: list[dict[str, Any]]) -> list[str]:
    """Extract unique observation/document IDs from tool-result message content."""
    doc_ids: list[str] = []
    seen: set[str] = set()
    for message in messages:
        content = message.get("content")
        if not isinstance(content, str):
            continue
        for doc_id in _DOC_ID_PATTERN.findall(content):
            if doc_id not in seen:
                seen.add(doc_id)
                doc_ids.append(doc_id)
    return doc_ids


def _get_dialectic_level_model_config(
    reasoning_level: ReasoningLevel,
) -> ConfiguredModelSettings:
    return settings.DIALECTIC.LEVELS[reasoning_level].MODEL_CONFIG


def _get_dialectic_synthesis_model_config(
    reasoning_level: ReasoningLevel,
) -> ConfiguredModelSettings | None:
    if reasoning_level == "minimal":
        return None
    return settings.DIALECTIC.LEVELS[reasoning_level].SYNTHESIS_MODEL_CONFIG


def _effective_level_max_tokens(reasoning_level: ReasoningLevel) -> int:
    level_settings = settings.DIALECTIC.LEVELS[reasoning_level]
    return (
        level_settings.MAX_OUTPUT_TOKENS
        if level_settings.MAX_OUTPUT_TOKENS is not None
        else settings.DIALECTIC.MAX_OUTPUT_TOKENS
    )


def _effective_model_max_tokens(model_config: ConfiguredModelSettings) -> int:
    return (
        model_config.max_output_tokens
        if model_config.max_output_tokens is not None
        else settings.DIALECTIC.MAX_OUTPUT_TOKENS
    )


class DialecticAgent:
    """
    An agentic dialectic that iteratively gathers context to answer queries.

    Unlike the standard dialectic which pre-gathers all context before a single
    LLM call, this agent uses tools to strategically gather only the context
    needed to answer the specific query.
    """

    def __init__(
        self,
        workspace_name: str,
        session_name: str | None,
        observer: str,
        observed: str,
        observer_peer_card: list[str] | None = None,
        observed_peer_card: list[str] | None = None,
        metric_key: str | None = None,
        reasoning_level: ReasoningLevel = "low",
        custom_rules: str = "",
    ):
        """
        Initialize the dialectic agent.

        Args:
            workspace_name: Workspace identifier
            session_name: Session identifier (may be None for global queries)
            observer: The peer making the query
            observed: The peer being queried about
            observer_peer_card: Biographical information about the observer
            observed_peer_card: Biographical information about the observed peer
            metric_key: Optional key for logging metrics (if provided, agent won't log separately)
            reasoning_level: Level of reasoning to apply
        """
        self.workspace_name: str = workspace_name
        self.session_name: str | None = session_name
        self.observer: str = observer
        self.observed: str = observed
        self.observer_peer_card: list[str] | None = observer_peer_card
        self.observed_peer_card: list[str] | None = observed_peer_card
        self.metric_key: str | None = metric_key
        self.reasoning_level: ReasoningLevel = reasoning_level

        # Initialize conversation history with system prompt
        self.messages: list[dict[str, Any]] = [
            {
                "role": "system",
                "content": prompts.agent_system_prompt(
                    observer,
                    observed,
                    observer_peer_card,
                    observed_peer_card,
                    custom_rules=custom_rules,
                ),
            }
        ]
        self._session_history_initialized: bool = False
        self._prefetched_conclusion_count: int = 0
        self._run_id: str = generate_nanoid()  # Always generate for event correlation

    async def _initialize_session_history(self) -> None:
        """Fetch and inject session history into the system prompt if configured."""
        if self._session_history_initialized:
            return
        self._session_history_initialized = True

        max_tokens = settings.DIALECTIC.SESSION_HISTORY_MAX_TOKENS
        if max_tokens == 0 or not self.session_name:
            return

        # Fetch recent messages up to the token limit
        stmt = await crud.get_messages(
            workspace_name=self.workspace_name,
            session_name=self.session_name,
            token_limit=max_tokens,
            reverse=False,  # chronological order
        )
        async with tracked_db("dialectic.session_history", read_only=True) as db:
            result = await db.execute(stmt)
            messages = result.scalars().all()

            if not messages:
                return

            # Format messages for injection (must access ORM attrs before session closes)
            formatted_messages: list[str] = []
            for msg in messages:
                formatted = format_new_turn_with_timestamp(
                    msg.content, msg.created_at, msg.peer_name
                )
                formatted_messages.append(formatted)

        session_history_section = (
            "\n\n## SESSION HISTORY\n\n"
            "The following is the recent conversation history from this session. "
            "Use this as immediate context when answering the query.\n\n"
            "<session_history>\n"
            f"{chr(10).join(formatted_messages)}\n"
            "</session_history>"
        )

        # Append session history to the system prompt
        self.messages[0]["content"] += session_history_section

    async def _prefetch_relevant_observations(self, query: str) -> str | None:
        """
        Prefetch semantically relevant observations for the query.

        This provides immediate context to the agent without requiring
        tool calls, improving response quality and speed.

        Performs two separate searches to prevent retrieval dilution:
        - Explicit observations (produced by deriver)
        - Higher-level observations (produced in dreaming/background/chat)

        The number of observations fetched depends on reasoning level:
        - minimal: 10 of each type (reduced context for cost savings)
        - all others: 25 of each type

        Args:
            query: The user's query

        Returns:
            Formatted observations string or None if no observations found
        """
        # Use reduced prefetch for minimal reasoning to save tokens
        prefetch_limit = 10 if self.reasoning_level == "minimal" else 25

        try:
            # Pre-compute embedding once for both searches (no DB needed)
            with embedding_call_purpose(
                EmbeddingCallPurpose.DIALECTIC_PREFETCH.value,
                workspace_name=self.workspace_name,
                run_id=self._run_id,
                parent_category="dialectic",
            ):
                query_embedding = await embedding_client.embed(query)

            # search_memory manages its own short-lived DB sessions so no
            # connection is held during external vector-store calls.
            explicit_repr = await search_memory(
                workspace_name=self.workspace_name,
                observer=self.observer,
                observed=self.observed,
                query=query,
                limit=prefetch_limit,
                levels=["explicit"],
                embedding=query_embedding,
            )

            derived_repr = await search_memory(
                workspace_name=self.workspace_name,
                observer=self.observer,
                observed=self.observed,
                query=query,
                limit=prefetch_limit,
                levels=["deductive", "inductive", "contradiction"],
                embedding=query_embedding,
            )

            if explicit_repr.is_empty() and derived_repr.is_empty():
                return None

            # Count prefetched conclusions for telemetry. `Representation.len()`
            # sums all four levels (explicit/deductive/inductive/contradiction);
            # the previous hand-sum dropped inductive + contradiction even
            # though prefetch explicitly requests them.
            self._prefetched_conclusion_count = explicit_repr.len() + derived_repr.len()

            # Format as two separate sections
            parts: list[str] = []

            if not explicit_repr.is_empty():
                parts.append(explicit_repr.format_as_markdown(include_ids=False))

            if not derived_repr.is_empty():
                # Include IDs for derived so agent can use get_reasoning_chain
                parts.append(derived_repr.format_as_markdown(include_ids=True))

            return "\n".join(parts)

        except Exception as e:
            logger.warning(f"Failed to prefetch observations: {e}")
            return None

    async def _prepare_query(
        self, query: str
    ) -> tuple[Callable[[str, dict[str, Any]], Any], str, str | None, float]:
        """
        Prepare common state for answering a query.

        Handles session history initialization, metrics setup, observation prefetching,
        user message construction, and tool executor creation.

        Args:
            query: The question to answer about the peer

        Returns:
            A tuple of (tool_executor, task_name, run_id, start_time)
        """
        await self._initialize_session_history()

        run_id: str | None = None
        if self.metric_key:
            task_name = self.metric_key
        else:
            run_id = generate_nanoid()
            task_name = f"dialectic_chat_{run_id}"
        start_time = time.perf_counter()

        accumulate_metric(
            task_name,
            "context",
            (
                f"workspace: {self.workspace_name}\n"
                f"session: {self.session_name or '(global)'}\n"
                f"observer: {self.observer}\n"
                f"observed: {self.observed}\n"
                f"reasoning_level: {self.reasoning_level}"
            ),
            "blob",
        )
        accumulate_metric(task_name, "query", query, "blob")

        prefetched_observations = await self._prefetch_relevant_observations(query)

        if prefetched_observations:
            user_content = (
                f"Query: {query}\n\n"
                f"## Relevant Observations (prefetched)\n"
                f"The following observations were found to be semantically relevant to your query. "
                f"Use these as primary context. You may still use tools to find additional information if needed.\n\n"
                f"{prefetched_observations}"
            )
            accumulate_metric(
                task_name, "prefetched_observations", prefetched_observations, "blob"
            )
        else:
            user_content = f"Query: {query}"

        self.messages.append({"role": "user", "content": user_content})

        tool_executor: Callable[
            [str, dict[str, Any]], Any
        ] = await create_tool_executor(
            workspace_name=self.workspace_name,
            session_name=self.session_name,
            observer=self.observer,
            observed=self.observed,
            history_token_limit=settings.DIALECTIC.HISTORY_TOKEN_LIMIT,
            run_id=self._run_id,
            agent_type="dialectic",
            parent_category="dialectic",
        )

        return tool_executor, task_name, run_id, start_time

    def _telemetry_context(self) -> LLMTelemetryContext:
        """Build the LLMTelemetryContext shared by answer() and answer_stream().

        Carries the instance's `_run_id` (always set in __init__) + workspace +
        peer identifiers so LLMCallCompletedEvent and 's
        AgentIterationEvent can attribute every per-iteration LLM call back to
        this dialectic invocation.
        """
        return LLMTelemetryContext(
            workspace_name=self.workspace_name,
            call_purpose="dialectic.answer",
            parent_category="dialectic",
            agent_type="dialectic",
            run_id=self._run_id,
            peer_name=self.observed,
        )

    def _get_tools(self) -> list[dict[str, Any]]:
        """Return the tool definitions for this agent."""
        return (
            DIALECTIC_TOOLS_MINIMAL
            if self.reasoning_level == "minimal"
            else DIALECTIC_TOOLS
        )

    def _event_peer_name(self) -> str:
        """Peer name to report on the aggregate DialecticCompletedEvent."""
        return self.observed

    def _performance_trace_name(self) -> str:
        """Trace name used for local performance logs."""
        return "dialectic_chat"

    def _stringify_tool_result_content(self, content: Any) -> str:
        """Convert provider-specific tool result content into stable text."""
        if content is None:
            return ""
        if isinstance(content, str):
            return content

        try:
            if isinstance(content, list):
                rendered_parts: list[str] = []
                for item in cast(list[Any], content):
                    if isinstance(item, dict):
                        item_dict = cast(dict[str, Any], item)
                    else:
                        item_dict = None
                    if item_dict is not None and item_dict.get("type") == "text":
                        text = item_dict.get("text")
                        if isinstance(text, str) and text:
                            rendered_parts.append(text)
                            continue
                    rendered_parts.append(
                        json.dumps(item, ensure_ascii=False, default=str)
                    )
                return "\n".join(part for part in rendered_parts if part)

            if isinstance(content, dict):
                return json.dumps(
                    cast(dict[str, Any], content), ensure_ascii=False, default=str
                )

            return str(cast(object, content))
        except Exception:
            return str(cast(object, content))

    def _build_synthesis_messages(
        self,
        search_messages: list[dict[str, Any]],
        search_response_content: str,
    ) -> list[dict[str, Any]]:
        """Build a toolless synthesis prompt from the search transcript."""
        system_content = ""
        search_context_parts: list[str] = []

        for msg in search_messages:
            role = msg.get("role", "")
            content = msg.get("content", "")

            if role == "system":
                if isinstance(content, str):
                    system_content += content
                elif isinstance(content, list):
                    for block in cast(list[Any], content):
                        if not isinstance(block, dict):
                            continue
                        block_dict = cast(dict[str, Any], block)
                        if block_dict.get("type") == "text":
                            text = block_dict.get("text")
                            if isinstance(text, str):
                                system_content += text
                continue

            if role == "user":
                if isinstance(content, str) and content:
                    search_context_parts.append(f"[USER]: {content}")
                    continue
                if isinstance(content, list):
                    for block in cast(list[Any], content):
                        if not isinstance(block, dict):
                            continue
                        block_dict = cast(dict[str, Any], block)
                        block_type = block_dict.get("type")
                        if block_type == "text":
                            text = block_dict.get("text")
                            if isinstance(text, str) and text:
                                search_context_parts.append(f"[USER]: {text}")
                        elif block_type == "tool_result":
                            tool_id = str(block_dict.get("tool_use_id", "unknown"))
                            result = self._stringify_tool_result_content(
                                block_dict.get("content")
                            )
                            if result:
                                search_context_parts.append(
                                    f"[TOOL RESULT ({tool_id})]: {result}"
                                )
                    continue

            if role == "assistant":
                if isinstance(content, str) and content:
                    search_context_parts.append(f"[ASSISTANT]: {content}")
                elif isinstance(content, list):
                    for block in cast(list[Any], content):
                        if not isinstance(block, dict):
                            continue
                        block_dict = cast(dict[str, Any], block)
                        block_type = block_dict.get("type")
                        if block_type == "text":
                            text = block_dict.get("text")
                            if isinstance(text, str) and text:
                                search_context_parts.append(f"[ASSISTANT]: {text}")
                        elif block_type == "tool_use":
                            name = str(block_dict.get("name", "unknown"))
                            tool_input = block_dict.get("input", {})
                            search_context_parts.append(
                                f"[TOOL CALL: {name}]: "
                                + json.dumps(tool_input, ensure_ascii=False)
                            )

                raw_tool_calls: list[Any] = cast(
                    list[Any], msg.get("tool_calls", []) or []
                )
                for tool_call in raw_tool_calls:
                    if not isinstance(tool_call, dict):
                        continue
                    tool_call_dict = cast(dict[str, Any], tool_call)
                    function = tool_call_dict.get("function", {})
                    if isinstance(function, dict):
                        function_dict = cast(dict[str, Any], function)
                        name = function_dict.get("name", "unknown")
                        args = function_dict.get("arguments", "{}")
                    else:
                        name = tool_call_dict.get("name", "unknown")
                        args = tool_call_dict.get("input", {})
                    search_context_parts.append(f"[TOOL CALL: {name}]: {args}")
                continue

            if role == "tool":
                tool_id = msg.get("tool_call_id", "unknown")
                result = self._stringify_tool_result_content(content)
                if result:
                    search_context_parts.append(f"[TOOL RESULT ({tool_id})]: {result}")

        if not search_context_parts and search_response_content:
            search_context_parts.append(f"[SEARCH RESPONSE]: {search_response_content}")

        messages_out: list[dict[str, Any]] = []
        if system_content:
            messages_out.append({"role": "system", "content": system_content})

        search_context = "\n\n".join(search_context_parts)
        messages_out.append(
            {
                "role": "user",
                "content": (
                    "The following is the search process used to gather "
                    "information:\n\n"
                    f"---\n{search_context}\n---\n\n"
                    "Based on the information gathered above, provide your final "
                    "response to the original query. Be direct, grounded, and "
                    "helpful. Do not call tools."
                ),
            }
        )
        return messages_out

    def _phase_metrics(
        self,
        phase_name: str,
        model_config: ConfiguredModelSettings,
        response: HonchoLLMCallResponse[str],
        *,
        tool_calls_count: int,
    ) -> DialecticPhaseMetrics:
        return DialecticPhaseMetrics(
            phase_name=phase_name,
            transport=model_config.transport,
            model=model_config.model,
            input_tokens=response.input_tokens,
            output_tokens=response.output_tokens,
            cache_read_tokens=response.cache_read_input_tokens or 0,
            cache_creation_tokens=response.cache_creation_input_tokens or 0,
            iterations=max(response.iterations, 1),
            tool_calls_count=tool_calls_count,
            hit_input_token_cap=response.hit_input_token_cap,
        )

    async def _persist_dialectic_trace(
        self,
        *,
        query: str,
        response_content: str,
        input_tokens: int,
        output_tokens: int,
        tool_calls_made: list[dict[str, Any]],
        total_duration_ms: float,
        trace_messages: list[dict[str, Any]] | None = None,
    ) -> None:
        trace = DialecticTraceCreate(
            workspace_name=self.workspace_name,
            session_name=self.session_name,
            observer=self.observer,
            observed=self.observed,
            query=query,
            retrieved_doc_ids=extract_doc_ids_from_messages(
                trace_messages or self.messages
            ),
            tool_calls=tool_calls_made,
            response=response_content,
            reasoning_level=self.reasoning_level,
            total_duration_ms=total_duration_ms,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
        )
        try:
            async with tracked_db("dialectic.trace") as db:
                await crud.create_dialectic_trace(db, trace)
                await db.commit()
        except Exception as e:
            logger.warning("Failed to persist dialectic trace: %s", e)

    async def _log_response_metrics(
        self,
        task_name: str,
        run_id: str | None,
        start_time: float,
        response_content: str,
        input_tokens: int,
        output_tokens: int,
        cache_read_input_tokens: int | None,
        cache_creation_input_tokens: int | None,
        tool_calls_count: int,
        thinking_content: str | None,
        iterations: int,
        hit_input_token_cap: bool = False,
        two_phase_mode: bool = False,
        phases: list[DialecticPhaseMetrics] | None = None,
        query: str | None = None,
        tool_calls_made: list[dict[str, Any]] | None = None,
        trace_messages: list[dict[str, Any]] | None = None,
    ) -> None:
        """
        Log metrics common to both streaming and non-streaming responses.

        Args:
            task_name: Metrics task identifier
            run_id: Run identifier (None if using caller-provided metric_key)
            start_time: Start time from time.perf_counter()
            response_content: The full response text
            input_tokens: Input token count (actual from API)
            output_tokens: Output token count (actual from API)
            cache_read_input_tokens: Cache read tokens (if any)
            cache_creation_input_tokens: Cache creation tokens (if any)
            tool_calls_count: Number of tool calls made
            thinking_content: Thinking trace content (if any)
            iterations: Number of iterations in the tool execution loop
        """
        accumulate_metric(task_name, "tool_calls", tool_calls_count, "count")

        if thinking_content:
            accumulate_metric(task_name, "thinking", thinking_content, "blob")

        log_token_usage_metrics(
            task_name,
            input_tokens,
            output_tokens,
            cache_read_input_tokens or 0,
            cache_creation_input_tokens or 0,
        )
        accumulate_metric(task_name, "response", response_content, "blob")

        elapsed_ms = (time.perf_counter() - start_time) * 1000
        accumulate_metric(task_name, "total_duration", elapsed_ms, "ms")

        if not self.metric_key and run_id is not None:
            log_performance_metrics(self._performance_trace_name(), run_id)

        # Prometheus metrics
        if settings.METRICS.ENABLED:
            prometheus_metrics.record_dialectic_tokens(
                count=input_tokens,
                token_type=TokenTypes.INPUT.value,
                component=DialecticComponents.TOTAL.value,
                reasoning_level=self.reasoning_level,
            )
            prometheus_metrics.record_dialectic_tokens(
                count=output_tokens,
                token_type=TokenTypes.OUTPUT.value,
                component=DialecticComponents.TOTAL.value,
                reasoning_level=self.reasoning_level,
            )

        # Emit telemetry event
        emit(
            DialecticCompletedEvent(
                run_id=self._run_id,
                workspace_name=self.workspace_name,
                peer_name=self._event_peer_name(),
                session_name=self.session_name,
                reasoning_level=self.reasoning_level,
                two_phase_mode=two_phase_mode,
                total_iterations=iterations,
                prefetched_conclusion_count=self._prefetched_conclusion_count,
                tool_calls_count=tool_calls_count,
                total_duration_ms=elapsed_ms,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                cache_read_tokens=cache_read_input_tokens or 0,
                cache_creation_tokens=cache_creation_input_tokens or 0,
                hit_input_token_cap=hit_input_token_cap,
                phases=phases or [],
            )
        )

        if query is not None:
            await self._persist_dialectic_trace(
                query=query,
                response_content=response_content,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                tool_calls_made=tool_calls_made or [],
                total_duration_ms=elapsed_ms,
                trace_messages=trace_messages,
            )

    async def answer(self, query: str) -> str:
        """
        Answer a query about the peer using agentic tool calling.

        The agent will:
        1. Receive the query
        2. Use tools to gather relevant context
        3. Synthesize a response grounded in the gathered context

        Args:
            query: The question to answer about the peer

        Returns:
            The synthesized answer string
        """
        tool_executor, task_name, run_id, start_time = await self._prepare_query(query)

        # Get level-specific settings
        level_settings = settings.DIALECTIC.LEVELS[self.reasoning_level]
        synthesis_model_config = _get_dialectic_synthesis_model_config(
            self.reasoning_level
        )

        tools = self._get_tools()

        if synthesis_model_config is not None:
            search_max_tokens = level_settings.MAX_OUTPUT_TOKENS or 1024
            search_response: HonchoLLMCallResponse[str] = await honcho_llm_call(
                model_config=_get_dialectic_level_model_config(self.reasoning_level),
                prompt="",
                max_tokens=search_max_tokens,
                tools=tools,
                tool_choice=level_settings.TOOL_CHOICE,
                tool_executor=tool_executor,
                max_tool_iterations=level_settings.MAX_TOOL_ITERATIONS,
                messages=self.messages,
                track_name="Dialectic Search",
                max_input_tokens=settings.DIALECTIC.MAX_INPUT_TOKENS,
                trace_name="dialectic_search",
                telemetry=self._telemetry_context(),
            )
            synthesis_messages = self._build_synthesis_messages(
                search_response.messages or self.messages,
                search_response.content,
            )
            synthesis_response: HonchoLLMCallResponse[str] = await honcho_llm_call(
                model_config=synthesis_model_config,
                prompt="",
                max_tokens=_effective_model_max_tokens(synthesis_model_config),
                messages=synthesis_messages,
                track_name="Dialectic Synthesis",
                max_input_tokens=settings.DIALECTIC.MAX_INPUT_TOKENS,
                trace_name="dialectic_synthesis",
                telemetry=self._telemetry_context(),
            )
            phases = [
                self._phase_metrics(
                    "search",
                    _get_dialectic_level_model_config(self.reasoning_level),
                    search_response,
                    tool_calls_count=len(search_response.tool_calls_made),
                ),
                self._phase_metrics(
                    "synthesis",
                    synthesis_model_config,
                    synthesis_response,
                    tool_calls_count=0,
                ),
            ]
            await self._log_response_metrics(
                task_name=task_name,
                run_id=run_id,
                start_time=start_time,
                response_content=synthesis_response.content,
                input_tokens=search_response.input_tokens
                + synthesis_response.input_tokens,
                output_tokens=search_response.output_tokens
                + synthesis_response.output_tokens,
                cache_read_input_tokens=(
                    (search_response.cache_read_input_tokens or 0)
                    + (synthesis_response.cache_read_input_tokens or 0)
                ),
                cache_creation_input_tokens=(
                    (search_response.cache_creation_input_tokens or 0)
                    + (synthesis_response.cache_creation_input_tokens or 0)
                ),
                tool_calls_count=len(search_response.tool_calls_made),
                thinking_content=synthesis_response.thinking_content,
                iterations=search_response.iterations + 1,
                hit_input_token_cap=(
                    search_response.hit_input_token_cap
                    or synthesis_response.hit_input_token_cap
                ),
                two_phase_mode=True,
                phases=phases,
                query=query,
                tool_calls_made=search_response.tool_calls_made,
                trace_messages=search_response.messages or self.messages,
            )
            return synthesis_response.content

        max_tokens = _effective_level_max_tokens(self.reasoning_level)

        response: HonchoLLMCallResponse[str] = await honcho_llm_call(
            model_config=_get_dialectic_level_model_config(self.reasoning_level),
            prompt="",  # Ignored since we pass messages
            max_tokens=max_tokens,
            tools=tools,
            tool_choice=level_settings.TOOL_CHOICE,
            tool_executor=tool_executor,
            max_tool_iterations=level_settings.MAX_TOOL_ITERATIONS,
            messages=self.messages,
            track_name="Dialectic Agent",
            max_input_tokens=settings.DIALECTIC.MAX_INPUT_TOKENS,
            trace_name="dialectic_chat",
            telemetry=self._telemetry_context(),
        )

        await self._log_response_metrics(
            task_name=task_name,
            run_id=run_id,
            start_time=start_time,
            response_content=response.content,
            input_tokens=response.input_tokens,
            output_tokens=response.output_tokens,
            cache_read_input_tokens=response.cache_read_input_tokens,
            cache_creation_input_tokens=response.cache_creation_input_tokens,
            tool_calls_count=len(response.tool_calls_made),
            thinking_content=response.thinking_content,
            iterations=response.iterations,
            hit_input_token_cap=response.hit_input_token_cap,
            query=query,
            tool_calls_made=response.tool_calls_made,
            trace_messages=response.messages or self.messages,
        )

        return response.content

    async def answer_stream(self, query: str) -> AsyncIterator[str]:
        """
        Answer a query about the peer using agentic tool calling, streaming the response.

        The agent will:
        1. Receive the query
        2. Use tools to gather relevant context (non-streaming)
        3. Stream the synthesized response

        Args:
            query: The question to answer about the peer

        Yields:
            Chunks of the response text as they are generated
        """
        tool_executor, task_name, run_id, start_time = await self._prepare_query(query)

        # Get level-specific settings
        level_settings = settings.DIALECTIC.LEVELS[self.reasoning_level]
        synthesis_model_config = _get_dialectic_synthesis_model_config(
            self.reasoning_level
        )

        tools = self._get_tools()

        if synthesis_model_config is not None:
            search_max_tokens = level_settings.MAX_OUTPUT_TOKENS or 1024
            search_response: HonchoLLMCallResponse[str] = await honcho_llm_call(
                model_config=_get_dialectic_level_model_config(self.reasoning_level),
                prompt="",
                max_tokens=search_max_tokens,
                tools=tools,
                tool_choice=level_settings.TOOL_CHOICE,
                tool_executor=tool_executor,
                max_tool_iterations=level_settings.MAX_TOOL_ITERATIONS,
                messages=self.messages,
                track_name="Dialectic Search Stream",
                max_input_tokens=settings.DIALECTIC.MAX_INPUT_TOKENS,
                trace_name="dialectic_search",
                telemetry=self._telemetry_context(),
            )
            synthesis_messages = self._build_synthesis_messages(
                search_response.messages or self.messages,
                search_response.content,
            )
            synthesis_response: HonchoLLMCallResponse[str] = await honcho_llm_call(
                model_config=synthesis_model_config,
                prompt="",
                max_tokens=_effective_model_max_tokens(synthesis_model_config),
                messages=synthesis_messages,
                track_name="Dialectic Synthesis Stream",
                max_input_tokens=settings.DIALECTIC.MAX_INPUT_TOKENS,
                trace_name="dialectic_synthesis",
                telemetry=self._telemetry_context(),
            )
            phases = [
                self._phase_metrics(
                    "search",
                    _get_dialectic_level_model_config(self.reasoning_level),
                    search_response,
                    tool_calls_count=len(search_response.tool_calls_made),
                ),
                self._phase_metrics(
                    "synthesis",
                    synthesis_model_config,
                    synthesis_response,
                    tool_calls_count=0,
                ),
            ]
            await self._log_response_metrics(
                task_name=task_name,
                run_id=run_id,
                start_time=start_time,
                response_content=synthesis_response.content,
                input_tokens=search_response.input_tokens
                + synthesis_response.input_tokens,
                output_tokens=search_response.output_tokens
                + synthesis_response.output_tokens,
                cache_read_input_tokens=(
                    (search_response.cache_read_input_tokens or 0)
                    + (synthesis_response.cache_read_input_tokens or 0)
                ),
                cache_creation_input_tokens=(
                    (search_response.cache_creation_input_tokens or 0)
                    + (synthesis_response.cache_creation_input_tokens or 0)
                ),
                tool_calls_count=len(search_response.tool_calls_made),
                thinking_content=synthesis_response.thinking_content,
                iterations=search_response.iterations + 1,
                hit_input_token_cap=(
                    search_response.hit_input_token_cap
                    or synthesis_response.hit_input_token_cap
                ),
                two_phase_mode=True,
                phases=phases,
                query=query,
                tool_calls_made=search_response.tool_calls_made,
                trace_messages=search_response.messages or self.messages,
            )
            if synthesis_response.content:
                yield synthesis_response.content
            return

        max_tokens = _effective_level_max_tokens(self.reasoning_level)

        response = cast(
            StreamingResponseWithMetadata,
            await honcho_llm_call(
                model_config=_get_dialectic_level_model_config(self.reasoning_level),
                prompt="",  # Ignored since we pass messages
                max_tokens=max_tokens,
                stream=True,
                stream_final_only=True,
                tools=tools,
                tool_choice=level_settings.TOOL_CHOICE,
                tool_executor=tool_executor,
                max_tool_iterations=level_settings.MAX_TOOL_ITERATIONS,
                messages=self.messages,
                track_name="Dialectic Agent Stream",
                max_input_tokens=settings.DIALECTIC.MAX_INPUT_TOKENS,
                trace_name="dialectic_chat",
                telemetry=self._telemetry_context(),
            ),
        )

        accumulated_content: list[str] = []
        async for chunk in response:
            if chunk.content:
                accumulated_content.append(chunk.content)
                yield chunk.content

        await self._log_response_metrics(
            task_name=task_name,
            run_id=run_id,
            start_time=start_time,
            response_content="".join(accumulated_content),
            input_tokens=response.input_tokens,
            output_tokens=response.output_tokens,
            cache_read_input_tokens=response.cache_read_input_tokens,
            cache_creation_input_tokens=response.cache_creation_input_tokens,
            tool_calls_count=len(response.tool_calls_made),
            thinking_content=response.thinking_content,
            iterations=response.iterations,
            hit_input_token_cap=response.hit_input_token_cap,
            query=query,
            tool_calls_made=response.tool_calls_made,
        )
