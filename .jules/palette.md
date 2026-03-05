## 2024-05-30 - Prevent CLI Hang on TTY
**Learning:** CLI tools that read from `sys.stdin` by default will hang and provide a poor user experience if invoked without arguments on an interactive terminal.
**Action:** Always check `sys.stdin.isatty()` when reading from stdin. If it's a TTY and no arguments are provided, immediately present usage instructions and exit instead of blocking. This is a critical pattern for any CLI application that supports both arguments and piped input.
