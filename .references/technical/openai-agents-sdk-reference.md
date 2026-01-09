# OpenAI Agents SDK - Quick Reference Guide

**Version:** 0.4.2
**Last Updated:** November 2, 2025
**Purpose:** Practical patterns for integrating Agents SDK across automation projects

---

## Configuration Setup

### API Key Loading (Personal Projects)

```python
# Load from paths.py CONFIG
from paths import CONFIG
import os

api_key = CONFIG.get("OPEN_AI_API_KEY")  # Note: underscore in key name
os.environ["OPENAI_API_KEY"] = api_key   # Environment var: no underscore
```

### Imports

```python
from agents import Agent, Runner, function_tool, SQLiteSession
```

---

## Pattern 1: Basic Agent (Stateless)

**Use Case:** Simple queries, no memory needed

```python
from agents import Agent, Runner

agent = Agent(
    name="HelperAgent",
    instructions="You are a helpful assistant. Be concise.",
    model="gpt-4o-mini"  # or "gpt-4o" for more complex tasks
)

result = Runner.run_sync(agent, "Your prompt here")
print(result.final_output)  # String response
```

**When to Use:**

- One-off queries
- Stateless responses
- No conversation history needed
- Simple text generation

---

## Pattern 2: Agent with Tools

**Use Case:** Agent needs to perform actions or access data

```python
from agents import Agent, Runner, function_tool

@function_tool
def get_weather(city: str) -> str:
    """Get current weather for a city."""
    # Your implementation
    return f"Weather in {city}: Sunny, 72°F"

@function_tool
def search_database(query: str) -> dict:
    """Search database for information."""
    # Your implementation
    return {"results": [...]}

agent = Agent(
    name="ToolAgent",
    instructions="Use tools to answer user questions.",
    model="gpt-4o-mini"
)

result = Runner.run_sync(
    agent,
    "What's the weather in Seattle?",
    tools=[get_weather, search_database]
)
print(result.final_output)
```

**Tool Requirements:**

- Use `@function_tool` decorator
- Type hints required on parameters
- Docstring becomes tool description
- Return value automatically passed back to agent

**Agent Behavior:**

- Automatically decides which tools to call
- Can call multiple tools in sequence
- Orchestrates multi-step workflows

---

## Pattern 3: Agent with Memory (Sessions)

**Use Case:** Multi-turn conversations, context retention

```python
from agents import Agent, Runner, SQLiteSession

agent = Agent(
    name="ConversationAgent",
    instructions="Remember previous conversations.",
    model="gpt-4o-mini"
)

# In-memory session (lost on restart)
session = SQLiteSession(
    session_id="user-123",
    db_path=":memory:"  # Default - no persistence
)

# Turn 1
Runner.run_sync(agent, "My name is Jay", session=session)

# Turn 2 - agent remembers
result = Runner.run_sync(agent, "What's my name?", session=session)
print(result.final_output)  # "Your name is Jay!"
```

**Persistent Sessions (Survives Restarts):**

```python
# File-based session
session = SQLiteSession(
    session_id="prep-stage-jay",
    db_path="./sessions/prep_sessions.db"  # Persists to disk
)
```

**Important:**

- Same `session` object must be used across turns
- Each user needs unique `session_id`
- Without session, each call is independent (stateless)

---

## Pattern 4: Streaming Responses

**Use Case:** Real-time text display (teleprompter, chat UI)

```python
import asyncio
from agents import Agent, Runner

async def stream_response():
    agent = Agent(
        name="StreamAgent",
        instructions="Provide detailed explanations.",
        model="gpt-4o-mini"
    )

    result = Runner.run_streamed(agent, "Explain Python")
    full_response = ""

    async for event in result.stream_events():
        # Filter for text delta events
        if event.type == "raw_response_event" and hasattr(event, 'data'):
            if hasattr(event.data, 'delta') and event.data.delta:
                print(event.data.delta, end="", flush=True)
                full_response += event.data.delta

    print()  # Newline after streaming
    return full_response

# Run async function
response = asyncio.run(stream_response())
```

**Key Points:**

- `Runner.run_streamed()` returns `RunResultStreaming`
- MUST use `async for` with `result.stream_events()`
- Text chunks in `event.data.delta` (ResponseTextDeltaEvent)
- Print with `end=''` and `flush=True` for real-time display
- Requires `asyncio.run()` to execute

---

## Pattern 5: Multi-Agent System (Handoffs)

**Use Case:** Complex workflows requiring specialized agents

```python
from agents import Agent, Runner, Handoff

# Specialized agents
summary_agent = Agent(
    name="SummaryAgent",
    instructions="Summarize long text concisely.",
    model="gpt-4o-mini"
)

analysis_agent = Agent(
    name="AnalysisAgent",
    instructions="Perform detailed analysis. Delegate summaries to SummaryAgent.",
    model="gpt-4o",
    handoffs=[Handoff(target_agent=summary_agent)]
)

result = Runner.run_sync(
    analysis_agent,
    "Analyze this text and provide a summary: [long text]"
)
# Agent automatically delegates to SummaryAgent when needed
```

**Note:** Pattern validated in test scripts but not yet used in production

---

## Common Patterns by Use Case

### Chatbot / Conversational Interface

```python
agent = Agent(...)
session = SQLiteSession(session_id=user_id, db_path="./chat_sessions.db")

while True:
    user_input = input("You: ")
    result = Runner.run_sync(agent, user_input, session=session)
    print(f"Bot: {result.final_output}")
```

### Text Generation with Tools

```python
@function_tool
def get_data_from_db(query: str) -> dict:
    """Fetch data from database."""
    return execute_query(query)

agent = Agent(name="Generator", instructions="Use data to generate report.")
result = Runner.run_sync(agent, "Create report on sales", tools=[get_data_from_db])
```

### Real-Time Display (UI Integration)

```python
async def display_streaming_text(prompt: str):
    result = Runner.run_streamed(agent, prompt)
    async for event in result.stream_events():
        if event.type == "raw_response_event" and hasattr(event, 'data'):
            if hasattr(event.data, 'delta') and event.data.delta:
                ui_update_text(event.data.delta)  # Update UI element
```

---

## Migration Strategy (Simplified for Future Use)

### Fast-Track Migration (When Patterns Are Established)

**For simple integrations (basic agents, no complex orchestration):**

1. **Identify Pattern** (5 min)
   - Use decision guide above
   - Match to Pattern A, B, 1, 2, or 5

1. **Copy Template** (10 min)
   - Use production code from this doc
   - Adjust instructions and parameters
   - No need for extensive testing (patterns already validated)

1. **Integration Test** (15 min)
   - Test with real data once
   - Verify outputs acceptable
   - Check error handling

1. **Deploy** (5 min)
   - Replace old implementation
   - Commit to git

**Total time: ~30-45 minutes** (vs. 4-6 hours with full test suite)

---

### Full Testing Required When

- ❗ New pattern not documented here
- ❗ Multi-agent orchestration (handoffs)
- ❗ Complex tool interactions
- ❗ Mission-critical production code
- ❗ Unclear expected behavior

**In these cases:** Follow original test-first protocol (test script → validation → production)

---

## Before Migration

1. ✅ Install: `pip install openai-agents==0.4.2`
1. ✅ Create test script in `.helper_artifacts/`
1. ✅ Validate approach with sample data
1. ✅ Compare outputs with existing implementation

### During Migration

1. Create parallel implementation (don't touch production)
1. Test thoroughly with edge cases
1. Validate outputs match or improve on original
1. Get user confirmation before replacing production code

### After Migration

1. Keep backup of old code (comment out or archive)
1. Update integration points
1. Run full validation suite
1. Monitor for issues in production use

---

## Critical Discoveries (Empirical Testing)

### ❌ Documentation Inaccuracies

- **InMemorySession doesn't exist** → Use `SQLiteSession(db_path=":memory:")`
- **Stream event structure unclear** → Use `event.type=="raw_response_event"` and `event.data.delta`

### ✅ Validated Behaviors

- Agent automatically orchestrates tool calls (no explicit instructions needed)
- Sessions required for memory (without = stateless)
- Streaming requires async/await
- Tools use function docstrings for descriptions

---

## Performance Considerations

**Model Selection:**

- `gpt-4o-mini`: Fast, cheap, good for most tasks ($0.15/1M input tokens)
- `gpt-4o`: More capable, slower, costlier ($2.50/1M input tokens)

**Token Usage:**

- Sessions accumulate history → tokens increase over time
- Monitor session length, clear old conversations if needed
- Use `max_turns` parameter to limit agent loops

**Latency:**

- Streaming adds ~50-200ms overhead (usually negligible)
- Network latency is primary factor
- Consider caching for repeated queries

---

## Quick Decision Guide: Which Pattern to Use?

```text
Need conversation memory across multiple turns?
├─ YES → Pattern A: Session-Based Agent
│         Example: Chatbot, Q&A wizard, multi-step data collection
│         Key: SQLiteSession with persistent session_id
│
└─ NO → Does context change frequently per request?
         ├─ YES → Pattern B: Dynamic Agent Creation
         │         Example: Response generation with varying context
         │         Key: Create fresh agent per request with updated instructions
         │
         └─ NO → Pattern 1: Basic Agent (Stateless)
                   Example: One-off queries, simple text generation
                   Key: No session, same instructions every time

Need real-time text display (streaming)?
├─ Synchronous code (hotkeys, blocking operations)?
│   → Use OpenAI client streaming (NOT Agents SDK streaming)
│   → Pattern B example: openai_client.chat.completions.create(stream=True)
│
└─ Async code (web sockets, async UI)?
    → Use Agents SDK streaming: Runner.run_streamed()
    → Pattern 4 example: async for event in result.stream_events()

Need to access external data or perform actions?
└─ YES → Pattern 2: Agent with Tools
          Define functions with @function_tool decorator
          Agent automatically orchestrates tool calls

Need specialized agents for different tasks?
└─ YES → Pattern 5: Multi-Agent System
          Define handoffs between specialized agents
          Example: SummaryAgent + AnalysisAgent + ExtractionAgent
```

### Real-World Examples

**Scenario: "Generate response based on participant's recent conversation"**
→ **Pattern B** (Dynamic Agent Creation)

- Context changes: Different participant, different conversation each time
- No memory needed: Each response independent
- Streaming needed: Real-time display in UI
- Implementation: Create agent with participant context + conversation history, use OpenAI streaming

**Scenario: "Multi-turn preparation conversation before call"**
→ **Pattern A** (Session-Based Agent)

- Memory needed: Remember previous answers in conversation
- Context extraction: Analyze full conversation at end
- No streaming needed: Turn-by-turn Q&A
- Implementation: SQLiteSession, dual-agent (conversation + extraction)

**Scenario: "Generate one-off summary from text"**
→ **Pattern 1** (Basic Agent)

- No memory: Single input → single output
- No tools: Just text transformation
- No streaming: Final result sufficient
- Implementation: Simple Agent + Runner.run_sync()

**Scenario: "Query database and generate report"**
→ **Pattern 2** (Agent with Tools)

- Tool needed: Database access function
- Agent orchestrates: Decides what queries to run
- Implementation: @function_tool for DB queries, Agent automatically calls them

---

## Testing Checklist

When integrating Agents SDK:

- [ ] Agent creates successfully
- [ ] Basic queries return expected output
- [ ] Tools called correctly when needed
- [ ] Session preserves context across turns
- [ ] Streaming displays text in real-time (if used)
- [ ] Error handling graceful (network issues, API limits)
- [ ] Edge cases handled (empty input, very long prompts)
- [ ] Integration points work (UI, hotkeys, file I/O)

---

## Production-Proven Patterns (STT Transcriber Migrations)

### Pattern A: Session-Based Conversation Agent (Prep Stage)

**Use Case:** Multi-turn Q&A with context extraction

**Implementation:**

```python
from agents import Agent, Runner, SQLiteSession

class PrepStageAgent:
    def __init__(self, openai_client, model):
        self.openai_client = openai_client
        self.model = model

        # Conversation agent (persistent session)
        self.conv_agent = Agent(
            name="PrepStageAgent",
            instructions="""You are a helpful assistant preparing someone for a conversation.
            Ask 3-5 questions to understand context. Be concise.""",
            model=self.model
        )

        # Extraction agent (stateless)
        self.extraction_agent = Agent(
            name="ExtractionAgent",
            instructions="Extract key facts from conversation history. Format as bullet points.",
            model=self.model
        )

    def start_session(self, session_id):
        """Create new session for user"""
        return SQLiteSession(session_id=session_id, db_path=":memory:")

    def chat(self, user_input, session):
        """Single turn of conversation"""
        result = Runner.run_sync(self.conv_agent, user_input, session=session)
        return result.final_output

    def extract_context(self, session):
        """Extract key facts from full conversation"""
        # Use same session to access full history
        result = Runner.run_sync(
            self.extraction_agent,
            "Summarize the key facts from this conversation.",
            session=session
        )
        return result.final_output
```

**Key Discoveries:**

- ✅ Session automatically includes conversation history (no manual tracking needed)
- ✅ Dual-agent pattern: conversational agent + extraction agent
- ✅ Same session used for both agents (extraction sees full history)
- ✅ **Code reduction:** 180+ lines → 93 lines (48%)

---

### Pattern B: Dynamic Agent Creation (Teleprompter)

**Use Case:** Response generation with changing context (no persistence needed)

**Implementation:**

```python
from agents import Agent, Runner
from openai import OpenAI

class TeleprompterResponseAgent:
    def __init__(self, openai_client, model):
        self.openai_client = openai_client
        self.model = model

    def create_response_agent(self, persona_context, conversation_context,
                             quick_notes, mode, last_statement):
        """Create fresh agent with current context"""

        instructions = f"""You are helping craft responses for {persona_context}.

CONVERSATION HISTORY:
{conversation_context}

QUICK NOTES:
{quick_notes}

MODE: {mode}
{"LAST STATEMENT: " + last_statement if last_statement else ""}

Generate a natural, concise response."""

        return Agent(
            name="TeleprompterAgent",
            instructions=instructions,
            model=self.model
        )

    def generate_streaming_response(self, user_input, callback):
        """Generate response with incremental display (SYNCHRONOUS)"""

        # Create agent with current context
        agent = self.create_response_agent(...)

        # Use OpenAI client for synchronous streaming (NOT Agents SDK streaming)
        stream = self.openai_client.chat.completions.create(
            model=self.model,
            messages=[{"role": "user", "content": user_input}],
            stream=True
        )

        full_response = ""
        for chunk in stream:
            if chunk.choices[0].delta.content:
                text = chunk.choices[0].delta.content
                callback(text)  # Real-time UI update
                full_response += text

        return full_response
```

**Key Discoveries:**

- ✅ **Hybrid approach:** Agents SDK for agent creation + OpenAI streaming for display
- ✅ Agents SDK streaming (`Runner.run_streamed`) requires async/await (not suitable for synchronous hotkeys)
- ✅ Dynamic instructions: Create fresh agent per request with updated context
- ✅ Stateless: No session needed (each response independent)
- ✅ Helper functions extracted: filtering, formatting, mode detection
- ✅ **Code reduction:** 150 lines → 40 lines (73%)

---

### Pattern C: Helper Functions for Context Preparation

**Best Practice:** Extract reusable logic from agent code

```python
def filter_substantive_turns(turns, max_turns=10):
    """Remove trivial acknowledgments, keep meaningful dialogue"""

    def is_substantive(text):
        # Filter out "okay", "got it", single-word responses
        text = text.strip().lower()
        if len(text) < 5:
            return False
        if text in ["okay", "got it", "yes", "no", "sure", "alright", "thanks"]:
            return False
        return True

    substantive = [turn for turn in turns if is_substantive(turn['text'])]
    return substantive[-max_turns:]  # Last N turns

def format_conversation(turns):
    """Format turns as readable dialogue"""
    return "\n".join([f"{turn['speaker']}: {turn['text']}" for turn in turns])

def detect_response_mode(turns):
    """Determine if responding to statement or starting conversation"""
    if not turns:
        return "starter", None

    last_turn = turns[-1]
    text = last_turn['text'].strip()

    # Check if last turn needs response
    if text.endswith('?'):  # Question
        return "response", text
    elif len(text) > 20 and not is_acknowledgment(text):  # Statement
        return "response", text
    else:  # Acknowledgment
        return "starter", None
```

**Benefits:**

- ✅ Reusable across multiple agent implementations
- ✅ Testable independently
- ✅ Cleaner agent code (single-responsibility)
- ✅ Easier to maintain and extend

---

## Example Projects Using Agents SDK

**STT Transcriber (Phases 1-3 Complete):**

- ✅ Prep Stage Agent: Session-based conversation preparation (Pattern A)
- ✅ Teleprompter Agent: Streaming response generation (Pattern B)
- ⏳ Context System: Multi-agent architecture (Phase 4 - pending)

**Validated Performance:**

- Prep Stage: Natural conversation flow, 100% extraction accuracy
- Teleprompter: 1.9s response, 1.0s to first chunk, smooth streaming
- Code reduction: 48% (prep), 73% (teleprompter)

**Future Applications:**

- Database query agents with tool access
- Report generation agents with data fetching
- Multi-step workflow automation agents

---

## Advanced Topics

### VS Code Integration via Model Context Protocol (MCP)

#### What is MCP?

Model Context Protocol - Open standard for AI agents to communicate with external tools/applications. Enables custom VS Code Copilot behaviors.

#### Integration Approach

##### Step 1: Create MCP Server

```python
from agents import Agent, MCPServer

agent = Agent(
    name="VSCodeAgent",
    instructions="AI coding assistant with custom tools",
    tools=[create_file, run_tests, format_code]
)

# Expose agent via MCP
server = MCPServer(agent)
server.start()
```

##### Step 2: Connect VS Code

- Configure VS Code Agent Builder to connect to your MCP server
- VS Code sends user messages → Your agent processes → Returns results
- Agent can call tools → VS Code executes them (file creation, etc.)

**Use Cases:**

- Custom coding assistant beyond default Copilot
- Project-specific AI tools (company coding standards, internal APIs)
- Autonomous task completion ("Create Flask app with tests")

**Note:** Advanced integration - requires understanding of MCP protocol and VS Code extension API. Not recommended for immediate use, but valuable for future custom tooling.

---

## Additional Resources

- **Official Docs:** [https://platform.openai.com/docs/guides/agents](https://platform.openai.com/docs/guides/agents)
- **GitHub Repo:** [https://github.com/openai/openai-agents-python](https://github.com/openai/openai-agents-python)
- **Test Scripts:** `01. stt transcriber/.helper_artifacts/test_1*.py`
- **Phase 1 Learnings:** `.helper_artifacts/phase1_learnings_summary.md`
- **Migration Plan:** `.helper_artifacts/MIGRATION_PLAN.md`
- **OpenAI Developer Forum:** [https://community.openai.com](https://community.openai.com)

---

*This reference based on empirical testing with OpenAI Agents SDK 0.4.2*
*Patterns validated through test-first development approach*
*Last updated: November 2, 2025*
