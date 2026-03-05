# Fretboard Visualization Improvements

The current implementation provides a dynamic fretboard for Guitar (6-string) and Bass (4/5-string) with Scale and Chord modes.

## Future Considerations

- **Complex Chord Voicings:** Currently, the chord mode shows all instances of the chord's notes across the entire fretboard. Implementing a "fingering" engine that suggests specific, playable shapes (CAGED system, drop-2, etc.) would be a powerful addition.
- **Custom Tunings:** Allow users to input custom string tunings (e.g., DADGAD, Drop D).
- **Lefty Mode:** Add a toggle to flip the fretboard for left-handed players.
- **Nut-only View:** An option to only show the first 4-5 frets (common for open chords).
- **Audio Feedback:** Integrating a simple synth to play the chord/scale when clicked.
- **Degree Preset:** Add a "1-3-6" preset button to quickly highlight the most common intervals as suggested.

## Technical Notes
- The fretboard is rendered entirely in the frontend using standard JS/DOM for maximum portability and zero-dependency compliance of the GUI.
- Note derivation for NNS tokens is done by mapping the degree to the current key's tonic.
