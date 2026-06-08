"""Scan our eval files for backslash in f-string expressions (invalid in Python<3.12)."""
import re, sys

files = [
    'python3.11libs/edini/eval/evaluator.py',
    'python3.11libs/edini/eval/log_parser.py',
    'python3.11libs/edini/eval/models.py',
    'python3.11libs/edini/eval/store.py',
    'python3.11libs/edini/eval/__init__.py',
]

found_any = False

for fname in files:
    with open(fname, 'r', encoding='utf-8') as f:
        content = f.read()

    lines = content.split('\n')

    for i, line in enumerate(lines, 1):
        # Look for f-strings and examine what's inside {}
        in_expr = False
        brace_depth = 0
        skip_next = False
        for col, ch in enumerate(line):
            if skip_next:
                skip_next = False
                continue
            if ch == '\\':
                skip_next = True
                continue
            if ch == '{' and not in_expr:
                # Check if preceded by f (f-string)
                if col > 0 and line[col-1] in ('f', 'F'):
                    in_expr = True
                    brace_depth = 1
                # Also check if we're already in a string
                elif in_expr:
                    brace_depth += 1
            elif ch == '{' and in_expr:
                brace_depth += 1
            elif ch == '}' and in_expr:
                brace_depth -= 1
                if brace_depth == 0:
                    in_expr = False

        # Now let's use a different approach: find f-strings by scanning for backslash inside braces
        # Actually the above doesn't work well. Let's use regex.
        
        # Find backslash inside braces in f-strings
        # Pattern: an f" or f' string where \ is between { and }
        fstring_pattern = re.compile(r'f["\'].*?\{[^}]*\\[^}]*\}')
        for m in fstring_pattern.finditer(line):
            found_any = True
            print(f'{fname}:{i}: Potential issue: {line.strip()[:120]}')

if not found_any:
    print('No backslash-in-fstring-expression issues found in any eval files.')
