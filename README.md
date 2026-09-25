# Arabic Historical Video Editor

Local AI pipeline for turning Arabic narration recordings into edited
historical videos with automatic scene planning, asset sourcing, and
audio effects.

## Hardware
- Mac Mini M4 (16GB) or better
- ~15GB free disk for models

## Setup

### 1. Install Ollama models
```bash
ollama pull command-r7b-arabic:7b
ollama pull qwen2.5vl:7b# Auto-Vid-Editor
