"""Read-only WorkBuddy evidence collection and frozen-case auditing.

Chosen direction: raw bytes stay outside the release; projections expose calls,
receipts and visible output, never providerData.reasoning. Human review remains
necessary for semantic claims; this tool is not an execution permission gate.
"""
