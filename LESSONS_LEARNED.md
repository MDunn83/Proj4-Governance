# Lessons Learned — Proj4 Governance Tool Build

Captured from the Claude Code session that produced `proj4_governance_workflow.json`. These lessons apply to any n8n workflow built with Groq LLMs.

---

## 1. n8n Merge Node: Parameter Name Is Not What the Docs Suggest

**Problem:** The Merge node was configured with `"combinationMode": "mergeByPosition"` in the JSON. On import, n8n silently defaulted to "Match Fields" mode, which failed because no matching fields existed.

**Fix:** The correct parameter is `"combineBy": "combineByPosition"` — a different key name and a different value format.

**Takeaway:** Always export a working workflow from the n8n UI and diff it against your generated JSON. The UI export is the ground truth for parameter names.

---

## 2. Groq Model Availability Changes Without Notice

**Problem:** `gemma2-9b-it` was used initially and produced clean output. It was deprecated mid-build with no warning.

**Fix:** Switched to `qwen/qwen3-32b`, which is on the current free tier (60 RPM).

**Takeaway:** Check the Groq model list before starting a build. Free-tier models turn over frequently. Verify programmatically if possible.

---

## 3. qwen3 Produces `<think>` Blocks by Default

**Problem:** qwen/qwen3-32b outputs extended reasoning wrapped in `<think>...</think>` tags before its answer. These blocks appeared in the cleaned response and in classifier output.

**Fix:** Add `"reasoning_effort": "none"` to every Groq API request body. Also add a regex strip in the Code node as a safety net:
```javascript
text = text.replace(/<think>[\s\S]*?<\/think>/gi, '');
```

**Takeaway:** Any model with a reasoning/thinking mode must have that mode explicitly disabled unless you need the reasoning trace.

---

## 4. LLMs Can Emit Literal `\n` Strings, Not Newlines

**Problem:** The model returned responses containing the two-character sequence backslash-n (`\n`) as literal text rather than as a newline character.

**Fix:** Add this replacement in the Code node that processes LLM output:
```javascript
text = text.replace(/\\n/g, ' ');
```
In the JSON file this must be written as `\\\\n` to survive the double-escaping.

**Takeaway:** Never assume LLM output is clean. Always run it through a sanitization Code node before passing it downstream.

---

## 5. Batching Must Be Applied to All HTTP Request Nodes

**Problem:** Batching was added only to the Generate Response node during initial planning. The two classifier nodes were left without batch limits and hit Groq's 60 RPM cap immediately on the first test run.

**Fix:** Add `options.batching.batch.batchSize: 1` and `batchInterval: 4000` to every HTTP Request node that calls the Groq API.

**Takeaway:** When rate limits apply to an API, every node that calls that API needs batching — not just the first one.

---

## 6. `response_format: json_object` Breaks With Thinking Mode and Low `max_tokens`

**Problem:** The classifier nodes used `response_format: { type: "json_object" }` and `max_tokens: 60`. When the model entered thinking mode, the thinking tokens consumed the entire budget, leaving nothing for the JSON response. The result was `failed_generation: ""`.

**Fix:** Remove `response_format` entirely. Increase `max_tokens` to 200. Instruct the model in the prompt to return raw JSON only. Add a Code node with try/catch + regex fallback to parse the output.

**Takeaway:** `response_format: json_object` and reasoning models do not mix safely. Rely on prompt instructions and robust parsing instead.

---

## 7. Parallel Classification Requires a Merge Node, Not Sequential Chaining

**Problem:** Initial design wired Classify Query → Classify Response sequentially. This meant the response classifier received query classification output as its input context, and the IF node only checked one classification result.

**Fix:** Fan out from the Strip Markdown node to both classifier nodes simultaneously. Each Parse Code node outputs uniquely named fields (`queryClass` vs `responseClass`). A Merge node (by position) rejoins the two branches before the Assemble Row node.

**Takeaway:** When two operations are independent, run them in parallel. Fan-out in n8n is a single node wired to two downstream nodes in the same connection array.

---

## 8. Merge Node Field Conflicts Will Silently Drop Data

**Problem:** In an early parallel design, both Parse nodes output a field called `classification`. After merging, only one value survived.

**Fix:** Each Parse node must output uniquely named fields. Parse Query Result outputs `queryClass`, `queryDomain`, etc. Parse Response Result outputs `responseClass`, `responseDomain`, etc. Zero field name overlap.

**Takeaway:** Before designing a Merge, list every field each branch will output and confirm there are no collisions.

---

## 9. Cross-Node References Break After HTTP Request Nodes

**Problem:** `$('Set Start Time').item.json` was referenced deep in the chain, after multiple HTTP Request nodes. HTTP Request nodes replace the entire item with the response body, stripping all upstream context.

**Fix:** The Strip Markdown Code node (immediately after the first HTTP node) explicitly carries all needed context fields onto its output item: `userId`, `query`, `startTime`, `genUsage`. All downstream nodes reference `$json.*` instead of cross-node refs.

**Takeaway:** After any HTTP Request node, treat all upstream data as gone. Carry forward everything you need in an explicit Code or Edit Fields node.

---

## 10. IF Node Conditions Do Not Always Import Correctly

**Observation:** The n8n skill file documents this and it held true: IF node conditions sometimes import with the left side showing as a static value instead of an expression. The condition appears to be `"true" equals "SENSITIVE"` rather than `{{ $json['response class'] }} equals "SENSITIVE"`.

**Fix:** After importing, open the Route to Review IF node and manually verify all four conditions show as expressions. Re-enter any that show as static values.

**Takeaway:** IF node conditions are the single most import-fragile part of an n8n workflow. Always check them first when a workflow runs but routes incorrectly.

---

## 11. Validate JSON Before Committing

**Problem:** Several bugs (wrong typeVersions, bad escaping, wrong parameter names) made it into committed workflow versions and were only caught during live testing.

**Fix:** A `validate_workflow.py` script was created to check: JSON validity, node typeVersions, Code node modes, HTTP typeVersions, connection name resolution, and absence of cross-node refs after HTTP nodes.

**Takeaway:** Automated pre-commit validation catches a class of errors that are invisible from reading the JSON. Run it before every commit.

---

## 12. Google Sheets Node `__rl` Format Is Required

**Observation:** The Google Sheets node (typeVersion 4) requires spreadsheet and sheet references in the `__rl` resource-locator format:
```json
"documentId": { "__rl": true, "value": "<id>", "mode": "id" },
"sheetName": { "__rl": true, "value": "<name>", "mode": "name" }
```
Using a plain string value causes the node to show an error on import.

**Takeaway:** Always use the `__rl` format for Google Sheets node references in typeVersion 4.
