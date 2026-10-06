# Responsive card material bounds

Exact f66b5e9 Windows offscreen tests returned31passed/2failed; native windows-platform tests returned24passed/9failed. Both include an image-provider exception for a535-point button raster. Other native input/focus failures remain unclassified: the reused offscreen launcher did not wait for native exposure/activation, so those are not established product defects.

StoneButton paints responsive Library artwork cards as well as compact controls. The button material guard rejected heights over512, while QML uses the actual card height. This repair permits bounded heights through2048, matching existing field/shadow material bounds, without changing geometry, event handlers, cache ownership or media state. Width remains bounded4096; nonpositive or excessive dimensions still reject. Six direct material regressions exercise actual535-point and2048-point rasters plus invalid boundaries.

This successor preserves frozen Mac evidence and the installed release. It does not claim to repair separated physical Done misses. Repaired-platform and applicable artifact qualification must be recorded separately before release.
