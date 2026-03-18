import time
from pathlib import Path
from src.nashville_numbers.tone_library import ToneLibrary, _utc_now

def measure_baseline():
    tl = ToneLibrary(Path("/tmp/tone_test2"))

    # Generate a large manifest
    manifest = {"tones": [], "irs": []}
    for i in range(10000):
        manifest["tones"].append({
            "id": f"tone_{i}",
            "name": f"Tone {i}",
            "model_file": f"tone_{i}.nam",
            "imported_at": _utc_now()
        })

    tl._save_manifest(manifest)
    man = tl._load_manifest()

    # Benchmark finding the last tone repeatedly
    start = time.time()
    for _ in range(100):
        tl._find_tone(man, "tone_9999")
    end = time.time()

    baseline = end - start
    print(f"Time finding last tone (baseline): {baseline:.4f}s")
    return baseline

def measure_optimized():
    tl = ToneLibrary(Path("/tmp/tone_test2"))

    manifest = {"tones": [], "irs": []}
    for i in range(10000):
        manifest["tones"].append({
            "id": f"tone_{i}",
            "name": f"Tone {i}",
            "model_file": f"tone_{i}.nam",
            "imported_at": _utc_now()
        })

    tl._save_manifest(manifest)
    man = tl._load_manifest()

    # Benchmark finding the last tone repeatedly
    start = time.time()
    # In optimized version, we'll map on load or just when calling _find_tone, wait.
    # The instruction says "Changing from a list scan to a dictionary mapping `id -> record` during load/cache is a classic caching optimization with clear, localized fix."

    # Let's test modifying _load_manifest to build a mapping? Or doing it on-the-fly?
    # If we modify _load_manifest to return an extra mapping dict, we have to change the signature.
    # What if we just do mapping cache on ToneLibrary class?
    # Or cache inside _load_manifest but that's returning a dict.

    # Let's look at how _load_manifest returns its value.
    pass

if __name__ == "__main__":
    measure_baseline()
