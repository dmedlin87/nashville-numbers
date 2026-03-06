## 2026-03-04 - Caching Pure Key Inference Functions
**Learning:** During musical section splitting (`infer_sections`), the key inference engine iteratively splits the progression string and calls `rank_keys` to score identical sub-strings repeatedly. The tokenization and string extraction inside this function are unexpectedly expensive when called thousands of times on long inputs.
**Action:** Use `@functools.lru_cache` to memoize pure string-analysis functions (like `rank_keys`) that are repeatedly called with the exact same sub-strings, especially in recursive or splitting algorithms.
## 2024-05-20 - Optimize String Tokenization with Regex
**Learning:** Manual character-by-character parsing with a `while` loop in Python is computationally expensive due to interpreter overhead per iteration, especially for long input strings common in text processing.
**Action:** Replace manual tokenization loops with compiled regular expressions (`re.split` or `re.finditer`) where possible, as they delegate the parsing logic to highly optimized C extensions.
## 2024-10-25 - Module-Level Constants for Dictionary/List Allocations
**Learning:** Re-declaring literal dictionaries, lists, or sets (e.g., mapping musical degrees to semitones) inside a function causes Python to allocate new objects and garbage-collect them on every single call. For functions called frequently in loops (like converting every token in a long chord progression), this overhead adds up significantly.
**Action:** Move static lookup tables, configuration dictionaries, and constant sets to the module level so they are initialized exactly once at import time.
