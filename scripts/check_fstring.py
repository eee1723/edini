"""Scan evaluator.py for f-strings with backslash in expressions."""
import sys

with open('python3.11libs/edini/eval/evaluator.py', 'r', encoding='utf-8') as f:
    content = f.read()

lines = content.split('\n')

# Simple approach: look at each line that starts an f-string
# and check if any character between {} is a backslash
for i, line in enumerate(lines, 1):
    stripped = line.strip()
    if not stripped:
        continue
    
    # Check for f-strings (f"..." or f'...')
    for col, ch in enumerate(stripped):
        if ch == 'f' and col + 1 < len(stripped) and stripped[col + 1] in ('"', "'"):
            quote = stripped[col + 1]
            j = col + 2
            depth = 0
            while j < len(stripped):
                c = stripped[j]
                if c == '{':
                    depth += 1
                elif c == '}':
                    depth -= 1
                elif c == '\\' and depth > 0:
                    print(f"Line {i}: Backslash in f-string expression: {stripped[:120]}")
                    break
                elif c == quote and depth == 0:
                    break
                j += 1
            else:
                # Check if this is a multi-line f-string continued on next lines
                if stripped.endswith(('(', '\\')):
                    pass  # Multi-line, skip for now

print("Scan complete")
