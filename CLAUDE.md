# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Trading Journal - A codebase for tracking and analyzing trading activity.

## Current Status

This is a newly initialized repository. The codebase structure and tooling will be established as development progresses.

## Development Setup

Development commands will be documented here once the project structure is established.

## Architecture

Architecture documentation will be added as the codebase develops.

## Claude Code Configuration

### Status Line Setup

The Claude Code status line is configured to display real-time token usage and cost tracking in the bottom right of the screen.

**Display Format:** `Model Name | ### in | $#.#### | 150k/200k (75%)`

**Example:** `Claude 3.5 Sonnet | 23k in | $0.0690 | 24k/200k (12%)`

**Information Shown:**
- **Model Name** - Current Claude model being used
- **Input Tokens** - Total input tokens consumed in the session
- **Cost** - Estimated cost in USD based on current pricing
- **Context Usage** - Current total tokens vs maximum context window
- **Percentage** - Percentage of context window utilized

**Configuration Location:**
- Global settings: `~/.claude/settings.json`
- Status line script: `~/.claude/statusline-command.sh`

**To Apply Across Projects:**
The status line configuration is global and automatically applies to all Claude Code sessions. No per-project configuration is needed.

**Pricing Reference:**
- Input tokens: $3 per million tokens
- Output tokens: $15 per million tokens
