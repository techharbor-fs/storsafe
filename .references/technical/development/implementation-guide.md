# Implementation Guide: Logging & DEBUG_MODE Pattern

**Purpose**: Step-by-step guide for implementing logging and DEBUG_MODE in existing scripts
**Last Updated**: October 12, 2025

---

## 📋 Overview

This guide shows how to add:

1. **Centralized logging** (logger_config.py)
1. **DEBUG_MODE pattern** (verbose/quiet output toggle)
1. **DRY_RUN mode** (preview without execution)

to any automation script.

---

## 🎯 Quick Start Checklist

For any new or existing script:

- [ ] Copy `logger_config.py` to client folder if not exists
- [ ] Add `DEBUG_MODE` constant at top of script
- [ ] Import logging functions
- [ ] Replace `print()` with `logger.info()` or wrap in `DEBUG_MODE`
- [ ] Add `log_automation_start()` and `log_automation_end()`
- [ ] Add `exc_info=True` to error logging
- [ ] Test with `DEBUG_MODE = True` then `False`

---

## 🔧 Step-by-Step Implementation

### Step 1: Setup Logger Config

**If logger_config.py doesn't exist in your client folder:**

```bash
# Copy from westons to your client folder
cp "automation files/02. westons/logger_config.py" "automation files/01. personal/logger_config.py"
```

### Step 2: Add Constants at Top of Script

```python
# Add these near the top, after imports
# ============================================================
# Configuration
# ============================================================

# Development/Production Mode
DEBUG_MODE = True  # Set to False for production
DRY_RUN = False    # Set to True to preview without executing
```

### Step 3: Import Logging Functions

```python
# Add to imports section
from logger_config import (
    setup_logger,
    log_automation_start,
    log_automation_end,
    log_section
)

# Create logger (use descriptive module name)
logger = setup_logger('speechmatics')  # or 'payroll', 'invoice', etc.
```

### Step 4: Add Automation Lifecycle Logging

**At script start:**

```python
def main():
    """Main function"""
    log_automation_start(
        logger,
        "Speechmatics Transcriber",
        "Real-time audio transcription with polishing"
    )

    try:
        # Your automation code here
        run_transcription()

        # Success logging with summary
        log_automation_end(
            logger,
            "Speechmatics Transcriber",
            success=True,
            summary={
                "Duration": f"{duration:.1f} seconds",
                "Transcribed": f"{word_count} words"
            }
        )

    except Exception as e:
        # Failure logging with full stack trace
        logger.error(f"Transcription failed: {e}", exc_info=True)
        log_automation_end(
            logger,
            "Speechmatics Transcriber",
            success=False
        )
        raise
```

### Step 5: Replace Print Statements

#### Pattern 1: Verbose Debug Output

```python
# Before
print(f"Processing file: {filename}")
print(f"Detected language: {language}")
print(f"API response: {response}")

# After
if DEBUG_MODE:
    logger.debug(f"Processing file: {filename}")
    logger.debug(f"Detected language: {language}")
    logger.debug(f"API response: {response}")
```

#### Pattern 2: Important Progress Messages

```python
# Before
print("Starting transcription...")
print(f"Transcribed {count} words")
print("Transcription complete!")

# After
logger.info("Starting transcription...")
logger.info(f"Transcribed {count} words")
logger.info("✅ Transcription complete!")
```

#### Pattern 3: Warnings and Errors

```python
# Before
print(f"Warning: Audio quality low")
print(f"Error: API connection failed")

# After
logger.warning(f"⚠️ Audio quality low - results may be inaccurate")
logger.error(f"❌ API connection failed: {error_details}")
```

### Step 6: Add Section Markers

For scripts with multiple phases:

```python
# Phase 1
log_section(logger, "Loading Configuration")
# ... load config code ...

# Phase 2
log_section(logger, "Processing Audio")
# ... audio processing code ...

# Phase 3
log_section(logger, "Generating Output")
# ... output generation code ...
```

### Step 7: Implement DRY_RUN Mode

For actions that modify data or make API calls:

```python
def save_transcript(text, filename):
    """Save transcript to file"""
    if DRY_RUN:
        logger.info(f"[DRY RUN] Would save {len(text)} characters to {filename}")
        logger.info(f"[DRY RUN] Preview: {text[:100]}...")
        return

    # Actual save logic
    with open(filename, 'w') as f:
        f.write(text)
    logger.info(f"✅ Saved transcript to {filename}")

def send_to_api(data):
    """Send data to external API"""
    if DRY_RUN:
        logger.info(f"[DRY RUN] Would send {len(data)} bytes to API")
        logger.info(f"[DRY RUN] Data preview: {data[:200]}")
        return {"status": "dry_run", "message": "Not actually sent"}

    # Actual API call
    response = requests.post(API_URL, json=data)
    logger.info(f"✅ API response: {response.status_code}")
    return response.json()
```

---

## 📝 Real-World Example: Speechmatics Transcriber

### Before (Using print statements)

```python
def transcribe_audio(audio_file):
    print("Starting transcription...")
    print(f"File: {audio_file}")
    print(f"Size: {os.path.getsize(audio_file)} bytes")

    try:
        # Connect to API
        print("Connecting to Speechmatics API...")
        ws = connect_to_speechmatics()

        # Send audio
        print("Sending audio data...")
        for chunk in read_audio(audio_file):
            ws.send(chunk)
            print(f"Sent {len(chunk)} bytes")

        # Get results
        print("Receiving transcription...")
        transcript = ws.receive()
        print(f"Received {len(transcript)} characters")

        # Polish with OpenAI
        print("Polishing transcript with OpenAI...")
        polished = polish_transcript(transcript)
        print(f"Polishing complete: {len(polished)} characters")

        # Save
        output_file = audio_file.replace('.wav', '.txt')
        with open(output_file, 'w') as f:
            f.write(polished)
        print(f"Saved to {output_file}")

        print("Transcription complete!")
        return polished

    except Exception as e:
        print(f"Error: {e}")
        raise
```

### After (With logging and DEBUG_MODE)

```python
# Configuration
DEBUG_MODE = True
DRY_RUN = False

# Setup logging
from logger_config import setup_logger, log_automation_start, log_automation_end, log_section
logger = setup_logger('speechmatics')

def transcribe_audio(audio_file):
    """Transcribe audio file with Speechmatics API and polish with OpenAI."""

    log_automation_start(
        logger,
        "Audio Transcription",
        f"Transcribe and polish: {os.path.basename(audio_file)}"
    )

    try:
        # Log file info
        file_size = os.path.getsize(audio_file)
        if DEBUG_MODE:
            logger.debug(f"File: {audio_file}")
            logger.debug(f"Size: {file_size:,} bytes")

        # Phase 1: Connect to API
        log_section(logger, "Connecting to Speechmatics API")
        ws = connect_to_speechmatics()
        logger.info("✅ Connected to Speechmatics API")

        # Phase 2: Send audio
        log_section(logger, "Sending Audio Data")
        total_sent = 0
        for chunk in read_audio(audio_file):
            ws.send(chunk)
            total_sent += len(chunk)

            if DEBUG_MODE and total_sent % 100000 == 0:
                logger.debug(f"Sent {total_sent:,} bytes...")

        logger.info(f"✅ Sent {total_sent:,} bytes total")

        # Phase 3: Receive transcription
        log_section(logger, "Receiving Transcription")
        transcript = ws.receive()
        word_count = len(transcript.split())
        logger.info(f"✅ Received transcription: {len(transcript)} characters, {word_count} words")

        if DEBUG_MODE:
            logger.debug(f"Preview: {transcript[:200]}...")

        # Phase 4: Polish with OpenAI
        log_section(logger, "Polishing Transcript")

        if DRY_RUN:
            logger.info("[DRY RUN] Would polish with OpenAI")
            polished = transcript
        else:
            polished = polish_transcript(transcript)
            logger.info(f"✅ Polishing complete: {len(polished)} characters")

            if DEBUG_MODE:
                logger.debug(f"Preview: {polished[:200]}...")

        # Phase 5: Save results
        log_section(logger, "Saving Results")
        output_file = audio_file.replace('.wav', '.txt')

        if DRY_RUN:
            logger.info(f"[DRY RUN] Would save to {output_file}")
        else:
            with open(output_file, 'w') as f:
                f.write(polished)
            logger.info(f"✅ Saved to {output_file}")

        # Success summary
        log_automation_end(
            logger,
            "Audio Transcription",
            success=True,
            summary={
                "File": os.path.basename(audio_file),
                "Size": f"{file_size:,} bytes",
                "Characters": len(polished),
                "Words": word_count,
                "Output": os.path.basename(output_file)
            }
        )

        return polished

    except Exception as e:
        # Detailed error logging with stack trace
        logger.error(f"❌ Transcription failed: {e}", exc_info=True)
        log_automation_end(logger, "Audio Transcription", success=False)
        raise
```

**Benefits:**

- ✅ **DEBUG_MODE = True**: Shows all details during development
- ✅ **DEBUG_MODE = False**: Clean output for production
- ✅ **DRY_RUN = True**: Preview without actually calling APIs
- ✅ **Logs saved to file**: `logs/speechmatics_YYYYMMDD.log`
- ✅ **Console colored output**: Easy to scan visually
- ✅ **Full error traces**: Debug problems quickly

---

## 🎨 Output Comparison

### DEBUG_MODE = True (Development)

```text
2025-10-12 14:30:00 | INFO     | ═══════════════════════════════════════════════════════
2025-10-12 14:30:00 | INFO     | Starting: Audio Transcription
2025-10-12 14:30:00 | INFO     | Description: Transcribe and polish: audio.wav
2025-10-12 14:30:00 | INFO     | ═══════════════════════════════════════════════════════
2025-10-12 14:30:00 | DEBUG    | File: C:\path\to\audio.wav
2025-10-12 14:30:00 | DEBUG    | Size: 1,234,567 bytes
2025-10-12 14:30:01 | INFO     | ───────────────────────────────────────────────────────
2025-10-12 14:30:01 | INFO     | Connecting to Speechmatics API
2025-10-12 14:30:01 | INFO     | ───────────────────────────────────────────────────────
2025-10-12 14:30:02 | INFO     | ✅ Connected to Speechmatics API
2025-10-12 14:30:02 | INFO     | ───────────────────────────────────────────────────────
2025-10-12 14:30:02 | INFO     | Sending Audio Data
2025-10-12 14:30:02 | INFO     | ───────────────────────────────────────────────────────
2025-10-12 14:30:02 | DEBUG    | Sent 100,000 bytes...
2025-10-12 14:30:03 | DEBUG    | Sent 200,000 bytes...
2025-10-12 14:30:05 | INFO     | ✅ Sent 1,234,567 bytes total
... (continues with all details)
```

### DEBUG_MODE = False (Production)

```text
2025-10-12 14:30:00 | INFO     | ═══════════════════════════════════════════════════════
2025-10-12 14:30:00 | INFO     | Starting: Audio Transcription
2025-10-12 14:30:00 | INFO     | Description: Transcribe and polish: audio.wav
2025-10-12 14:30:00 | INFO     | ═══════════════════════════════════════════════════════
2025-10-12 14:30:02 | INFO     | ✅ Connected to Speechmatics API
2025-10-12 14:30:05 | INFO     | ✅ Sent 1,234,567 bytes total
2025-10-12 14:30:10 | INFO     | ✅ Received transcription: 5,432 characters, 987 words
2025-10-12 14:30:15 | INFO     | ✅ Polishing complete: 5,234 characters
2025-10-12 14:30:15 | INFO     | ✅ Saved to audio.txt
2025-10-12 14:30:15 | INFO     | ═══════════════════════════════════════════════════════
2025-10-12 14:30:15 | INFO     | ✅ Automation Complete: Audio Transcription
2025-10-12 14:30:15 | INFO     | Summary:
2025-10-12 14:30:15 | INFO     |   File: audio.wav
2025-10-12 14:30:15 | INFO     |   Size: 1,234,567 bytes
2025-10-12 14:30:15 | INFO     |   Characters: 5234
2025-10-12 14:30:15 | INFO     |   Words: 987
2025-10-12 14:30:15 | INFO     |   Output: audio.txt
2025-10-12 14:30:15 | INFO     | ═══════════════════════════════════════════════════════
```

---

## 🔍 Testing Your Implementation

### Step 1: Test with DEBUG_MODE = True

```python
DEBUG_MODE = True
DRY_RUN = True

# Run your script
python your_script.py
```

**Verify:**

- ✅ Console shows detailed debug messages
- ✅ Log file created in `logs/`
- ✅ No actual API calls (DRY_RUN mode)
- ✅ Preview messages show what would happen

### Step 2: Test with DEBUG_MODE = False

```python
DEBUG_MODE = False
DRY_RUN = True

# Run your script
python your_script.py
```

**Verify:**

- ✅ Console shows only important messages
- ✅ Still no actual execution (DRY_RUN mode)
- ✅ Output is clean and professional

### Step 3: Production Run

```python
DEBUG_MODE = False
DRY_RUN = False

# Run your script
python your_script.py
```

**Verify:**

- ✅ Actual execution happens
- ✅ Clean console output
- ✅ Detailed log file for debugging if needed

---

## 📊 Common Patterns

### Pattern 1: Loop Processing with Progress

```python
log_section(logger, "Processing Records")

total = len(records)
for idx, record in enumerate(records, 1):
    if DEBUG_MODE:
        logger.debug(f"Processing record {idx}/{total}: {record['id']}")

    result = process_record(record)

    # Log every 10% progress
    if idx % (total // 10) == 0:
        logger.info(f"Progress: {idx}/{total} ({idx/total*100:.0f}%)")

logger.info(f"✅ Processed {total} records")
```

### Pattern 2: External API Calls

```python
@retry(stop=stop_after_attempt(3), wait=wait_exponential(min=2, max=10))
def call_external_api(data):
    """Call API with retry logic"""

    if DRY_RUN:
        logger.info(f"[DRY RUN] Would call API with {len(data)} records")
        return {"status": "dry_run"}

    try:
        logger.info(f"Calling API...")
        response = requests.post(API_URL, json=data)
        response.raise_for_status()

        logger.info(f"✅ API call successful")
        if DEBUG_MODE:
            logger.debug(f"Response: {response.json()}")

        return response.json()

    except requests.RequestException as e:
        logger.error(f"❌ API call failed: {e}", exc_info=True)
        raise
```

### Pattern 3: File Operations

```python
def save_results(data, filename):
    """Save results to file with backup"""

    if DRY_RUN:
        logger.info(f"[DRY RUN] Would save {len(data)} records to {filename}")
        return

    # Backup existing file
    if os.path.exists(filename):
        backup = f"{filename}.backup"
        shutil.copy2(filename, backup)
        logger.info(f"✅ Created backup: {backup}")

    # Save new data
    with open(filename, 'w') as f:
        json.dump(data, f, indent=2)

    logger.info(f"✅ Saved {len(data)} records to {filename}")

    if DEBUG_MODE:
        logger.debug(f"File size: {os.path.getsize(filename):,} bytes")
```

---

## 🎯 Quick Reference

### When to Use Each Log Level

| Level | Use For | Example |
|-------|---------|---------|
| `logger.debug()` | Detailed info for developers (DEBUG_MODE only) | Variable values, loop iterations |
| `logger.info()` | Normal operations, progress | "Processing started", "✅ Complete" |
| `logger.warning()` | Concerning but not fatal | "⚠️ Low disk space", "API slow" |
| `logger.error()` | Errors that need attention | "❌ Failed to save file" |
| `logger.critical()` | System failures | "🚨 Database connection lost" |

### Log Emoji Guide

- ✅ Success/completion
- ❌ Failure/error
- ⚠️ Warning/caution
- 🔍 Investigation/checking
- 📊 Statistics/summary
- 🚀 Starting/launching
- ⏱️ Performance/timing
- 🎯 Target/goal reached

---

## 📚 Next Steps

1. **Implement in one script first** - Test and refine
1. **Create a template** - Copy pattern to other scripts
1. **Update AI instructions** - Add implementation guidelines
1. **Review logs regularly** - Improve logging based on usefulness

---

**For questions, refer to copilot-instructions.md or [best-practices.md](best-practices.md)**
