# Python Mutability and Aliasing Guide

This document explains the aliasing hazards that are automatically detected in
this codebase and how to write safe alternatives.

## The Problem

Python variables hold *references*, not value copies.  When you assign a mutable
object (list, dict, set) to multiple names or slots, every name shares the same
underlying object.  A mutation through any one of them is visible through all
the others — this is *aliasing*.

## High-Risk Patterns

### 1. `[mutable] * N`

```python
# Bug: all three slots point to the same inner list
rows = [[]] * 3
rows[0].append(1)
print(rows)  # [[1], [1], [1]] — all three mutated!

# Fix: comprehension creates independent objects
rows = [[] for _ in range(3)]
rows[0].append(1)
print(rows)  # [[1], [], []]
```

The same applies to dicts and sets inside the outer list:

```python
# Bug
buckets = [{}] * 10
# Fix
buckets = [{} for _ in range(10)]
```

### 2. `dict.fromkeys(keys, mutable)`

```python
# Bug: all keys map to the same list object
d = dict.fromkeys(["a", "b", "c"], [])
d["a"].append(1)
print(d)  # {"a": [1], "b": [1], "c": [1]}

# Fix: comprehension gives each key its own list
d = {k: [] for k in ["a", "b", "c"]}
d["a"].append(1)
print(d)  # {"a": [1], "b": [], "c": []}
```

### 3. Mutable default arguments

```python
# Bug (Ruff B006): `items` is shared across all calls that omit the arg
def process(items=[]):
    items.append("x")
    return items

# Fix: use None as sentinel, initialise in the body
def process(items=None):
    if items is None:
        items = []
    items.append("x")
    return items
```

### 4. Late-binding closures in loops

```python
# Bug (Ruff B023): all handlers see the *final* value of `key`
handlers = []
for key in ["a", "b", "c"]:
    handlers.append(lambda: key)

print([h() for h in handlers])  # ["c", "c", "c"]

# Fix: bind the value at creation time via a default argument
handlers = []
for key in ["a", "b", "c"]:
    handlers.append(lambda k=key: k)

print([h() for h in handlers])  # ["a", "b", "c"]
```

### 5. Aliasing a caller's list in constructors

```python
# Bug: mutations to the original list after construction affect the object
class Chain:
    def __init__(self, providers):
        self._providers = providers  # alias!

providers = [a, b]
chain = Chain(providers)
providers.append(c)          # also appended to chain._providers!

# Fix: defensive copy in the constructor
class Chain:
    def __init__(self, providers):
        self._providers = list(providers)
```

### 6. Returning internal mutable state from properties

```python
# Bug: caller can mutate internal state
@property
def items(self):
    return self._items   # caller gets the real list

# Fix: return a copy
@property
def items(self):
    return list(self._items)
```

## Automatic Detection

Three complementary layers enforce these rules:

| Layer | What it catches | When it runs |
|-------|----------------|--------------|
| **Ruff B006** | Mutable default arguments | `make lint`, pre-commit, CI |
| **Ruff B023** | Late-binding closures in loops | `make lint`, pre-commit, CI |
| **Semgrep** (`semgrep/python-mutability.yml`) | `[mutable]*N`, `dict.fromkeys(keys, mutable)` | `make static-checks`, pre-commit, CI |
| **Architecture tests** (`tests/architecture/`) | All patterns above (full AST scan) | `make test`, CI |

Run `make static-checks` locally before pushing to catch Semgrep findings early.

## Code Review Checklist

When reviewing Python code, look for:

- [ ] Any `[x] * N` where `x` is a list, dict, set, or call returning one
- [ ] Any `dict.fromkeys(keys, value)` where `value` is mutable
- [ ] Any function or method that stores a passed-in list/dict/set without copying it
- [ ] Any property or accessor that returns a reference to an internal collection
- [ ] Any lambda or nested `def` inside a loop that references the loop variable
- [ ] Any class with a mutable attribute defined at class scope (not in `__init__`)

## Safe Patterns at a Glance

| Instead of | Use |
|------------|-----|
| `[[]] * N` | `[[] for _ in range(N)]` |
| `[{}] * N` | `[{} for _ in range(N)]` |
| `dict.fromkeys(keys, [])` | `{k: [] for k in keys}` |
| `dict.fromkeys(keys, {})` | `{k: {} for k in keys}` |
| `def f(items=[])` | `def f(items=None)` then `if items is None: items = []` |
| `lambda: key` in a loop | `lambda k=key: k` |
| `self._x = passed_list` | `self._x = list(passed_list)` |
| `return self._x` (from property) | `return list(self._x)` |
