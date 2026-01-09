# OpenAI Models Comparison for AI Agent Development

**Last Updated:** October 23, 2025

---

## Overview

This document compares OpenAI's available models for use in AI agent applications, specifically for the Speechmatics Transcriber Copilot mode. It covers pricing, capabilities, speed, and recommended use cases.

---

## Model Categories

OpenAI offers three main categories of models:

1. **GPT-4o Series** - Multimodal, optimized models (text, images, audio)
1. **GPT-4 Series** - Legacy high-performance text models
1. **o1 Series** - Advanced reasoning models for complex problem-solving

---

## Detailed Model Comparison

### 1. GPT-4o (October 2024)

**Overview:**

- Latest production model from OpenAI
- Multimodal capabilities (text, images, audio)
- Optimized for speed and cost
- Best balance of quality and performance

**Pricing:**

- **Input tokens:** $2.50 per 1 million tokens
- **Output tokens:** $10.00 per 1 million tokens
- **Cached input tokens:** $1.25 per 1M (50% discount)

**Technical Specifications:**

- **Context window:** 128,000 tokens (~96,000 words or ~400 pages)
- **Max output tokens:** 16,384 tokens
- **Training data:** Up to October 2023
- **Speed:** Fast (optimized for real-time applications)
- **Latency:** ~1-2 seconds for typical responses

**Capabilities:**

- ✅ Excellent text understanding and generation
- ✅ Strong reasoning and problem-solving
- ✅ Multimodal (can process images, audio)
- ✅ Function calling and structured outputs
- ✅ JSON mode for structured data
- ✅ Reproducible outputs (seed parameter)

**Best For:**

- Production AI agent applications
- Real-time conversational AI
- Complex context understanding (large context window)
- Multimodal applications
- Balance of quality and cost

**Use in Copilot Mode:**

- F3 response generation (contextual responses)
- Conversation summary generation
- Context analysis and extraction
- Smart context updates (analyzing conversations for facts)

**Cost Estimate for Copilot Usage:**

- Typical F3 call: 15KB context + 2KB conversation = ~5,000 tokens input
- Response: ~500 tokens output
- **Per F3 press:** $0.0125 input + $0.005 output = **$0.0175**
- **50 F3 presses:** ~$0.88
- **1-hour conversation (10 F3 + 1 summary):** ~$0.26

---

### 2. GPT-4o-mini (July 2024)

**Overview:**

- Smaller, faster, cheaper version of GPT-4o
- Designed for high-volume, cost-sensitive applications
- Still maintains strong performance for most tasks

**Pricing:**

- **Input tokens:** $0.15 per 1 million tokens
- **Output tokens:** $0.60 per 1 million tokens
- **Cached input tokens:** $0.075 per 1M (50% discount)

**💰 Cost Advantage:** 17x cheaper than GPT-4o for input, 17x cheaper for output

**Technical Specifications:**

- **Context window:** 128,000 tokens (same as GPT-4o)
- **Max output tokens:** 16,384 tokens
- **Training data:** Up to October 2023
- **Speed:** Very fast (faster than GPT-4o)
- **Latency:** <1 second for typical responses

**Capabilities:**

- ✅ Good text understanding and generation
- ✅ Solid reasoning (slightly less nuanced than GPT-4o)
- ✅ Function calling and structured outputs
- ✅ JSON mode for structured data
- ✅ Fast processing for real-time applications
- ⚠️ Less sophisticated at complex reasoning vs GPT-4o
- ⚠️ May miss subtle context clues GPT-4o would catch

**Best For:**

- Development and testing (cheap iteration)
- High-volume applications (lots of API calls)
- Simple to moderate complexity tasks
- Quick responses where top-tier quality isn't critical
- Cost-sensitive production deployments

**Use in Copilot Mode:**

- Testing and development (save money while building)
- Transcript polishing (simple cleanup tasks)
- Quick F3 responses for casual conversations
- High-frequency operations where cost matters

**Cost Estimate for Copilot Usage:**

- Same usage as GPT-4o example
- **Per F3 press:** $0.00075 input + $0.0003 output = **$0.00105**
- **50 F3 presses:** ~$0.05
- **1-hour conversation (10 F3 + 1 summary):** ~$0.013

**Quality Comparison:**

- **GPT-4o:** "Ben, I've been working on the ADP integration we discussed last week. The OAuth token refresh is working smoothly now, and I've tested it with the sample data you provided. I think we're ready for you to review the test environment - would next Tuesday work for a demo?"
- **GPT-4o-mini:** "Ben, the ADP integration is progressing well. I've implemented the token refresh and tested it. Ready for you to review when you have time. Does next week work for a demo?"

Both are good, but GPT-4o is more natural and contextually aware.

---

### 3. GPT-4 Turbo (April 2024)

**Overview:**

- Previous generation flagship model
- Now superseded by GPT-4o (which is better AND cheaper)
- Still available but not recommended for new projects

**Pricing:**

- **Input tokens:** $10.00 per 1 million tokens
- **Output tokens:** $30.00 per 1 million tokens

**❌ Cost Disadvantage:** 4x more expensive than GPT-4o with inferior performance

**Technical Specifications:**

- **Context window:** 128,000 tokens
- **Max output tokens:** 4,096 tokens
- **Training data:** Up to April 2023
- **Speed:** Slower than GPT-4o

**Recommendation:**

- **Do not use** - GPT-4o is better in every way
- Only relevant for legacy applications that haven't migrated yet

---

### 4. GPT-4 (Original, March 2023)

**Overview:**

- Original GPT-4 release
- Smaller context window than Turbo/4o
- Completely superseded by newer models

**Pricing:**

- **Input tokens:** $30.00 per 1 million tokens
- **Output tokens:** $60.00 per 1 million tokens

**❌ Cost Disadvantage:** 12x more expensive than GPT-4o

**Technical Specifications:**

- **Context window:** 8,192 tokens (very small)
- **Max output tokens:** 8,192 tokens
- **Training data:** Up to September 2021

**Recommendation:**

- **Do not use** - Outdated and extremely expensive
- Historical reference only

---

### 5. o1-preview (September 2024)

**Overview:**

- Advanced reasoning model designed for complex problem-solving
- Uses "chain of thought" reasoning internally
- Takes longer to respond but provides deeper analysis
- NOT designed for conversational AI

**Pricing:**

- **Input tokens:** $15.00 per 1 million tokens
- **Output tokens:** $60.00 per 1 million tokens

**❌ Cost Disadvantage:** 6x more expensive than GPT-4o, 100x more expensive than GPT-4o-mini

**Technical Specifications:**

- **Context window:** 128,000 tokens
- **Max output tokens:** 32,768 tokens
- **Training data:** Up to October 2023
- **Speed:** Slow (spends time "thinking")
- **Latency:** 5-30 seconds depending on complexity

**Capabilities:**

- ✅ Exceptional reasoning and problem-solving
- ✅ Advanced coding and debugging
- ✅ Complex math and scientific reasoning
- ✅ Multi-step logical analysis
- ❌ NOT conversational (no natural chat flow)
- ❌ Slow response times
- ❌ Expensive

**Best For:**

- Complex coding problems (debugging, architecture)
- Advanced math or scientific analysis
- Multi-step reasoning tasks
- Research and analysis work

**NOT Suitable For:**

- Real-time conversational AI (too slow)
- Quick responses (takes 10+ seconds)
- High-frequency operations (too expensive)

**Use in Copilot Mode:**

- ❌ **Not recommended** for F3 responses (too slow/expensive)
- ❌ **Not recommended** for summaries (overkill)
- ⚠️ **Maybe** for very complex context analysis (if you need deep reasoning)

---

### 6. o1-mini (September 2024)

**Overview:**

- Smaller, faster, cheaper version of o1-preview
- Still focused on reasoning, not conversation
- Better cost efficiency than o1-preview but still expensive

**Pricing:**

- **Input tokens:** $3.00 per 1 million tokens
- **Output tokens:** $12.00 per 1 million tokens

**❌ Cost Disadvantage:** Still 20x more expensive than GPT-4o-mini

**Technical Specifications:**

- **Context window:** 128,000 tokens
- **Max output tokens:** 65,536 tokens
- **Speed:** Faster than o1-preview, still slower than GPT-4o

**Capabilities:**

- ✅ Good reasoning capabilities (STEM focus)
- ✅ Coding and debugging
- ⚠️ Less broad knowledge than o1-preview
- ❌ Still not conversational

**Best For:**

- STEM reasoning tasks at lower cost than o1-preview
- Coding problems that need reasoning
- Cost-sensitive reasoning tasks

**Use in Copilot Mode:**

- ❌ **Not recommended** - Still overkill and too expensive

---

## Direct Comparison Table

| Model | Input $/1M | Output $/1M | Context | Speed | Use Case |
|-------|-----------|-------------|---------|-------|----------|
| **GPT-4o** | $2.50 | $10.00 | 128K | Fast | **Production conversational AI** ✅ |
| **GPT-4o-mini** | $0.15 | $0.60 | 128K | Very Fast | **Cost-sensitive / Testing** ✅ |
| GPT-4 Turbo | $10.00 | $30.00 | 128K | Medium | Legacy (don't use) ❌ |
| GPT-4 | $30.00 | $60.00 | 8K | Slow | Legacy (don't use) ❌ |
| o1-preview | $15.00 | $60.00 | 128K | Very Slow | Complex reasoning only |
| o1-mini | $3.00 | $12.00 | 128K | Slow | STEM reasoning only |

---

## Cost Comparison for Copilot Use Case

**Scenario:** 1-hour conversation with 10 F3 responses + 1 summary

| Model | Per F3 | 10 F3 | Summary | Total | Monthly (20 hrs) |
|-------|--------|-------|---------|-------|------------------|
| **GPT-4o-mini** | $0.001 | $0.010 | $0.003 | **$0.013** | **$0.26** ✅ |
| **GPT-4o** | $0.018 | $0.180 | $0.080 | **$0.260** | **$5.20** |
| GPT-4 Turbo | $0.070 | $0.700 | $0.300 | **$1.000** | **$20.00** ❌ |
| o1-preview | $0.105 | $1.050 | $0.450 | **$1.500** | **$30.00** ❌ |

---

## Recommendations for Speechmatics Copilot

### Development Phase

**Use GPT-4o-mini:**

- Super cheap testing and iteration
- Fast responses for development workflow
- Good enough quality for building features
- **Cost:** ~$0.26/month for 20 hours of testing

### Production Phase - Hybrid Approach

**For important client conversations (Ben Price, Westons):**

- Use **GPT-4o** for F3 responses (better quality, worth the cost)
- Use **GPT-4o** for smart context updates (accuracy matters)
- **Cost:** ~$5.20/month for 20 hours

**For casual/practice conversations:**

- Use **GPT-4o-mini** (sufficient quality, save money)
- **Cost:** ~$0.26/month for 20 hours

**Implementation:**

```text
When loading context:
- If participant == "Ben Price" or "Westons" → Use GPT-4o
- Else → Use GPT-4o-mini
```

### Specific Use Cases

| Task | Recommended Model | Why |
|------|------------------|-----|
| F3 responses (client calls) | GPT-4o | Quality matters for client interactions |
| F3 responses (casual/practice) | GPT-4o-mini | Good enough, save money |
| Transcript polishing | GPT-4o-mini | Simple cleanup, doesn't need GPT-4o |
| Conversation summaries | GPT-4o-mini | Extracting facts is straightforward |
| Smart context updates | GPT-4o | Accuracy critical for documentation |
| Testing/development | GPT-4o-mini | Cheap iteration |

---

## Model Selection Logic

### When to Use GPT-4o

✅ Client conversations (Ben Price, important relationships)
✅ Complex context analysis (smart updates)
✅ When quality/nuance matters more than cost
✅ Production environment with paying clients
✅ Situations where mistakes are costly

### When to Use GPT-4o-mini

✅ Development and testing
✅ Casual practice conversations
✅ Simple tasks (transcript cleanup)
✅ High-frequency operations where cost adds up
✅ When "good enough" is sufficient

### When NOT to Use o1 Models

❌ Real-time conversational AI (too slow)
❌ Quick response needs (takes 10+ seconds)
❌ Cost-sensitive applications (very expensive)
❌ Simple tasks (massive overkill)

---

## Context Window Considerations

**What is a token?**

- ~4 characters or ~0.75 words
- 1,000 tokens ≈ 750 words or ~3 pages

**Copilot Context Sizes:**

- Persona (persona.md): ~7KB = ~2,000 tokens
- Client context (westons.md): ~7.5KB = ~2,000 tokens
- Conversation history (10 summaries): ~5KB = ~1,500 tokens
- Current conversation (10 turns): ~2KB = ~500 tokens
- **Total input per F3 call:** ~6,000 tokens
- **Output response:** ~500 tokens

**All models (GPT-4o, GPT-4o-mini) have 128K context window:**

- Can handle 20x your current context size
- No risk of running out of space
- Can scale to much larger contexts if needed

---

## Response Quality Comparison

### Example: F3 Response Generation

**Prompt:** Ben says "How's the payroll module coming along?"

**GPT-4o Response:**
> "Ben, great timing on asking about payroll. I just finished testing the ADP integration yesterday and it's working really well. The CSV export format matches exactly what we reviewed last week, and I've validated the overtime calculations against your sample data - everything checks out perfectly.
>
> I think we're ready for you to review the test environment. Would you have 30 minutes next Tuesday to walk through it together? I can show you the full workflow from timesheet parsing to ADP-ready output, and we can discuss any adjustments before we go live.
>
> Also, I wanted to mention - while testing, I noticed a potential improvement for how we handle worker comp calculations that could save you time on month-end reporting. I'll show you when we meet."

**GPT-4o-mini Response:**
> "The payroll module is coming along well, Ben. I've completed the ADP integration and tested the CSV export format. The overtime calculations are working correctly based on your sample data.
>
> I think we're ready for you to review it. Would next week work for a demo? I can walk you through the workflow and we can make any adjustments before going live."

**Analysis:**

- Both are accurate and professional
- GPT-4o has more natural flow and personality
- GPT-4o catches subtle opportunities (the worker comp improvement)
- GPT-4o references past conversations more naturally
- GPT-4o-mini is direct and efficient but less engaging

**For client relationships:** GPT-4o's quality edge is worth the cost
**For casual use:** GPT-4o-mini is perfectly adequate

---

## Caching Benefits (Advanced)

Both GPT-4o and GPT-4o-mini support **prompt caching** (50% discount on cached input):

**How it works:**

- If you send the same context repeatedly (persona.md + westons.md)
- OpenAI caches it for 5-10 minutes
- Subsequent calls get 50% off input token cost

**Copilot benefit:**

- During active conversation, context stays mostly the same
- Multiple F3 presses within 10 minutes get discount
- Effective input cost: $1.25/1M for GPT-4o, $0.075/1M for GPT-4o-mini

**Real cost with caching (10 F3 in one hour):**

- First F3: Full price ($0.0125 input)
- Next 9 F3: Cached price ($0.00625 input each)
- **Savings:** ~40% on input tokens

---

## Future Considerations

### Upcoming Models (Rumors)

- **GPT-5** - Expected 2025, likely significant quality jump
- **Cheaper models** - OpenAI tends to reduce prices over time
- **Specialized models** - Task-specific models may emerge

### Long-Term Strategy

- Build with GPT-4o-mini now (cheap development)
- Switch to GPT-4o for production (or newer models when available)
- Design system to easily swap models (configuration-based)
- Monitor OpenAI announcements for better/cheaper options

---

## Implementation Notes

**Current System:**
Your Copilot mode likely has hardcoded model selection. Recommend adding:

```python
# In config.json
{
  "OPENAI_MODEL_F3_RESPONSES": "gpt-4o-mini",
  "OPENAI_MODEL_SUMMARIES": "gpt-4o-mini",
  "OPENAI_MODEL_CONTEXT_UPDATES": "gpt-4o",
  "USE_SMART_MODEL_SELECTION": true,  # Switch based on participant
  "PRIORITY_PARTICIPANTS": ["Ben Price", "Westons"]  # Use GPT-4o for these
}
```

**Smart Selection Logic:**

```text
If participant in PRIORITY_PARTICIPANTS:
    model = "gpt-4o"
Else:
    model = "gpt-4o-mini"
```

---

## Summary & Recommendation

**For Speechmatics Copilot:**

1. **Development:** Use GPT-4o-mini exclusively (cheap testing)
1. **Production:** Hybrid approach
   - GPT-4o for important client conversations
   - GPT-4o-mini for casual/practice conversations
1. **Smart context updates:** Always use GPT-4o (accuracy critical)
1. **Transcript polishing:** Use GPT-4o-mini (simple task)

**Never use:**

- ❌ GPT-4 Turbo or GPT-4 (outdated and expensive)
- ❌ o1 models (overkill for conversational AI)

**Best value:** GPT-4o-mini for most tasks, GPT-4o for high-stakes interactions

**Cost estimate:**

- Development: ~$0.26/month
- Production (20 hrs, hybrid): ~$2-3/month
- Very affordable for the value provided

---

*Last Updated: October 23, 2025*
*Pricing accurate as of October 2024 - check OpenAI website for current rates*
