"""codejudge-mcp: an MCP server (Streamable HTTP) that wraps CodeJudge's public
HTTP API as tools an AI agent can call.

A separate deployable from the agent (D1): it is the only component that talks to
CodeJudge, and it does so purely over HTTP. Written in Python using the official
`mcp` SDK so the whole repo is one language (revises the original D2, which had
this in Go — MCP's job here is thin enough that a second language bought nothing).
"""
