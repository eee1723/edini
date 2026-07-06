"""Chat assembly layer: ChatRuntime, ScopeConfig, ChatWindowShell, BaseChatDriver.

Layering: this layer wires RpcClient (via ChatRuntime) to components/. It is the
ONLY place that knows about both. Components never import from here.
"""
