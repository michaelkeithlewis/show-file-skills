"""Session maker: build and edit DiGiCo .ses files from an input list or a show description, on an editor-saved
baseline (see ../../references/baselines.md).

Modules: consoles (console table, baselines found by file name), build (writer), intake (input lists, categories,
descriptions), taxonomy (the 50 template categories and their name rules), listparse (input-list reader),
layout (input count / order / stereo by bytes), process (per-instrument processing + read back),
validate (structural invariants), inspect (read-only session checker), edit (operations on an existing session),
commands (plain-English edit commands -> edit operations), options (FX, mixes, buses, patch, preamps for a build),
fx / sends / buses / patch / busside (the writers behind options and edit).
"""
