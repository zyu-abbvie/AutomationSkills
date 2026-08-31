# Jython in this estate

How to write Ignition project scripts that match this estate's house style and survive the gateway JVM. Every count and path below comes from the two on-disk backups; all project `.py` under `<Proj>/ignition/` runs as Jython 2.7 inside the gateway JVM, not CPython.

Path shorthand used throughout (both are absolute roots):

| Token | Expands to |
|---|---|
| `$DEV` | `$DEV` |
| `$PROD` | `$PROD` |

## Read this first

1. A Java exception thrown by an Ignition/JDBC/java.io call **does not** get caught by `except Exception`. This is the single biggest source of silent failure here. See [Java exceptions](#java-exceptions-escape-except-exception).
2. `.value` is used 573 times; `.quality` 38 times, in 6 files. Bad-quality reads silently yield `None`. Check quality in new code, do not mass-rewrite old code.
3. Tag history paths are hardcoded to the **prod** gateway (`ignition-wz02163d`) 347 times, including inside dev projects. Do not copy those literals into anything new without parameterising.
4. Indentation is tabs in 107 files and 4 spaces in 61. Match the file you are in. Never reindent a file wholesale.
5. `except Exception, e:` (Python 2.5 syntax) is live in 23 places. It is valid Jython. Do not "modernise" it — a Python 3 formatter will reject the file and produce a diff nobody asked for.

## Jython 2.7 language constraints

| Constraint | Reality in the estate | Evidence |
|---|---|---|
| No f-strings | 0 f-strings in any gateway script. `.format()` is used 100 times. The only 3 f-strings on disk are in `$DEV/PT_Opt/remove_status_bar.py`, a host-side CPython helper that never runs in the JVM. | `$DEV/PT_Opt/ignition/script-python/Report/code.py:20` `equipment_base = "{0}/{1}/{2}/VO{3}".format(...)` |
| `print` is a statement | 20 occurrences of bare `print x`. Harmless but the output goes to wrapper.log, not to a caller. | `$DEV/TSWG/ignition/script-python/Report/code.py:29` `print row` and `:40` `print body` |
| `/` is floor division on ints | **0** files use `from __future__ import division`. So `/` truncates. Guarded code writes `float(n)` or `60.0`. | Broken: `$DEV/TSWG/ignition/script-python/Report/code.py:33` `datetime.datetime.fromtimestamp(objects[2]/1000)` — truncates epoch-millis to whole seconds. Same line in the FC_Parent, Extruder-AP31-4-273 and FC02-R8-125-1 copies. Correct: `$DEV/PT_Opt/intelligent_monitoring_implementation.py:318` `mean_x = sum(x) / float(n)`; `:191` `... / 60.0` |
| `str` vs `unicode` are distinct | `unicode()` / `.encode('utf-8')` is mandatory before handing text to a `java.io` writer or to MQTT publish. Publish takes **bytes**. | `$DEV/ForcedDeg_Project/ignition/script-python/forceddeg/code.py:195` `return unicode(v) if not isinstance(v, unicode) else v`; `:533` `fos.write(payload.encode('utf-8'))`; `$DEV/LNP_opt/ignition/script-python/shared/PumpControl/code.py:94-97` |
| `long` exists and is needed | Epoch-millis exceeds 32-bit `int` on some paths; the estate uses `long()` deliberately, with a comment. | `$PROD/Camera_Demo/com.inductiveautomation.webdev/resources/image_list/doGet.py:26` `return long(v)  # Jython: use long`; `$DEV/ForcedDeg_Project/.../forceddeg/code.py:444` `nxt = long(g.get(_SHARE_BACKOFF_KEY, 0))` |
| `java.util.Date` vs `datetime.datetime` | Ignition APIs hand back `java.util.Date`. Both are in use and converted ad hoc. Prefer the `system.date.*` layer (~130 calls) over hand conversion. | `$DEV/TFF_Parent/com.inductiveautomation.webdev/resources/TFFReport/doGet.py:14` `from java.util import Date`; `$DEV/MCP_Tools/com.inductiveautomation.mcp/tools/queryTagHistory/onToolCalled.py:6` `Date = __import__('java.util').util.Date`; duck-typed bridge at `$DEV/MCP_Tools/ignition/script-python/mcp_helpers/code.py:88` `ts_ms = ts.getTime() if ts is not None and hasattr(ts, "getTime") else None` |

Java class import has two spellings in use. Both work; pick one per file:

```python
import java.lang.Exception as JavaException          # $DEV/MCP_Tools/ignition/script-python/maximo/code.py:18
JLang = __import__('java.lang').lang                 # $DEV/MCP_Tools/com.inductiveautomation.mcp/tools/addPitfall/onToolCalled.py:7
```

The `__import__` form is required in MCP `onToolCalled.py` and other resources where top-of-file imports beyond `import system` are awkward; see `$DEV/MCP_Tools/com.inductiveautomation.mcp/tools/evalScript/onToolCalled.py:5-12`, which pulls `os`, `re`, `sys`, `time`, `traceback`, `StringIO`, `__builtin__` and `java.lang.System` that way inside the function body.

## Java exceptions escape `except Exception`

Jython's `Exception` is `exceptions.Exception`. `java.lang.Exception` is not a subclass of it. Anything raised from JDBC, `java.io`, `ProcessBuilder`, `ClassLoader.loadClass`, or an Ignition system function that fails inside Java will fly straight past your handler and out of the script. In a gateway timer that means the timer dies with a stack trace you have to go find in wrapper.log; in a WebDev resource it means a 500.

This is documented in exactly **one** place in the estate. Copy it.

```python
# $DEV/MCP_Tools/com.inductiveautomation.mcp/tools/addPitfall/onToolCalled.py:7, 61-73
JLang = __import__('java.lang').lang
...
    try:
        system.db.runPrepUpdate(
            "INSERT INTO dbo.MCP_Pitfalls (category, symptom, ...) VALUES (?,?,?,?,?,'proposed',?,?,?,?,?)",
            [category, symptom, ...], DB)
    except JLang.Exception, je:
        # Java exceptions escape `except Exception` in Jython, so catch java.lang.Exception
        return fail("insert rejected by the database: " + str(je.getMessage() or je)[:300])
    except:
        return fail("insert failed for an unknown reason")
```

Two things to note. `except JLang.Exception, je:` uses the Python-2 comma form because `JLang.Exception` is a Java class and the `as` form is not used at this call site — either syntax parses in Jython 2.7, but the comma form is what is on disk, so a diff that changes it is noise. And `je.getMessage()` is the Java accessor; `str(je)` alone often gives you a class name with no detail.

The **double-handler** shape — a typed/`Exception` handler followed by a bare `except:` — is the belt-and-braces version, used where the block must never be allowed to break its caller:

```python
# $DEV/MCP_Tools/com.inductiveautomation.mcp/tools/evalScript/onToolCalled.py:116-192 (abridged)
    # Must never be able to break evalScript itself, so the
    # whole block is guarded -- including a bare except, because java.lang
    # exceptions escape Jython's "except Exception".
    kb = None
    try:
        ...
    except Exception:
        kb = None
    except:
        kb = None
```

Write the double handler around any block that touches JDBC, the filesystem, or a Java library and whose failure must not take the whole entry point down. Everywhere else, catch `java.lang.Exception` explicitly and **log it** — a bare `except: pass` is the estate's worst habit (see [Logging](#logging-and-error-handling)).

Places that need this and do not have it, so you know what you are walking into: `$DEV/ForcedDeg_Project/ignition/script-python/forceddeg/code.py:278-330` (ProcessBuilder, `java.lang.System`, only `except Exception`) and `$DEV/EquipmentScheduler/ignition/script-python/scheduler/code.py:122` (`loadClass('com.microsoft.sqlserver.jdbc.SQLServerDriver')`).

## The `system.*` vocabulary you will actually use

Counts are textual occurrences across both backups. Note this misses PROD gateway event scripts, which are gzipped Java-serialised blobs at `<Proj>/ignition/event-scripts/data.bin` in 11 projects and invisible to grep.

| Call | Count | A real call site |
|---|---|---|
| `system.tag.readBlocking` | 512 | `$DEV/PT/ignition/script-python/Report/code.py:12` |
| `system.tag.writeBlocking` | 142 | `$DEV/Martillac-Alarms/ignition/timer/OpcAutoHeal/handleTimerEvent.py:37` |
| `system.net.sendEmail` | 93 | `$DEV/PT/ignition/script-python/Report/code.py:98` |
| `system.util.getLogger` | 81 | `$DEV/LNP_opt/ignition/script-python/shared/PumpControl/code.py:107` |
| `system.dataset.setValue` | 73 | `$DEV/ABC-Alarms/ignition/timer/Update_Tables_500L/handleTimerEvent.py:122` |
| `system.date.now` | 56 | `$DEV/Ruben-Test-App/ignition/timer/Snapshot/handleTimerEvent.py:40` |
| `system.tag.queryTagHistory` | 52 | `$DEV/PT_Opt/ignition/script-python/Report/code.py:94` |
| `system.dataset.toCSV` | 51 | `$DEV/PT/ignition/script-python/Report/code.py:48` |
| `system.date.secondsBetween` | 40 | `$DEV/PT/ignition/script-python/Report/code.py:14` |
| `system.db.runPrepUpdate` | 33 | `$DEV/MCP_Tools/ignition/script-python/maximo/code.py:17` |
| `system.db.runPrepQuery` | 25 | `$DEV/MCP_Tools/com.inductiveautomation.mcp/tools/addPitfall/onToolCalled.py:75` |
| `system.date.format` | 17 | `$DEV/LargeScaleFC/ignition/script-python/largescalefc/code.py` |

Tag I/O plus dataset plus date is where nearly all the lines go. `system.db.*` is a minority.

## Tag reads: quality is a real defect, not a style preference

The house one-liner is:

```python
# $DEV/PT/ignition/script-python/Report/code.py:12
Start = system.tag.readBlocking(Batch_Start_Time)[0].value
```

No guard. If the tag is missing, stale, or the provider is down, `.value` is `None` and the `None` propagates into date math, CSV output and emails without a single log line. `.value` appears 573 times; `.quality` appears 38 times across only 6 files (LNP_opt `PumpControl` and `ValveControl`, PT_Opt `Report` and its monitoring scripts).

The correct pattern, from the estate:

```python
# $DEV/LNP_opt/ignition/script-python/shared/PumpControl/code.py:150-161
	try:
		tagPath = buildTagPath(session, pumpId, "PumpStatus")
		result = system.tag.readBlocking([tagPath])[0]

		if result.quality.isGood():
			return (result.value, "Good", None)
		else:
			return (None, str(result.quality), "Bad tag quality: " + str(result.quality))

	except Exception as e:
		error_msg = "Failed to read pump status: " + str(e)
		return (None, "Error", error_msg)
```

The fail-fast variant, where the caller is a report that should abort rather than emit garbage:

```python
# $DEV/PT_Opt/ignition/script-python/Report/code.py:33-43
		start_result = system.tag.readBlocking([batch_start_tag])[0]
		...
		if not start_result.quality.isGood():
			raise ValueError("Failed to read batch start time: {0}".format(start_result.quality))
```

Guidance, explicitly:

- **New code:** always check `result.quality.isGood()` before using `result.value`. Return an `(value, error)` tuple or raise — do not return a bare `None` that looks like a legitimate reading.
- **Existing code:** do **not** mass-rewrite the 573 `.value` call sites. It is a large untestable diff across 40+ dev and 114 prod projects, and each site has its own idea of what a failure should do. Add the check when you are already changing that function for another reason, and say so in the change.

## `readBlocking` string-vs-list: leave old sites alone

The documented API takes lists and returns a list. 76 call sites pass a bare string literal instead and rely on coercion; 46 use the list form. Writes are worse — 28 scalar `writeBlocking` calls in one 202-line timer.

```python
# String/scalar form, 76 sites. $DEV/ABC-Alarms/ignition/timer/Update_Tables_5443/handleTimerEvent.py:116
SP = system.tag.readBlocking('[default]ABC/WaveRockers/5443/Temp1/SP')[0].value
# Scalar write. $DEV/ABC-Alarms/ignition/timer/Update_Tables_50L/handleTimerEvent.py:8
system.tag.writeBlocking(tagPaths, Hi)

# List form, 46 sites. $DEV/Ruben-Test-App/ignition/timer/Snapshot/handleTimerEvent.py:40
system.tag.writeBlocking([lastRunTagPath], [system.date.now()])
```

Rules:

- **New code:** always lists, both arguments. `system.tag.readBlocking([p])[0]`, `system.tag.writeBlocking([p], [v])`.
- **Editing old code:** do not "fix" a string call to a list call as a drive-by. Wrapping the path in a list changes the return shape at some call sites and the surrounding `[0].value` / `[0]` indexing breaks silently or throws in the gateway, not at edit time. Convert only when you are rewriting the function and can re-read every index in it.

`system.tag.writeAsync` occurs **once** estate-wide, against 142 `writeBlocking`. Writes here are blocking by convention. Do not introduce async writes into an existing timer or tag-change script — the ordering assumptions around them are implicit.

## Database access

There is exactly one connection name in scripted code: `"SQLServer"`, assigned to a module constant and passed as the **trailing positional argument**.

```python
# $DEV/MCP_Tools/com.inductiveautomation.mcp/tools/addPitfall/onToolCalled.py:10
DB = "SQLServer"
# :62-68
system.db.runPrepUpdate(
    "INSERT INTO dbo.MCP_Pitfalls (category, symptom, cause, fix, evidence, status, "
    "keywords, project, gateway, ign_version, author) "
    "VALUES (?,?,?,?,?,'proposed',?,?,?,?,?)",
    [category, symptom, str(cause or ""), ...], DB)
```

| Call | Count | Verdict |
|---|---|---|
| `system.db.runPrepUpdate` | 33 | House default for writes. Use it. |
| `system.db.runPrepQuery` | 25 | House default for reads. Use it. |
| `system.db.runScalarPrepQuery` | 7 | Fine for single-value reads. |
| `system.db.runNamedQuery` | 11 | Confined to the copy-pasted `Report` libraries. Called by bare name plus a params dict: `system.db.runNamedQuery("Get_Annotations", params)` — `$DEV/TSWG/ignition/script-python/Report/code.py:24`. Named queries are duplicated per project, not shared (`Get_Annotations` exists 47x). |
| `system.db.runQuery` | 6 | String-concatenated SQL, no parameters. Do not add more; replace when you touch one. |

**Dataset consumption is positional and brittle.** The mainstream idiom is `system.dataset.toPyDataSet(ds)` then `row[1]`, `objects[2]` — which silently returns the wrong column the moment a query's `SELECT` list changes. Example: `$DEV/PT_Opt/gateway_timer_reasoning_engine.py:91` `values = [row[1] for row in system.dataset.toPyDataSet(history)]`.

There is no list-of-dicts helper in the estate. Two places build dicts by column name, and that is the pattern to write:

```python
# $DEV/MCP_Tools/ignition/script-python/mcp_helpers/code.py:72-73, 87
	headers = [str(ds.getColumnName(i)) for i in range(ds.getColumnCount())]
	idx = {h.lower(): i for i, h in enumerate(headers)}
	...
	ts = ds.getValueAt(r, ts_col) if ts_col is not None else None
```

Raw-JDBC variant using `ResultSetMetaData`: `$DEV/EquipmentScheduler/ignition/script-python/scheduler/code.py:151` `cols = [meta.getColumnLabel(i + 1) for i in range(meta.getColumnCount())]`.

## Tag history provider paths are hardcoded to PROD

```python
# $DEV/PT_Opt/ignition/script-python/Report/code.py:23  -- this is a DEV project
historian_base = "[SQLServer/ignition-wz02163d:mqtt engine]{0}/{1}/{2}/VO{3}".format(site, building, roomfloorbench, equipment)
```

`"[SQLServer/ignition-wz02163d:mqtt engine]"` appears **347 times** and `"[SQLServer/ignition-wz02163d:default]"` **110 times**, including inside dev projects. The bracket is `[historyProvider/datasource:tagProvider]` and `ignition-wz02163d` names the **prod** gateway. Any dev-project report using these literals is reading prod history — and any project promoted from dev to prod carries the literal along and happens to keep working, which is why nobody has noticed.

Live tag reads use `[default]` (484x) or `[MQTT Engine]` (49x) and are fine.

For new code: put the bracketed prefix in a module constant so it can be changed in one place, and derive the gateway name rather than typing it. Do not silently repoint existing report libraries — some of them are deliberately reporting on prod data from a dev project.

## Logging and error handling

`system.util.getLogger("<Name>")` with a **hardcoded string literal**. 81 call sites. No logger is derived from the project name programmatically. Two naming conventions:

| Style | Used by | Example |
|---|---|---|
| `"<Component>"` for a whole library | older/bigger libs | `ForcedDeg` (15 calls), `PT_Monitoring` (8), `LargeScaleFC` (3), `PumpControl` (2) |
| `"<component>.<operation>"` dotted per function | newer code — write this | `webdev.camera.mqtt` (5), `flex01.liveMonitor` (2), `scheduler.timer`, `maximo_refresh.timer`, `PT_Opt.Report`, `martillac.autoheal` |

The two antipatterns you will meet:

**1. Swallowed exceptions.** 62 blocks are an `except` whose body is only `pass` or `continue`; 134 bare `except:` clauses against 170 `except Exception`. These produce no log line at all, which makes them the single hardest thing to debug here. Citations: `$DEV/ForcedDeg_Project/ignition/script-python/forceddeg/code.py:92, 193, 304, 316, 362, 438, 509`; `$DEV/FLEX01-R8-320-3-1/ignition/script-python/flex01/code.py:857, 1312, 1331, 1350, 1352`; `$DEV/EquipmentScheduler/ignition/script-python/maximo_refresh/code.py:81, 141`.

**2. Email-the-traceback, log nothing.** The copy-pasted `Report` package (33 copies) wraps the whole function in one `try`, then on any failure catches bare `except:` and emails `str(sys.exc_info())` to a hardcoded personal address list. No logger call, no re-raise — the gateway log stays clean while the report fails.

```python
# $DEV/PT/ignition/script-python/Report/code.py:100-103
	except:
		email_list = "dave.sutherland@abbvie.com, ruben.quintero@abbvie.com"
		body = "Experiment: " + str(...) + "\n" + "Error: " + str(sys.exc_info())
		system.net.sendEmail(smtpProfile="SMTP_ABBVIE", fromAddr="ignition@email.com", subject="TFF Report Failure", body=body, html=0, to=email_list)
```

Same block at `$DEV/TSWG/ignition/script-python/Report/code.py:53-56`, and in all 33 `Report` copies.

**Write this instead** — named logger, log before returning, return a `(value, error)` tuple so the caller can decide:

```python
# $DEV/LNP_opt/ignition/script-python/shared/PumpControl/code.py:92-108
	try:
		if isinstance(value, str):
			payload = value.encode("utf-8")
		elif isinstance(value, (int, float)):
			payload = str(value).encode("utf-8")
		else:
			payload = value
		system.cirruslink.engine.publish(broker, topic, payload, qos, retain)
		return (True, None)
	except Exception as e:
		error_msg = "MQTT Publish Failed: " + str(e)
		system.util.getLogger("PumpControl").error(error_msg)
		return (False, error_msg)
```

Add the `except JLang.Exception, je:` arm to that shape whenever the body touches JDBC, files or a Java library. Keep email for **operational** alerting (a batch failed, a task is due) — not as your error channel.

## Indentation

107 files indent with literal tabs, 61 with 4 spaces. Mixing them inside one file is a `TabError` at import time, and Ignition will report it as a broken script resource with no obvious cause. Detect before editing:

```bash
head -40 <file> | grep -cP '^\t'   # nonzero => tabs
```

Match the file. Never reindent a file you are only partly changing.

## Threading

| Call | Count | Notes |
|---|---|---|
| `system.util.invokeAsynchronous` | 2 | Both correct: fire-and-forget of a local `run()` closure. `$PROD/LNP_418/ignition/script-python/LNP/code.py:302` and `:338`. Note `time.sleep` inside the thread at `:298` — that is safe there because it is off the calling thread. |
| `system.util.invokeLater` | 2 | Both **wrong**. `$DEV/LNP_opt/ignition/script-python/shared/PumpControl/code.py:200-201` `# Small delay to ensure flow rate is set` / `system.util.invokeLater(lambda: None, 100)`; `$DEV/LNP_opt/.../shared/ValveControl/code.py:112`. |
| `system.util.sleep` | 2 | Rare. Blocks the calling thread. |

`invokeLater` schedules onto the client/Designer event-dispatch thread and returns immediately. In gateway scope there is no EDT to schedule onto, and it does not block the caller in any scope — so the intended delay never happens and the MQTT flow-rate setpoint and the start command are published back-to-back. If you need a gap between two gateway actions, either `time.sleep` inside an `invokeAsynchronous` closure (as LNP_418 does) or restructure so the second action is triggered by a tag-change on the first one's confirmation.

Unsafe in gateway scope generally: anything Perspective/Vision session-scoped (`system.gui.*`, `system.nav.*`, `system.perspective.*` without an explicit `sessionId`), and blocking the timer thread past its period — a fixed-rate timer whose script overruns will queue and pile up.

## Libraries worth reading before you write

| Library | Lines | Read it for | Do not copy |
|---|---|---|---|
| `$DEV/LNP_opt/ignition/script-python/shared/PumpControl/code.py` | 360 | The best overall model: constant tables (`PUMP_LIMITS`, `PUMP_LOCATIONS`) at `:7-25`, Args/Returns docstrings, quality-checked reads `:151-160`, `(ok, error)` tuple returns, utf-8 MQTT publish wrapper with named-logger error path `:78-108`, precheck-before-actuate gate `:164-210`. Siblings `shared/ValveControl` (interlocks) and `shared/SafetyChecks` (206 lines) are the same style. | Line 201, the `invokeLater`-as-sleep bug. |
| `$DEV/MCP_Tools/ignition/script-python/mcp_helpers/code.py` | 342 | The most Jython-literate code here: explicit `import system`, `from java.lang import System as JSystem` / `from java.io import File as JFile`, defensive multi-shape attribute probing `:24-51`, header docstring stating scope and import path (`Gateway scope. Imported as: from mcp_helpers import code as h`) `:1-16`, and the only correct Dataset-to-dict-by-column-name reader `:62-110`. Its sibling MCP tool scripts hold the estate's only `java.lang.Exception` handling. | Nothing. Note the project is duplicated on disk at `$DEV/MCP_Tools/MCP_Tools/...` — cite the outer path. |
| `$DEV/ForcedDeg_Project/ignition/script-python/forceddeg/code.py` | 2089 | How to document a gateway timer entry point: `:1-10` gives exact Designer wiring (`Project > Gateway Event Scripts > Timer / Threading: Shared / Delay: 60000ms / Fixed Rate / Script: project.forceddeg.checkDueTasks()`), `:16-21` module constants, `:26` raw string for a Windows path, `:28-35` a comment explaining *why* a constraint exists. Correct unicode handling. | Its exception handling — 8+ `except: pass` in the first 520 lines. |

Runner-up for a design rationale in comments: `$DEV/EquipmentScheduler/ignition/script-python/scheduler/code.py:1-20`, which explains why it bypasses the gateway's own `SQLServer` connection, and `:73-151` for raw JDBC via `ClassLoader` and `ResultSetMetaData`.

## Two things that will bite an automated reader

**PROD gateway event scripts are invisible to grep.** 11 projects on WZ02163D store them as a gzipped Java-serialised blob at `<Proj>/ignition/event-scripts/data.bin`. Any `grep --include='*.py'` audit misses all prod gateway timer/scheduled/tag-change Jython. Most blobs are 242-244 byte empty stubs; real content lives in `$PROD/RIO_IP_Tracker/ignition/event-scripts/data.bin` (750 B) and `$PROD/TFF-Teller-BSL3-2-1/ignition/event-scripts/data.bin` (863 B). Decompress with `gzip` before searching.

**One script library hardcodes OAuth client secrets** as plain module-level dict literals for multiple environments: `$DEV/MCP_Tools/ignition/script-python/maximo/code.py` around lines 22-38. A naive `sed -n '1,50p'` of that file puts them in your context. Exclude that path from bulk reads and from any pitfall/KB capture; read from line 40 onward if you need the rest of the module.
