## 2026-03-04 - Caching Pure Key Inference Functions
**Learning:** During musical section splitting (`infer_sections`), the key inference engine iteratively splits the progression string and calls `rank_keys` to score identical sub-strings repeatedly. The tokenization and string extraction inside this function are unexpectedly expensive when called thousands of times on long inputs.
**Action:** Use `@functools.lru_cache` to memoize pure string-analysis functions (like `rank_keys`) that are repeatedly called with the exact same sub-strings, especially in recursive or splitting algorithms.
