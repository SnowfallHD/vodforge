# Output picker initialization and reopen reliability

Qt Quick uses the public FolderDialog on both desktop platforms. Initialize it with an existing absolute selected folder, then existing Downloads, then explicit Home. Retain the save destination when a folder disappears; do not silently replace it while opening a chooser. Reject relative selections and report provider access failures. Existing local folder validation remains required.

A retained Qt 6.11.2 dialog helper applies its initial directory only on first show. Create a new public FolderDialog for each opening, before open; ignore another trigger while visible. Forge, Settings and recovery share this route. No custom OS picker, private API or validation bypass is introduced.

Sixteen source/offscreen cases cover fallback, relative-path rejection, provider errors, spaces/Unicode/literal percent/hash, immediate-close persistence, bundle-internal cwd, cancel, latest-folder reopen and visible-trigger identity. Exact e80 runtime fails seven cases; fixed focused regressions pass79 and maintained workflow checks36. Native paste/reopen/restart must be independently recorded; the user-reported native “disallowed” message is not reproduced by these tests. Windows native remains unverified.

Primary implementation: https://raw.githubusercontent.com/qt/qtdeclarative/v6.11.2/src/quickdialogs/quickdialogs/qquickfolderdialog.cpp
