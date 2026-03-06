# NAM + Music Expansion Ideas

Date: 2026-03-06
Status: Future idea document

## Purpose

This document captures a broader product direction for expanding Nashville Numbers from a converter/fretboard tool into a more complete music sketchpad and practice environment.

The main spark is integrating Neural Amp Modeler (NAM) so the app can move beyond simple note playback and into real guitar/bass tone. From there, the app could grow into progression playback, strumming and picking patterns, MIDI-driven writing tools, backing tracks, mode exploration, and arrangement helpers.

## Current Starting Point

As of today, this repo already has more than text conversion:

- Nashville Number conversion and key inference
- GUI-based fretboard visualization
- Note and chord playback routes
- A high-quality playback path based on FluidSynth
- A browser fallback synth when HQ audio is unavailable

That means the app already has the beginnings of a transport/playback system. NAM would not replace that foundation. It would sit on top of it as a more realistic tone stage.

## External Ecosystem Snapshot

### Neural Amp Modeler

Neural Amp Modeler is an open-source ecosystem built around three main pieces:

- trainer: model creation
- core DSP: real-time playback engine
- plugin: desktop plugin and standalone app layer

Official overview:

- [Neural Amp Modeler](https://www.neuralampmodeler.com/)
- [The Code](https://www.neuralampmodeler.com/the-code)

### TONE3000

TONE3000 is a major distribution point for NAM captures and impulse responses. Relevant pieces:

- public catalog of `.nam` models and `.wav` IRs
- browser playback and live-input experiences built around NAM
- beta API for app/device integrations
- open-source WASM work around browser NAM playback

Useful references:

- [TONE3000 home](https://www.tone3000.com/)
- [Neural Amp Modeler guide](https://www.tone3000.com/neural-amp-modeler)
- [NAM Web Player announcement](https://www.tone3000.com/blog/introducing-the-nam-web-player)
- [TONE3000 API beta announcement](https://www.tone3000.com/blog/introducing-the-tone3000-api)
- [tone-3000/neural-amp-modeler-wasm](https://github.com/tone-3000/neural-amp-modeler-wasm)

## Core Insight

The biggest technical truth here is simple:

NAM is best when it processes believable DI audio, not abstract note events.

That matters because our app currently thinks mostly in terms of:

- notes
- chords
- fretboard positions
- MIDI-like playback events

If we feed NAM a plain synth, a toy oscillator, or a low-realism GM guitar patch, we will get distorted output, but not necessarily convincing guitar tone. The quality of the source matters.

So there are really two different NAM opportunities:

1. Live input NAM
2. Generated accompaniment NAM

Live input is the easiest way to get authentic results quickly. Generated accompaniment is more ambitious, because it needs a good DI source layer before the NAM stage.

## What NAM Could Do For This App

### 1. Make the app sound like an instrument instead of a utility

Today the app can help users understand harmony and hear notes/chords. NAM could make the same experience feel musical and inspiring instead of purely instructional.

### 2. Turn progressions into playable backing ideas

A progression like `1 - 5 - 6m - 4` could become:

- a strummed acoustic idea
- a clean electric picking pattern
- a crunchy pop-rock rhythm part
- a bass part through a bass amp model
- a full loop with count-in and tempo

### 3. Bridge theory and tone

Nashville Numbers are useful because they are abstract. NAM is useful because it is concrete and physical. Putting them together could make the app teach both:

- harmonic function
- voicing choices
- fretboard shape choice
- arrangement
- tone selection
- genre feel

## Product Directions

### Direction A: Live Input Practice Rig

This is the cleanest NAM use case.

Flow:

`instrument input -> NAM model -> optional IR -> output`

What users could do:

- plug in guitar or bass
- choose a key and progression
- see fretboard targets
- play along with the chart
- hear themselves through a real amp/cab model
- switch tones by genre or song section

Why this is attractive:

- highest wow factor
- no need to fake a guitar source from MIDI
- fits NAM naturally
- turns the app into a practice tool immediately

Potential features:

- tuner
- input meter
- latency meter
- noise gate
- simple reverb/delay after the amp stage
- loop selected bars
- slow-down practice mode

### Direction B: Auto-Generated Guitar/Bass Playback

This is the more ambitious and more differentiated idea.

Flow:

`progression engine -> pattern engine -> DI source instrument -> NAM model -> IR -> mix bus`

What this would unlock:

- automatic rhythm guitar playback
- auto-picked arpeggios
- bassline generation from chord roots and passing tones
- section-aware arrangement ideas
- backing tracks from number charts

The challenge:

We need a believable source before the NAM stage.

Possible source strategies:

- multi-sampled DI guitar note library
- DI bass sample library
- recorded strumming phrase library sliced by tempo
- SFZ/SoundFont-style DI instrument mapped by articulation
- hybrid engine that uses samples for attack and synthesis for sustain

This is feasible, but it is meaningfully more work than live input.

### Direction C: Tone Browser + Preview Layer

This would let users browse tones inside the app and audition them quickly.

Possible UX:

- choose `Clean`, `Edge`, `Crunch`, `Lead`, `Bass`, `Ambient`
- preview a reference riff through several tones
- favorite tones for later use
- attach a tone to a progression or song idea

Possible sources:

- bundled starter tones
- user-imported `.nam` and IR files
- TONE3000 account integration
- later, direct browsing if API scope allows

This could be valuable even before full live input or auto-accompaniment exists.

### Direction D: Export/Re-Amp Workflow

This is the lowest-risk near-term option.

Instead of running NAM fully in-app right away, the app could export:

- MIDI
- dry audio
- progression stems
- bassline stems
- click/count-in tracks

Then the user runs those through NAM in a DAW or NAM-compatible player.

This is less magical, but much faster to deliver.

## Bigger Music Features Beyond NAM

These are worth documenting because they fit the same future direction.

### Progression Engine

The app could understand number charts as musical objects, not just text.

Example capabilities:

- detect bar structure
- loop sections
- set tempo and meter
- label verse, chorus, bridge
- save song forms
- transpose instantly
- audition alternate harmonic rhythms

### Strumming and Picking Patterns

Each progression could be paired with a performance style:

- whole-note pads
- downstrokes
- folk strum
- country train beat
- funk scratches
- worship swells
- broken-chord fingerpicking
- pop eighth-note chugs
- arpeggiated synth-like guitar picking

Controls:

- intensity
- swing
- humanization
- mute density
- accent pattern
- palm mute amount

### Bassline Generator

For each chart, generate:

- root notes
- root-fifth patterns
- scalar walkups/walkdowns
- passing tones
- pedal tones
- simple groove templates by genre

This alone would make the app more useful as a songwriting assistant.

### Drum and Percussion Support

Even simple drums would make the app feel complete:

- metronome
- click with accents
- shaker/tambourine loops
- basic drum grooves by style
- fills at section boundaries

### MIDI Click-to-Make-Music Composer

This could become a central creative surface.

Possible UI ideas:

- piano roll
- fretboard click-to-place notes
- step sequencer
- pad/grid view for clips
- drag notes to change duration
- snap to key, mode, and chord tones
- highlight avoid notes
- convert lick ideas into scale-degree labels

This should not try to become a full DAW. It should be a constrained music sketchpad focused on harmony, fretboard, and arrangement.

### Modes, Triads, Sevenths, and Functional Harmony

The app could expand into a theory playground:

- major, natural minor, harmonic minor, melodic minor
- church modes
- pentatonics and blues scales
- triad families
- seventh chord families
- secondary dominants
- borrowed chords
- modal interchange
- chord substitutions
- diatonic harmonization by key

Possible interactions:

- click a mode and see fretboard shapes
- hear the same progression reharmonized by mode
- compare `I IV V` vs `i bVI bVII`
- show triads over each degree
- auto-generate practice loops from one harmonic concept

### Backing Tracks

Longer-term, the app could create simple arrangement-level backing tracks:

- intro
- verse
- pre-chorus
- chorus
- bridge
- outro

Each section could have:

- progression
- groove preset
- instrumentation choices
- tone choices
- dynamics

Exports:

- WAV
- stems
- MIDI
- practice mix
- no-guitar backing track

## Recommended Technical Architecture

If this direction is pursued, the app should think in layers:

### Layer 1: Music Intent

- key
- mode
- progression
- section map
- tempo
- meter
- groove

### Layer 2: Performance Generation

- voicing selector
- strumming/picking engine
- bassline generator
- drum pattern engine
- humanization

### Layer 3: Source Audio

- live instrument input
- DI guitar sample instrument
- DI bass sample instrument
- current synth fallback

### Layer 4: Tone Processing

- NAM model
- IR convolution
- post FX
- limiter/output gain

### Layer 5: Output Targets

- live monitoring
- loop playback
- export render
- stems
- MIDI

This separation keeps music logic independent from the specific tone engine.

## Best Integration Paths

### Path 1: Live Input First

Best first NAM path if the goal is immediate value.

Why:

- realistic results without building a fake DI instrument first
- clean mental model
- aligns with NAM's strengths
- makes the app a practice and rehearsal tool

What it needs:

- low-latency input/output device handling
- model loading
- IR loading
- UI for gain/cab selection
- fallback when NAM is unavailable

### Path 2: Pattern Engine First, NAM Later

Best first product path if the goal is broader songwriting value.

Why:

- useful even with the current synth/HQ playback stack
- creates musical behavior before tone complexity
- opens progression playback, basslines, and backing tracks

Then later:

- add DI source instruments
- add NAM tone stage

### Path 3: Tone Browser First

Best first path if the goal is discoverability and experimentation.

Why:

- lower scope than full arrangement generation
- makes NAM feel present in the app early
- can start with imports and a small curated bundle

## Practical Recommendation

If we want the strongest sequence of work, the most sensible order is:

1. Build a progression/pattern transport using the existing playback system.
2. Add export paths and simple backing-track generation.
3. Add live input support.
4. Add NAM + IR processing for live input.
5. Add DI-based generated guitar/bass playback through NAM.
6. Add tone library integration and richer browser/discovery workflows.

Reason:

- Step 1 gives immediate musical value.
- Step 4 gives the first authentic tone payoff.
- Step 5 is the hard but differentiated feature.

## TONE3000-Specific Ideas

Potential integrations:

- user imports `.nam` and IR files downloaded manually from TONE3000
- user signs into TONE3000 and loads saved/favorited tones if API permissions allow
- in-app recommended starter tones for common styles
- "tone packs" attached to genres, tunings, or song templates

Ideas for UX:

- `Try this chart with Deluxe Clean / AC Crunch / Recto Heavy / Motown Bass`
- `Swap cab` or `swap IR`
- `favorite this tone for all country progressions`
- `attach this tone to chorus only`

Important constraint:

The TONE3000 API beta announcement describes version one as account-based access to a user's own created or favorited tones. That sounds promising, but it is not the same thing as unrestricted in-app browsing of the whole public catalog. We should not design around capabilities we have not confirmed.

## Browser vs Native Integration

### Browser route

Pros:

- TONE3000 has already shown NAM can run in the browser via WASM
- naturally fits the existing embedded HTML GUI
- easier to experiment with web-based player components

Cons:

- CPU-heavy on weaker machines
- browser audio routing and permissions can be awkward
- lower control over low-latency desktop audio behavior

### Native route

Pros:

- potentially better latency and device control
- better fit for a serious practice rig
- easier long-term if the app becomes more audio-centric

Cons:

- more integration work from Python into C++/native DSP
- packaging complexity increases
- harder cross-platform maintenance

A hybrid approach may be best:

- browser/WASM for exploration and preview
- native path later for serious live input and production use

## Content Strategy

To make this compelling, tone alone is not enough. We need musical content too.

Potential content buckets:

- progression presets by genre
- strumming presets by genre
- bassline presets
- backing groove presets
- lesson/prompt packs
- practice drills
- scale and mode workouts
- artist-adjacent tone categories without trademark abuse

## Risks

### 1. NAM is not a magic replacement for source realism

Without good DI input, autogenerated guitar parts may sound fake even with a great amp model.

### 2. Scope creep

This can easily turn from "helpful music utility" into "accidental DAW."

Guardrail:

Stay focused on theory, fretboard, arrangement, and practice workflows.

### 3. Latency and CPU load

Real-time NAM, especially in browser contexts, can be demanding.

### 4. Licensing and asset rights

The NAM code may be permissively licensed, but individual models and IRs can still have creator-specific usage expectations. We should treat hosted content, downloads, API use, and redistribution carefully.

### 5. Product identity drift

If everything gets added at once, the Nashville Numbers value proposition gets blurry.

Guardrail:

Keep the core promise clear: understand harmony faster, hear it better, and turn it into something playable.

## Good First Experiments

These are small enough to validate the direction without a giant rewrite.

### Experiment 1: Progression Playback Engine

Take a number chart and generate:

- tempo-based loop playback
- strum patterns
- bass root notes
- count-in

Use the current audio stack first.

### Experiment 2: Live Input Mode

Add a simple live-input path with:

- input level meter
- monitoring toggle
- dry monitoring first
- later, NAM/IR insertion

### Experiment 3: Tone Import Proof of Concept

Support:

- selecting a local `.nam`
- selecting an optional IR
- saving a named preset

Even without full browsing, this would prove the workflow.

### Experiment 4: DI-Driven Autoplay Prototype

Use one very small DI guitar sample set and one bass DI set to test whether generated parts feel convincing after NAM processing.

This is the real test for "click notes to make music" plus realistic tone.

## Vision Statement

The long-term opportunity is not just "Nashville Numbers with amp sims."

It is a tool where a user can:

- type a number chart
- see the harmony on the fretboard
- hear it as chords, riffs, and basslines
- switch between modes and reharmonizations
- practice it live through great tones
- sketch a backing track
- export something musical, not just educational

If done well, the app could live in a unique space between:

- theory trainer
- songwriter scratchpad
- practice rig
- fretboard explorer
- lightweight backing-track generator

## Bottom Line

Yes, NAM feels like a strong future fit for this app.

But the right framing is:

- not "replace our current audio"
- not "turn MIDI directly into magic guitar tone"
- not "build a full DAW"

The right framing is:

- build a better musical engine first
- use NAM where believable source audio exists
- start with live input or controlled DI playback
- grow toward tone-aware progression playback and practice tools

That path keeps the idea creative, ambitious, and technically grounded.
