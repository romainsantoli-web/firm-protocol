# 🔒 Security Audit Report — crewAI

**Date:** 2026-03-06 23:03 UTC  
**Repository:** `/private/tmp/crewAI`  
**Scanner:** FIRM Security Firm (4 agents, copilot-pro)  
**Protocol:** firm-protocol v1.1.0

## Executive Summary

| Metric | Value |
|--------|-------|
| Total findings | **13** |
| Critical | **0** |
| High | **7** |
| Medium | **6** |
| Low | **0** |
| Info | **0** |
| Duplicates filtered | 0 |
| Overall risk score | **88/100** |

## Findings

### 🟠 HIGH (7)

#### 1. GitHub Actions run step uses untrusted interpolation

| Field | Value |
|-------|-------|
| Severity | **HIGH** |
| CWE | [CWE-78](https://cwe.mitre.org/data/definitions/78.html) |
| Location | `.github/workflows/publish.yml:20` |
| Found by | static-analyzer |

**Description:** Semgrep detected possible shell injection via direct interpolation of GitHub context in a run step. Untrusted input may reach shell commands.

**Remediation:** Assign untrusted GitHub context values to env vars and reference them safely with quoted variables in run scripts; avoid direct ${{ ... }} interpolation in shell.

---

#### 2. XML parsing with stdlib may permit XXE

| Field | Value |
|-------|-------|
| Severity | **HIGH** |
| CWE | [CWE-611](https://cwe.mitre.org/data/definitions/611.html) |
| Location | `lib/crewai-tools/src/crewai_tools/rag/loaders/xml_loader.py:45` |
| Found by | static-analyzer |

**Description:** Use of xml.etree parsing on potentially untrusted XML can allow XXE-style attacks and entity expansion abuse.

**Remediation:** Replace stdlib XML parser usage with defusedxml equivalents and disable external entity resolution.

---

#### 3. Code interpreter executes arbitrary Python with exec in unsafe mode

| Field | Value |
|-------|-------|
| Severity | **HIGH** |
| CWE | [CWE-94](https://cwe.mitre.org/data/definitions/94.html) |
| Location | `lib/crewai-tools/src/crewai_tools/tools/code_interpreter_tool/code_interpreter_tool.py:384-388` |
| Found by | code-scanner |

**Description:** The tool explicitly supports unsafe execution by installing requested libraries on the host and executing provided Python code with exec. This is direct arbitrary code execution if untrusted users or prompts can reach this path.

```
for library in libraries_used:
    os.system(f"pip install {library}")
...
exec(code, {}, exec_locals)
```

**Impact:** Full host compromise in unsafe mode, including arbitrary command execution, file access, persistence, and credential theft.

**Remediation:** Disable unsafe mode for untrusted workloads. Execute code only inside a hardened sandbox/container with strict allowlists, resource limits, and package installation controls. Never pass untrusted code directly to exec on the host.

---

#### 4. Host package installation uses shell command with unsanitized library names

| Field | Value |
|-------|-------|
| Severity | **HIGH** |
| CWE | [CWE-78](https://cwe.mitre.org/data/definitions/78.html) |
| Location | `lib/crewai-tools/src/crewai_tools/tools/code_interpreter_tool/code_interpreter_tool.py:384-386` |
| Found by | code-scanner |

**Description:** Package names are interpolated directly into an os.system shell command. If an attacker can influence libraries_used, shell metacharacters can inject arbitrary OS commands.

```
for library in libraries_used:
    os.system(f"pip install {library}")
```

**Impact:** Arbitrary command execution on the host system before Python code execution even begins, potentially allowing remote compromise through crafted dependency names.

**Remediation:** Do not use os.system with interpolated input. Invoke pip via subprocess.run with a fixed argument list, disable shell=True, and validate package names against a strict regex/allowlist.

---

#### 5. Potential SQL injection via raw formatted query

| Field | Value |
|-------|-------|
| Severity | **HIGH** |
| CWE | [CWE-89](https://cwe.mitre.org/data/definitions/89.html) |
| Location | `lib/crewai-tools/src/crewai_tools/tools/singlestore_search_tool/singlestore_search_tool.py:323` |
| Found by | static-analyzer |

**Description:** Semgrep detected raw SQL execution/formatting that may allow SQL injection if attacker-controlled input is concatenated.

**Remediation:** Use parameterized queries (bind parameters) or SQLAlchemy expression APIs/text() with named parameters; avoid string formatting for SQL.

---

#### 6. JWT decoded without signature verification

| Field | Value |
|-------|-------|
| Severity | **HIGH** |
| CWE | [CWE-287](https://cwe.mitre.org/data/definitions/287.html) |
| Location | `lib/crewai/src/crewai/cli/authentication/utils.py:27` |
| Found by | static-analyzer |

**Description:** JWT is decoded with verify=False, which bypasses token integrity checks and may allow forged tokens.

**Remediation:** Enable JWT signature verification and validate issuer/audience/expiry using trusted keys before accepting token claims.

---

#### 7. Pickle deserialization on local file can lead to code execution

| Field | Value |
|-------|-------|
| Severity | **HIGH** |
| CWE | [CWE-502](https://cwe.mitre.org/data/definitions/502.html) |
| Location | `lib/crewai/src/crewai/utilities/file_handler.py:168-170` |
| Found by | code-scanner |

**Description:** The file handler loads serialized data with pickle.load. Pickle is unsafe for untrusted input because crafted pickle payloads can execute arbitrary Python code during deserialization.

```
with open(self.file_path, "rb") as file:
    try:
        return pickle.load(file)
```

**Impact:** If an attacker can modify or replace the backing file, opening it will execute arbitrary code in the application's context.

**Remediation:** Replace pickle with a safe serialization format such as JSON for untrusted or semi-trusted data. If pickle must be used, ensure the file is stored in a strictly access-controlled location and authenticated before loading.

---


### 🟡 MEDIUM (6)

#### 1. XML loader uses standard ElementTree parser on untrusted XML

| Field | Value |
|-------|-------|
| Severity | **MEDIUM** |
| CWE | [CWE-611](https://cwe.mitre.org/data/definitions/611.html) |
| Location | `lib/crewai-tools/src/crewai_tools/rag/loaders/xml_loader.py:37-40` |
| Found by | code-scanner |

**Description:** The XML loader parses attacker-supplied XML with Python's standard xml.etree.ElementTree parser. Standard XML parsers may be vulnerable to XXE-style behaviors or denial of service issues such as entity expansion, depending on parser behavior and input.

```
if content.strip().startswith("<"):
    root = fromstring(content)
else:
    root = parse(source_ref).getroot()
```

**Impact:** Parsing hostile XML could disclose local resources or cause parser resource exhaustion, impacting availability and potentially confidentiality.

**Remediation:** Use defusedxml equivalents for XML parsing and reject dangerous constructs such as DTDs and external entities in untrusted XML.

---

#### 2. Arxiv PDF download accepts arbitrary URL schemes via urllib

| Field | Value |
|-------|-------|
| Severity | **MEDIUM** |
| CWE | [CWE-918](https://cwe.mitre.org/data/definitions/918.html) |
| Location | `lib/crewai-tools/src/crewai_tools/tools/arxiv_paper_tool/arxiv_paper_tool.py:158-162` |
| Found by | code-scanner |

**Description:** The download helper retrieves a caller-provided URL using urllib without enforcing an allowlist of schemes or hosts. urllib supports non-HTTP schemes such as file://, which can turn this into a local file read or SSRF primitive if inputs are attacker-controlled.

```
def download_pdf(self, pdf_url: str, save_path: str):
    ...
    urllib.request.urlretrieve(pdf_url, str(save_path))
```

**Impact:** Attackers may trigger requests to internal services or local file retrieval, potentially exposing sensitive internal resources or causing unexpected file writes.

**Remediation:** Restrict downloads to https URLs from expected arXiv hosts, parse and validate the URL before retrieval, and reject file:// and other unsafe schemes.

---

#### 3. SingleStore schema introspection builds SQL with unquoted table names

| Field | Value |
|-------|-------|
| Severity | **MEDIUM** |
| CWE | [CWE-89](https://cwe.mitre.org/data/definitions/89.html) |
| Location | `lib/crewai-tools/src/crewai_tools/tools/singlestore_search_tool/singlestore_search_tool.py:318-323` |
| Found by | code-scanner |

**Description:** The code interpolates table names directly into a SQL statement during schema introspection. Although it checks membership against existing table names first, the query still uses string formatting instead of identifier-safe quoting or parameterization. If an attacker can influence schema names or exploit edge cases in identifier handling, this pattern weakens SQL injection defenses and can break on unusual identifiers.

```
for table in tables:
    if table not in existing_tables:
        raise ValueError(...)
    cursor.execute(f"SHOW COLUMNS FROM {table}")
```

**Impact:** Potential SQL injection or malformed query execution in environments where table names are attacker-influenced or database metadata is not fully trusted. At minimum, this creates brittle SQL handling.

**Remediation:** Avoid f-string SQL construction for identifiers. Validate table names against a strict identifier allowlist and quote them using the database driver's identifier-escaping facilities, or fetch column metadata through information_schema queries using bound parameters where possible.

---

#### 4. JWT helper decodes tokens without signature verification

| Field | Value |
|-------|-------|
| Severity | **MEDIUM** |
| CWE | [CWE-287](https://cwe.mitre.org/data/definitions/287.html) |
| Location | `lib/crewai/src/crewai/cli/authentication/utils.py:24-27` |
| Found by | code-scanner |

**Description:** The helper parses JWT claims with signature verification explicitly disabled before full validation. Although the token is later verified, this still processes attacker-controlled claims from an untrusted token and uses them in error handling paths.

```
_unverified_decoded_token = jwt.decode(
    jwt_token, options={"verify_signature": False}
)
```

**Impact:** Tampered JWT claims may influence logs or exception messages and can create unsafe assumptions if the unverified payload is reused in future code changes. This weakens authentication hygiene around token handling.

**Remediation:** Do not decode attacker-supplied JWTs with verify_signature disabled unless absolutely necessary. If diagnostic claim access is needed, avoid trusting or reusing these values and prefer surfacing generic validation errors.

---

#### 5. Flow visualization injects HTML via innerHTML

| Field | Value |
|-------|-------|
| Severity | **MEDIUM** |
| CWE | [CWE-79](https://cwe.mitre.org/data/definitions/79.html) |
| Location | `lib/crewai/src/crewai/flow/visualization/assets/interactive.js:1431` |
| Found by | code-scanner |

**Description:** The visualization script writes assembled HTML directly into the DOM using innerHTML. If any portion of content derives from untrusted metadata, source code, or node labels without robust escaping, this creates a DOM XSS sink.

```
this.elements.content.innerHTML = content;
```

**Impact:** An attacker who can influence rendered flow metadata could execute arbitrary JavaScript in the viewer's browser, leading to credential theft or malicious actions in the local browser context.

**Remediation:** Avoid innerHTML for dynamic content. Build DOM nodes with textContent/createElement, or apply strict contextual escaping/sanitization to every untrusted field before insertion.

---

#### 6. Dynamic SQL update query constructed from attacker-controlled field names

| Field | Value |
|-------|-------|
| Severity | **MEDIUM** |
| CWE | [CWE-89](https://cwe.mitre.org/data/definitions/89.html) |
| Location | `lib/crewai/src/crewai/memory/storage/kickoff_task_outputs_storage.py:135-145` |
| Found by | code-scanner |

**Description:** While values are parameterized, column names are taken directly from kwargs keys and concatenated into the SQL statement. If untrusted input can reach kwargs, an attacker could alter the SQL structure through crafted field names.

```
for key, value in kwargs.items():
    fields.append(f"{key} = ?")
...
query = f"UPDATE latest_kickoff_task_outputs SET {', '.join(fields)} WHERE task_index = ?"
```

**Impact:** Potential SQL injection against the local SQLite database, possibly allowing unauthorized column updates or query manipulation if caller-controlled keys are accepted upstream.

**Remediation:** Restrict updatable fields to a fixed allowlist and reject unknown keys before building the statement. Keep values parameterized and never concatenate untrusted identifier names into SQL.

---


## Agent Performance

| Agent | Model | Tasks | Success Rate | Tokens | Findings |
|-------|-------|-------|-------------|--------|----------|
| security-director | claude-opus-4.6 | 2 | 100% | 342,023 | 0 |
| code-scanner | gpt-5.4 | 1 | 100% | 732,852 | 9 |
| static-analyzer | gpt-5.3-codex | 1 | 100% | 183,771 | 4 |
| report-synthesizer | gemini-3.1-pro-preview | 1 | 100% | 72,829 | 0 |

**Total tokens:** 1,331,475  
**Estimated cost:** $6.9296 (copilot-pro = $0.00 actual)

## Scan Metadata

| Field | Value |
|-------|-------|
| Duration | 7m 30s |
| Repository | `/private/tmp/crewAI` |
| Agents | 4 (copilot-pro) |
| Models | claude-opus-4.6, gpt-5.4, gpt-5.3-codex, gemini-3.1-pro |
| Token budget | 1,000,000 per agent |
| Total findings | 13 unique + 0 duplicates |

---

*Report generated by FIRM Security Firm — firm-protocol v1.1.0*