# NAM Integration and Music Expansion Research for nashville-numbers

## Repository baseline and what already exists

The current repo is already beyond “converter + play a chord.” It has a layered internal architecture with discrete modules for GUI + HTTP routing, progression planning, voicing, plan→event sequencing, MIDI export, and an optional high‑quality audio backend. fileciteturn29file0L1-L1

At a high level, the repo’s own internal “module map” (captured in a recent commit diff) matches the direction described in your idea document:  

- `music_lab.py` produces a structured plan (sections/bars/slots + groove + timing metadata).  
- `sequence.py` converts that plan into a timed event list.  
- `midi_export.py` exports a multi‑track Standard MIDI file (Type 1) from those events.  
- `audio/*` provides optional HQ playback, while the GUI can fall back to browser playback. fileciteturn29file0L1-L1

The repo is also explicitly tracking “tone and live‑input exploration” as a Phase 4 follow‑through, including NAM/IR exploration and live-input experiments. fileciteturn29file0L1-L1

The GUI already supports an HQ audio mode and a browser fallback path; the README describes optional HQ audio installation and fallback behavior. citeturn8view0 The HQ path is orchestrated by an `AudioService` façade that reports whether HQ is ready, otherwise indicating a fallback of `"web_tone"`. citeturn8view1

**Key implication:** your “recommended technical architecture” (Intent → Performance → Source Audio → Tone Processing → Outputs) is already partially embodied in code: `music_lab.py` and `sequence.py` are effectively “Intent + Performance,” while `audio/*` and browser audio cover “Source + Output.” fileciteturn29file0L1-L1

## Ecosystem: entity["organization","Neural Amp Modeler","open source amp modeler"] and entity["organization","TONE3000","nam profiles community"]

Neural Amp Modeler is positioned as an ecosystem with separate trainer, core DSP, and plugin layers, published under permissive open-source licenses (per the official NAM site). citeturn0search4

TONE3000 is simultaneously (a) the most important distribution venue for `.nam` models and `.wav` impulse responses and (b) a reference implementation proving feasibility for browser-based NAM use cases. It has shipped:

- A browser “Web Player” that runs NAM inference locally in-browser (not a prerecorded sample), and  
- A “Live Input” feature that enables real-time playing through models in the browser. citeturn0search0turn0search5

image_group{"layout":"carousel","aspect_ratio":"16:9","query":["TONE3000 NAM Web Player screenshot","Neural Amp Modeler plugin screenshot","TONE3000 logo","Neural Amp Modeler logo"],"num_per_query":1}

### What TONE3000’s Web Player proves technically

TONE3000’s Web Player describes its architecture as:

- NAM core DSP compiled to WebAssembly (via Emscripten),
- executed inside an `AudioWorklet` (Web Audio API),
- processing audio buffers in real time. citeturn0search0

It also explicitly calls out a major operational constraint: **cross-origin isolation requirements** (COOP/COEP headers) to enable `SharedArrayBuffer`, which many high-performance WASM+worklet stacks require. citeturn0search0turn3search2turn3search11

### Near-term change signal: “A2” architecture

TONE3000 has announced “A2” as a next-generation NAM architecture targeting improved efficiency and broader device support, with a stated launch window of March 2026. citeturn0search3

**Design consequence for this repo:** treat NAM model-loading as versioned and future‑proof. Your tone layer should not hardcode assumptions that only “A1 WaveNet-style” models exist, because the ecosystem is actively evolving. citeturn0search3turn1search0

## How to get the required “items” and stay compliant

This section focuses on (a) *what you need to acquire*, (b) *where it comes from*, and (c) *how to integrate it without violating rights or platform terms.*

### NAM models (`.nam`) and what’s inside them

The NAM documentation describes `.nam` files as JSON-parseable dictionaries containing at least: `version`, `architecture`, `config`, and `weights`, with optional metadata (including descriptive fields and sometimes `sample_rate`). citeturn1search0

**Practical win for your repo:** even before you run inference, you can build a “Tone Browser” that:

- imports `.nam`,
- reads metadata,
- categorizes tones (clean/hi-gain/etc if present),
- and shows “model info” transparently to users. citeturn1search0

### Where users can obtain models and IRs

TONE3000’s “Upload” interface confirms it supports `.nam` and `.wav` uploads and surfaces a public catalog with frequent additions. citeturn2search1turn2search4

Individual tones on TONE3000 can carry explicit licenses; for example, a tone page can show “License: CC BY” for a specific model, implying attribution requirements for redistribution or certain uses (depending on license). citeturn2search5

From the NAM ecosystem side, the official NAM “Users” page directs users to:

- plugins (“Play”) and
- training resources (“Create”),  
and points users to TONE3000 as the sharing/discovery hub. citeturn1search13

### TONE3000 API acquisition path

TONE3000 provides an API with:

- an OAuth-like authentication flow,
- documented endpoints (including tone search and model download URLs),
- and a default rate limit (100 requests/minute). citeturn0search2turn2search9

It also describes a “Select” flow designed to let users authenticate and pick tones through TONE3000’s own UI, after which your app receives tone data and downloadable model URLs—positioned as the fastest integration option. citeturn0search2

### Compliance constraints: you must design *against* bulk scraping and redistribution

TONE3000’s Terms of Service (effective March 12, 2025) include explicit prohibitions against systematic downloading/bulk extraction and against packaging/redistributing tones obtained from the platform without permission. The Terms also clarify that creators retain ownership of uploaded models. citeturn2search0

Additionally, TONE3000’s Tone Sharing Policy prohibits sharing captures of commercial software without permission, which matters if your app ever assists with creating or publishing captures. citeturn2search6

**What this means for “how to get” assets inside your app:**

- Prefer **user-initiated** acquisition (manual download/import, or a “Select” flow where a user explicitly picks a tone). citeturn0search2turn2search0  
- Store assets **locally per-user** and treat them as user-managed content, not something your app redistributes as a bundled library (unless you have explicit permission/compatible licenses). citeturn2search0turn2search5  
- Make license/attribution visible per imported model/IR, because tone pages can carry license terms. citeturn2search5turn2search9

## A seamless architecture that fits this repo’s current direction

Your idea doc correctly highlights the core technical truth: NAM is most convincing when fed believable DI audio, not abstract MIDI notes. TONE3000’s Web Player reinforces this by letting users test tones against DI tracks and mix amp-only captures with cabinet IRs. citeturn0search0

The repo’s current state already gives you a clean seam: the plan→event pipeline can stay stable while you introduce new “Source Audio” realizations and a “Tone Processing” stage. The repo itself documents this separation (planner → sequence → MIDI export / audio service). fileciteturn29file0L1-L1

### The most “seamless” integration strategy: one transport, two renderers

A practical architecture that minimizes rewrites and aligns with what you already ship:

**Transport + musical intelligence remain authoritative in Python.**  

- `music_lab.py` continues to define sections/bars/slots/groove.  
- `sequence.py` remains the canonical event compiler (and already supports drums, voicings, voice leading, and multi-track MIDI export). fileciteturn29file0L1-L1

**Renderer selection happens at the edge (browser audio vs HQ fluidsynth).**  

- Keep the current HQ path (`AudioService` / FluidSynth) for “instructional playback” and MIDI verification. citeturn8view1turn8view0  
- Add a **Web Audio “tone render” path** that can (a) run NAM WASM for live input and/or (b) run tone preview against DI clips, all inside the existing HTML GUI approach. citeturn0search0turn0search5

This avoids trying to force NAM into the FluidSynth path (which is fundamentally event-based) and instead introduces NAM where Web Audio already excels: real-time audio graph processing. citeturn0search0turn3search1turn3search6

### Why Web Audio is the right first “tone stage” for this repo

TONE3000’s approach is directly compatible with your embedded single-page GUI model (your repo is already browser-first in UX, with a native window wrapper). citeturn0search0turn8view0

From a timing model perspective:

- `AudioWorkletProcessor.process()` is called on the audio rendering thread repeatedly in fixed-size blocks (“render quantum”), currently 128 frames. citeturn3search1turn3search14  

- The Web Audio spec notes that nodes like `AudioWorkletNode` and `ConvolverNode` can add latency to an audio graph, which is directly relevant when chaining NAM inference + IR convolution. citeturn3search6

This clarifies the engineering constraint: a real-time NAM+IR chain must be performant enough to meet the per-quantum deadline, or it will glitch. citeturn3search14turn0search0

### Enabling SharedArrayBuffer for a high-performance NAM WASM path

To use `SharedArrayBuffer` in the browser (often required for multithreaded/high-performance WASM designs), the document must be cross-origin isolated. Browser documentation explains cross-origin isolation requires specific response headers (COOP/COEP). citeturn3search2turn3search11

TONE3000’s NAM Web Player calls out the same requirement and gives the exact headers it uses (COOP `same-origin`, COEP `require-corp`). citeturn0search0

**Seamless implementation detail for this repo:** because your GUI server is local and under your control, you can add these headers globally in your HTTP handler, and you can serve the NAM WASM bundle from the same local origin to avoid COEP resource-blocking surprises. citeturn0search0turn3search2

## Phased build plan that makes the whole vision work

This plan is aligned with your idea doc’s “Live input first” principle, and it also matches the repo’s roadmap indicator that Phase 4 is now about tone/live input exploration. fileciteturn29file0L1-L1

### Tone import and preview layer

Implement this first because it delivers “NAM in the app” without forcing you to solve low-latency monitoring on day one.

The Tone Browser should support:

- importing a local `.nam`,
- importing an optional `.wav` IR,
- extracting `.nam` metadata for display,
- selecting a DI preview clip (bundled or user-provided),
- and auditioning the result through the NAM+IR chain. citeturn1search0turn0search0

This mirrors TONE3000’s Web Player interaction model (DI inputs, IR mixing, and in-browser inference). citeturn0search0

**Asset acquisition path:** start with “user imports files they downloaded manually,” which avoids API scope uncertainty and stays aligned with the Terms’ anti-bulk-download stance. citeturn2search0

### Live input practice rig

TONE3000’s Live Input flow demonstrates the exact UX: connect instrument → grant mic access → select audio interface → play through model. citeturn0search5

For your app, this feature becomes “Practice Mode” layered on top of your existing:

- progression targets,
- fretboard visualization,
- and loop-capable transport. fileciteturn29file0L1-L1

A practical first-cut design:

- Live input runs **only in the browser audio engine** (Web Audio).
- Backing playback for the transport also runs in that same browser context when Live Input is enabled, to ensure a single coherent mix engine (and a single latency regime). This avoids unsynced dual-output behavior between OS-level FluidSynth audio and browser audio. citeturn3search6turn3search14

### TONE3000 account integration

Once the local import path is stable, integrate the API in a way that is explicitly user-driven and avoids any perception of scraping.

Two options are documented by TONE3000:

- **Select flow** (fastest; TONE3000 hosts the browsing/auth UI and returns tone data + model URLs), or  
- **Full API** (you build your own browsing UI; you handle auth tokens; you call search endpoints). citeturn0search2turn0search1

For “seamless” UX in your app, the Select flow is likely the better first step because it reduces UI surface area and keeps you closer to TONE3000’s intended integration path. citeturn0search2

### Generated accompaniment through NAM

This is the differentiated feature, but it’s downstream because you need a believable DI source layer first.

Your repo already has a credible “intent and performance” layer:

- grooves,
- voicings,
- voice leading,
- percussion events,
- and track-separated MIDI export. fileciteturn29file0L1-L1

To drive NAM convincingly, introduce a DI instrument source strategy that is explicit and modular:

- “DI Guitar (Sample)” source for chords/arps,
- “DI Bass (Sample)” source for bassline,
- both routed into NAM+IR.

This can start narrowly (single articulation, small note range, minimal velocity layers) and expand later. The `.nam` file format spec being JSON-based also makes it straightforward to associate a tone preset with a specific generated part and store it in your project state. citeturn1search0

## Risks, constraints, and mitigations

### Performance and latency

Real-time NAM inference is CPU intensive, and TONE3000 notes performance requirements and limitations for browser-based real-time playback. citeturn0search0turn0search5

The browser will call your audio worklet processing in short blocks (128 frames), and missing deadlines causes audible glitching. citeturn3search1turn3search14

**Mitigation:** build in “quality tiers” (model size selection, oversampling off/on, IR length limits, optional IR bypass) and provide clear UI feedback when the device cannot sustain real-time processing. citeturn0search0turn0search3

### Cross-origin isolation friction

Cross-origin isolation unlocks `SharedArrayBuffer` but can restrict loading cross-origin resources unless they support the necessary policies. citeturn3search2turn3search11turn0search0

**Mitigation:** serve all NAM WASM assets and (ideally) downloaded models/IRs from your own local origin (download-to-disk in Python, then serve locally), instead of streaming cross-origin assets directly into the isolated page. citeturn0search0turn2search0

### Content licensing and redistribution

TONE3000’s Terms prohibit bulk downloading and unauthorized redistribution, and individual tones may have licenses requiring attribution or restricting redistribution. citeturn2search0turn2search5

**Mitigation:** treat tones as user-procured assets, store locally with type + license metadata, and never ship a “mirrored catalog.” Use explicit user action for “download this tone.” citeturn2search0turn0search2

### Platform evolution

TONE3000’s A2 announcement indicates model architecture and performance characteristics may change in the near term (March 2026). citeturn0search3

**Mitigation:** make the tone engine version-aware:

- parse `.nam` `version` and `architecture`,
- validate compatibility,
- and keep your renderer as a plug-in interface so you can swap transport-independent inference backends over time. citeturn1search0turn0search3
