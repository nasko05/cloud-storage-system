"""Server-side AI reorganization assistant.

A stateless tool-calling loop over an OpenRouter (OpenAI-compatible) chat model.
Read-only tools run inline; mutating tools are proposed and applied only after
the user approves, transactionally, through the same operation cores the REST
routers use.
"""
