"""The one command registry every surface of the interface reads and runs.

Nothing is re-exported here on purpose: the palette, the composer, the key
hints and the buttons import the module they need, so no surface can grow its
own copy of a command.
"""
