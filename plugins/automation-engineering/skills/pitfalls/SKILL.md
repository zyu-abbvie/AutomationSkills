---
name: pitfalls
description: Search the estate's shared pitfall knowledge base before authoring Perspective views, tag or alarm configuration, named queries or gateway scripts, and record a new entry after diagnosing a non-obvious failure. Use at the start of any Ignition authoring task to check for known silent failures and dead ends, and at the end of any debugging session that uncovered something the next person would waste hours on. Covers how to phrase a symptom so search finds it, what counts as acceptable evidence, and why entries without a control that behaved differently are rejected.
---

# The shared pitfall knowledge base

`dbo.MCP_Pitfalls` on the `SQLServer` connection, exposed through two MCP tools on the dev gateway.
It exists because this estate has repeatedly paid for the same silent failures.

**Search before you author. Contribute after you diagnose.** Both halves matter — a KB that is only
read decays.

## Access reality

| Route | Works? |
|---|---|
| MCP `searchPitfalls` / `addPitfall` on dev | **needs authentication** — anonymous is 403 |
| The dev HTTP API | no route exposes the table |
| Direct SQL from this host | **no** — there is no SQL Server driver installed here |

So you need either an authenticated MCP session to `POST /data/mcp/MCP_Tools`, or a human with
Designer access. Check what you have:

```bash
${CLAUDE_PLUGIN_ROOT}/bin/ign capabilities        # reports the MCP endpoint and whether it is mounted
```

If the MCP server is not reachable, **say so rather than silently skipping the check** — and still
write your finding down for a human to enter. An unrecorded lesson is the failure mode this KB exists
to prevent.

One free path: the `evalScript` MCP tool **automatically attaches a `kb` block** to its response,
matching KB keywords against your code, the error message, the traceback and stderr. If you are
already running a script through it, read that block.

## Searching

```json
{"name": "searchPitfalls", "arguments": {"query": "table renders empty", "limit": 10}}
```

| Parameter | Meaning |
|---|---|
| `query` | symptom keywords. Matched against `symptom`, `cause`, `fix` and `keywords`. |
| `category` | `silent-failure` \| `schema-error` \| `dead-end` \| `designer-only` \| `tooling` \| `standard` |
| `includeProposed` | default `true`. Set `false` for human-verified entries only. |
| `limit` | 1–50, default 10 |

How the search actually behaves — this determines how you should phrase a query:

- Your query is **tokenized on whitespace**. Tokens of two characters or fewer are dropped, and so is
  a stopword list (`the`, `a`, `is`, `does`, `not`, `why`, `how`, `my`, …).
- It first requires **every** remaining token to appear somewhere in the row. If that returns nothing
  **and you supplied more than one token**, it retries with **any** token. The response tells you
  which mode produced the hits via `matchMode`.
- So: **search with two or three distinctive words, not a sentence.** `"alarm never fires"` works;
  `"why does my alarm not fire when the setpoint changes"` reduces to roughly the same tokens but
  pulls in noise on the any-term fallback.
- `superseded` rows are never returned. `proposed` rows are returned unless you opt out.
- Results are ordered `verified` first, then by `occurrences` descending.

Read the results as leads, not facts: **`status: "proposed"` means recorded but not human-verified.**
`occurrences` is how many times the symptom was independently hit — a high count is the strongest
signal in the table.

## Contributing

Call `addPitfall` **after** you have diagnosed something non-obvious.

```json
{"name": "addPitfall", "arguments": {
  "category": "silent-failure",
  "symptom":  "List endpoint returns zero rows although the data exists",
  "cause":    "An unrecognised query parameter is treated as an implicit field filter",
  "fix":      "Send only declared parameter names. The tell is metadata.matching == 0 while metadata.total stays at the real count.",
  "evidence": "GET /data/api/v1/logs?limit=1 returned 1 item; the same request plus &zzzBogus=1 returned 0 items with total unchanged at 54331. Control: a VALID filter that matches nothing drops total to 0 as well, so a large total with matching 0 is specifically the unknown-parameter case.",
  "keywords": "api,query parameter,matching,silent,empty",
  "project":  "MCP_Tools"
}}
```

### The rules the tool enforces

- **`category`, `symptom` and `evidence` are mandatory.** Anything else is rejected outright.
- **`evidence` must be at least 20 characters** and is expected to name **the control that behaved
  differently**. This is the point of the field: a check that cannot fail proves nothing. State the
  test you ran, its result, and the thing you compared against that came out the other way.
- **Deduplication is on the exact `symptom` string.** An identical symptom **increments
  `occurrences`** instead of inserting, and the response comes back with `action: "duplicate"`. That
  is a useful outcome, not an error — it strengthens an existing entry.
- Every entry is stored with `status: "proposed"`. A human promotes it to `verified`. The tool also
  records the gateway hostname, the Ignition version and the author.

### Writing a symptom the next person will find

The symptom is the search key, so **phrase it as how you would notice the problem**, not as the
cause and not as a question.

| Write this | Not this |
|---|---|
| `Table renders empty although the bound data is populated` | `propConfig binding misplaced` |
| `Alarm never fires when the setpoint is crossed` | `Why doesn't my alarm work?` |
| `Named query returns no rows and no error after import` | `Broken query` |

Put the cause in `cause` and the working shape in `fix`. Include the property path or the code that
actually works — a fix the reader can paste is worth more than a description of one.

### Choosing a category

| Category | Use when |
|---|---|
| `silent-failure` | it does nothing and reports no error — the most valuable kind here |
| `schema-error` | it throws something |
| `dead-end` | the approach does not work at all; record it so nobody retries |
| `designer-only` | it can only be done in the Designer, not on disk or over the API |
| `tooling` | the defect is in tooling around Ignition, not Ignition |
| `standard` | a house convention worth stating, rather than a defect |

## What is worth recording

Yes:

- A silent failure — HTTP 200 with no data, a resource the Gateway drops without a log line, a binding
  that keeps its static value.
- Something that cost you more than a few minutes and whose cause was not discoverable from the error.
- A dead end, so the next person does not repeat it.
- A cross-version difference between the 8.1 prod gateway and the 8.3 dev gateway.

No:

- Anything already in this plugin's skills and references — link to it instead.
- A one-off mistake in your own code with no general lesson.
- Anything you have not actually proven. If you did not run a control, you do not yet have evidence;
  either get one or do not submit.

## Do not trust these tools blindly

- Both tools return errors **in-band as data**, not as MCP protocol errors. `addPitfall` returns
  `{"ok": false, "error": …}` inside a normal-looking success envelope. **Check `ok` before believing
  the entry was recorded.**
- `searchPitfalls` returning `count: 0` means nothing matched your tokens. It does **not** mean the KB
  is empty — check `totalInKnowledgeBase` in the same response.
