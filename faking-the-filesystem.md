# Faking the filesystem in tests

Findings from evaluating [pyfakefs](https://github.com/pytest-dev/pyfakefs) as a
replacement for the hand-written I/O doubles this repo's tests currently use.
Nothing here has been acted on; the work it describes is queued in
[tasks.md](tasks.md#fake-filesystem). Measurements were taken against pyfakefs
6.2.0 on Python 3.14.6.

## What prompted it

`session_analysis`'s two fetchers take an injected
`write: Callable[[Path, bytes], None]` so their tests need no disk. The
parameter exists only for testing — no production caller passes one — and the
test double that replaces it reimplements the real writer, so the real one
(including its `mkdir(parents=True)`, which every mirrored capture directory
depends on) is never exercised.

That is the general shape of the problem: an I/O seam cut into a production
signature for the benefit of tests, which then test the seam rather than the
code.

## What pyfakefs is

An in-memory filesystem that patches Python's filesystem modules — `os`,
`os.path`, `pathlib`, `shutil`, `io`, and builtin `open`. Under pytest, a test
requests the `fs` fixture and every filesystem call inside it goes to memory:
the code under test's calls, and those of any library it calls. It lives under
the `pytest-dev` organization, the same one that maintains pytest, and its CI
covers Python 3.10 through 3.14 on Linux, macOS, and Windows.

The property that matters: **production code is unchanged**. The real writer
runs, the real `mkdir` runs, and the injected seam can be deleted.

## Why latency is not the deciding factor

The obvious objection is that disk in tests accumulates across a suite. Measured
for the shape these tests actually have — 156 small files written into mirrored
directory trees, then read back:

```
writing:  8.8 ms
reading:  2.2 ms
total:   11.0 ms
```

Against a suite of 661 tests running in about 3 seconds, that is roughly 0.4%.
Real temporary directories would be affordable here. The argument for pyfakefs
is therefore **not speed** — it is that the `write` parameter comes off three
public signatures and the real I/O paths start being exercised.

## What survives of the "restructure, don't mock" rule

`~/.claude/rules/testing.md` says to restructure an entry point to accept a
stream rather than mocking a file. The reason is that hand-written mocks are
brittle — not that streams are better design in themselves. A maintained fake
that reproduces the whole filesystem is far less brittle than a hand-written
double, so that reasoning does not carry over to it.

The distinction worth keeping is different, and `extraction.transcribe_sheet`
illustrates it: it takes `image: Image.Image`, a decoded domain object rather
than a path or a stream. That is the real principle — **take the decoded thing,
not a handle to where it lives** — and it is orthogonal to faking the
filesystem. Stream flexibility itself buys nothing here: scans arrive as files
in the ingest inbox, and no production caller would ever supply anything else.

Where code's subject genuinely _is_ the filesystem — directory trees, path
derivation, mirrored layouts — there is no stream to inject, and inventing an
injection seam produced the problem this document opens with.

## Granularity and how it is controlled

The `fs` fixture is function-scoped. Each test gets an empty fake filesystem;
tests that do not request it see the real disk untouched.

Turning it on for a whole directory, via `conftest.py`:

```python
@pytest.fixture(autouse=True)
def fake_filesystem(fs):
  """Every test here runs against the fake filesystem unless it opts out."""
  return fs
```

Opting a module or a single test back out — define a fixture of the same name
closer to the test, and the nearer one wins:

```python
@pytest.fixture
def fake_filesystem() -> None:
  return None
```

Stepping out mid-test, either imperatively or as a context manager:

```python
fs.pause()
...  # the real disk
fs.resume()

with Pause(fs):
  ...  # the real disk
```

Making specific real files visible, which is usually better than pausing since
it lasts the whole test and stays read-only:

```python
fs.add_real_file(path)
fs.add_real_directory(directory)  # for a whole fixture tree
```

`fs_class`, `fs_module`, and `fs_session` exist for wider scopes, and share
state across the tests within that scope — a file one test writes is still there
in the next. Function scope is the right default; the wider ones also do not
nest with `fs`, which causes reference-counting problems.

## Limits, with the behavior each actually produces

Three documented limits matter here. They fail in very different ways, and the
middle one is worse than its documentation suggests.

### Anything that shells out — fails loudly

`subprocess` and `multiprocessing` cannot start a process against a fake
filesystem. Running `git rev-parse` under `fs` raises immediately:

```
OSError: [Errno 9] Bad file descriptor: '7'
```

Cryptic, but an exception at the call site. `private_paths` shells out to git to
locate the checkout, so **that one function stays on a real filesystem** — which
costs nothing, since the git call now sits in a thin wrapper of its own and the
path logic it feeds is tested separately. That split is the general answer here:
a subprocess boundary wants separating, not faking.

### Pillow writing a JPEG — fails silently, and worse

`Image.save()` to a `.jpg` **raises nothing** and reports success. The file is
created at zero bytes, and the encoded image is written to standard output
instead, because Pillow's JPEG encoder writes through a C-level file descriptor
that the patching never sees. The failure only surfaces later:

```
pillow jpeg save: wrote 0 bytes
pillow jpeg: raised UnidentifiedImageError: cannot identify image file
```

PNG through the same call writes correctly, so this is specific to the C encoder
path. **The image pipeline is excluded by this** — `sheet_dewarp`,
`strip_cutting`, and `extraction` are all Pillow-based.

### `tmp_path` alongside `fs` — loud, but uninformative

`tmp_path` builds a real directory the fake filesystem then hides. Requesting
both errors at fixture setup, before the test body runs, so nothing passes
misleadingly — but the message names neither `fs` nor pyfakefs:

```
OSError: could not create numbered dir with prefix pytest- in
/tmp/pytest-of-<user> after 10 tries
```

This is worth catching properly, and it can be. `request.fixturenames` lists
everything a test pulls in, directly or through another fixture, and is
available before either fixture is built — so a guard in `conftest.py` fires
first regardless of declaration order:

```python
@pytest.fixture(autouse=True)
def guard_against_a_real_temporary_path(request: pytest.FixtureRequest) -> None:
  """Fail a test that asks for both a fake filesystem and a real temp path."""
  requested = set(request.fixturenames)
  if 'fs' in requested and 'tmp_path' in requested:
    pytest.fail(
      'a test cannot use both `fs` and `tmp_path`: the fake filesystem '
      'hides the real directory `tmp_path` needs. Write into the fake '
      'filesystem instead, or drop `fs` and use a real path.'
    )
```

### Others worth knowing

Documented but not exercised here: `sqlite3`, `lxml`, and parts of `pandas`
reach the filesystem through C and are never faked; a module that reads files at
import time is not patched, since the import already happened; a global `Path`
built outside a test never compares equal to a fake one; and the fake filesystem
is never truly empty, as temporary directories always exist.

There is also a non-finding worth recording so it is not re-investigated: a
`PytestCacheWarning` about `/Users/.pytest_cache` seen during this exploration
had nothing to do with pyfakefs. It reproduces with an empty test and no
pyfakefs at all, and comes from invoking pytest with an absolute path from an
unrelated working directory, which makes it derive a rootdir it cannot write to.

## Choosing between a fake and a test seam

Both answer the same question — how does a test stand in for something the code
depends on — and they answer it in different places. A **fake** replaces the
dependency below the API, so production code never learns it is being tested. A
**test seam** takes the dependency as a parameter with a production default, so
the caller decides what it is. That second shape is dependency injection: the
function stops reaching out for what it needs and is handed it instead.

The tradeoff is what each costs:

- A seam puts a parameter on a public signature for the benefit of a caller who
  is not production. It also states the dependency out loud, which reads well
  and is far less brittle than patching a module from the outside, since no test
  couples itself to an internal name.
- A fake keeps the signature clean and exercises the real code path, at the cost
  of a dependency and of patching that reaches wider than the code under test.

**Prefer a fake where one can cover the boundary invisibly; reach for a seam
where the dependency cannot be faked below the API.** In this project:

- The fetchers' injected `write` is the first case. pyfakefs fakes the whole
  filesystem, so the parameter comes off three public signatures and nothing is
  lost — that is what the task queued from this document does.
- `private_paths` is the second. Locating the checkout shells out to git, which
  no filesystem fake can stand in for, so `discover_private_tree` takes a
  `find_checkout` callable instead. A test hands it a directory, and only the
  default implementation goes unexercised — and it holds nothing but the git
  call.

An earlier attempt split that function in two and exported the pure half, which
kept the seam out of the signature but put a function in the public API that
only tests called. A seam that says what it is beats a public function that
quietly exists for testing.

## What this would apply to

Well suited: the traveller and fetcher tests, which move small text files
through plain `pathlib` — `acbl_fetching`, `club_fetching`, `traveller_store`,
`capture_urls`.

`traveller_store_test` is the fullest case: each test writes a capture tree,
runs the store over it, and reads the records back, so both halves of the round
trip are real filesystem work over small text files.

`private_paths_test` is a smaller case of the same thing: three of its tests
build real directories through `tmp_path` only so an existence check has
something to find, and would move to the fake filesystem along with the rest.
Note that they cannot keep `tmp_path` when they do — the two do not mix, which
is what the `conftest.py` guard above is for.

Excluded: anything Pillow-based, and `_this_checkout` for shelling out to git.

## What it would let the API drop

`capture_urls` currently exposes `sidecar_for` and `sidecar_contents` so a
fetcher can hand a path and bytes to its injected writer. With the injection
gone, that pair can collapse into a `write_sidecar` / `read_sidecar` pair that
does its own I/O, which is the shape it wanted in the first place.
