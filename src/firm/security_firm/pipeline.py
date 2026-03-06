"""Security scan pipeline — orchestrates 4 agents in parallel.

``SecurityPipeline`` creates a FIRM with 4 LLM agents, wires the
repo-scanner tools + MCP bridge, then runs a multi-phase scan:

1. **Map**    — security-director maps the repo structure
2. **Scan**   — code-scanner + static-analyzer + report-synthesizer
                work in parallel via ThreadPoolExecutor
3. **Triage** — security-director recalls all findings, deduplicates
4. **Report** — report-synthesizer generates the final Markdown

Agents communicate via FIRM shared memory (contribute + recall).
"""

from __future__ import annotations

import json
import logging
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

from firm.llm.agent import LLMAgent, create_llm_agent
from firm.llm.tools import Tool, ToolKit, ToolResult
from firm.runtime import Firm
from firm.security_firm.agents import SECURITY_AGENTS
from firm.security_firm.findings import Finding, FindingsDB, Severity
from firm.security_firm.report import ReportGenerator
from firm.security_firm.tools.repo_scanner import make_repo_tools

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Convert repo_scanner dicts → firm Tool objects
# ---------------------------------------------------------------------------

def _register_repo_tools(toolkit: ToolKit, repo_path: str) -> None:
    """Register the 10 repo-scanner tools into *toolkit*."""
    for tool_def in make_repo_tools():
        fn = tool_def["callable"]

        # Wrap each callable to return a ToolResult
        def _make_executor(func: Any, tname: str) -> Any:
            def _exec(**kwargs: Any) -> ToolResult:
                try:
                    result = func(**kwargs)
                    return ToolResult(success=True, output=result)
                except Exception as exc:
                    return ToolResult(
                        success=False,
                        output="",
                        error=f"{tname} failed: {exc}",
                    )
            return _exec

        tool = Tool(
            name=tool_def["name"],
            description=tool_def["description"],
            parameters={
                "type": "object",
                "properties": {
                    k: {"type": "string", "description": v}
                    for k, v in tool_def["parameters"].items()
                },
            },
            execute=_make_executor(fn, tool_def["name"]),
            dangerous=False,
        )
        toolkit.register(tool)


def _register_memory_tools(toolkit: ToolKit, firm: Any, agent_id: str) -> None:
    """Register contribute_memory and recall_memory as real tools."""
    contribute_tool = Tool(
        name="contribute_memory",
        description=(
            "Store a finding or analysis in FIRM shared memory so other agents "
            "can see it. The 'content' should be a JSON string with finding details. "
            "The 'tags' should be a comma-separated list like 'finding,high'."
        ),
        parameters={
            "type": "object",
            "properties": {
                "content": {
                    "type": "string",
                    "description": "The content to store (JSON string recommended).",
                },
                "tags": {
                    "type": "string",
                    "description": "Comma-separated tags, e.g. 'finding,critical'.",
                },
            },
            "required": ["content", "tags"],
        },
        execute=lambda content="", tags="": _exec_contribute(firm, agent_id, content, tags),
        dangerous=False,
    )
    toolkit.register(contribute_tool)

    recall_tool = Tool(
        name="recall_memory",
        description=(
            "Recall entries from FIRM shared memory matching given tags. "
            "Pass a tag to search for, like 'finding' or 'architecture'."
        ),
        parameters={
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Tag to search for in memory.",
                },
                "top_k": {
                    "type": "string",
                    "description": "Max number of results (default 50).",
                },
            },
            "required": ["query"],
        },
        execute=lambda query="", top_k="50": _exec_recall(firm, query, top_k),
        dangerous=False,
    )
    toolkit.register(recall_tool)


def _exec_contribute(firm: Any, agent_id: str, content: str, tags: str) -> ToolResult:
    """Execute contribute_memory tool."""
    try:
        tag_list = [t.strip() for t in tags.split(",") if t.strip()]
        if not tag_list:
            tag_list = ["finding"]
        firm.contribute_memory(agent_id, content, tag_list)
        return ToolResult(success=True, output=f"Stored in memory with tags: {tag_list}")
    except Exception as exc:
        return ToolResult(success=False, output="", error=f"contribute_memory failed: {exc}")


def _exec_recall(firm: Any, query: str, top_k: str) -> ToolResult:
    """Execute recall_memory tool."""
    try:
        k = int(top_k) if top_k else 50
        tags = [t.strip() for t in query.split(",") if t.strip()]
        if not tags:
            tags = ["finding"]
        memories = firm.recall_memory(tags, top_k=k)
        results = []
        for mem in memories:
            results.append({
                "id": mem.id,
                "content": mem.content,
                "tags": mem.tags,
                "weight": round(mem.weight, 3),
                "contributor": str(mem.contributor_id),
            })
        return ToolResult(success=True, output=json.dumps(results, indent=2))
    except Exception as exc:
        return ToolResult(success=False, output="", error=f"recall_memory failed: {exc}")


# ---------------------------------------------------------------------------
# SecurityPipeline
# ---------------------------------------------------------------------------

class SecurityPipeline:
    """Multi-agent security scanning pipeline.

    Usage::

        pipeline = SecurityPipeline(repo_path="/path/to/repo")
        report_md = pipeline.run()
    """

    def __init__(
        self,
        repo_path: str,
        firm_name: str = "SecurityFirm",
        db_path: str = ":memory:",
        use_mcp: bool = True,
        max_workers: int = 3,
    ) -> None:
        self.repo_path = str(Path(repo_path).resolve())
        self.repo_name = Path(self.repo_path).name
        self.firm_name = firm_name
        self.use_mcp = use_mcp
        self.max_workers = max_workers

        # Core state
        self.firm = Firm(firm_name)
        self.db = FindingsDB(db_path)
        self.agents: dict[str, LLMAgent] = {}
        self._start_time = 0.0

        # Wire up
        self._create_agents()

    # ── Setup ───────────────────────────────────────────────────────

    def _create_agents(self) -> None:
        """Instantiate the 4 LLM agents with tools."""
        for spec in SECURITY_AGENTS:
            agent = create_llm_agent(
                firm=self.firm,
                name=spec.name,
                provider_name=spec.provider,
                model=spec.model,
                authority=spec.initial_authority,
                working_dir=self.repo_path,
                config=spec.config,
            )

            # Register repo-scanner tools
            _register_repo_tools(agent._toolkit, self.repo_path)

            # Register contribute_memory / recall_memory tools
            _register_memory_tools(agent._toolkit, self.firm, agent.agent_id)

            # Optionally extend with MCP + Memory OS AI tools
            if self.use_mcp:
                try:
                    from firm.llm.mcp_bridge import extend_agent_with_all_mcp
                    added = extend_agent_with_all_mcp(
                        agent,
                        mcp_categories=spec.mcp_categories,
                        memory_categories=spec.memory_categories,
                    )
                    logger.info(
                        "Ecosystem tools loaded for %s: %d tools "
                        "(mcp=%s, memory=%s)",
                        spec.name, added,
                        spec.mcp_categories, spec.memory_categories,
                    )
                except Exception as exc:
                    logger.warning(
                        "MCP bridge unavailable for %s: %s — continuing without MCP",
                        spec.name, exc,
                    )

            self.agents[spec.name] = agent
            logger.info(
                "Agent '%s' ready (model=%s, authority=%.2f, tokens=%d)",
                spec.name, spec.model, spec.initial_authority,
                spec.config.max_tokens_budget,
            )

    # ── Main execution ──────────────────────────────────────────────

    def run(self) -> str:
        """Execute the full scan pipeline and return the Markdown report."""
        self._start_time = time.time()

        logger.info("=" * 60)
        logger.info("Security Firm — Scanning: %s", self.repo_path)
        logger.info("=" * 60)

        # Phase 1: Director maps the repo
        self._phase_map()

        # Phase 2: Parallel scanning
        self._phase_scan()

        # Phase 3: Director triages
        self._phase_triage()

        # Phase 4: Generate report
        report = self._phase_report()

        elapsed = time.time() - self._start_time
        logger.info("Scan complete in %.1fs — %d unique findings", elapsed, self.db.stats()["unique"])

        return report

    # ── Phase 1: Map ────────────────────────────────────────────────

    def _phase_map(self) -> None:
        """Security director maps the repository structure."""
        logger.info("Phase 1: Mapping repository...")
        director = self.agents["security-director"]

        task = (
            f"Map the repository at '{self.repo_path}'.\n"
            "1. Use repo_tree to list the full structure.\n"
            "2. Use repo_file_stats to get size and language stats.\n"
            "3. Identify the key source directories, config files, and "
            "   dependency files.\n"
            "4. Store your analysis in FIRM memory with tags ['map', 'structure'].\n"
            "5. Summarize what this project does and what to focus on."
        )
        result = director.execute_task(task)
        logger.info(
            "Phase 1 complete: %s (tokens=%d)",
            result.status.value, result.total_tokens,
        )

    # ── Phase 2: Parallel scan ──────────────────────────────────────

    def _phase_scan(self) -> None:
        """Three agents scan in parallel."""
        logger.info("Phase 2: Parallel scanning with 3 agents...")

        tasks = {
            "code-scanner": (
                f"Scan the repository at '{self.repo_path}' for code vulnerabilities.\n"
                "1. Use repo_tree to see the structure.\n"
                "2. Use repo_file_read to review each source file.\n"
                "3. Look for: SQL injection, command injection, XSS, SSRF, "
                "   path traversal, unsafe deserialization, auth bypass, "
                "   race conditions, crypto misuse, info disclosure.\n"
                "4. For each vulnerability, call contribute_memory with content:\n"
                '   JSON: {"title": "...", "severity": "critical|high|medium|low|info",\n'
                '          "file_path": "...", "line_start": N, "line_end": N,\n'
                '          "code_snippet": "...", "cwe_id": N, "description": "...",\n'
                '          "impact": "...", "remediation": "..."}\n'
                "   Tags: ['finding', '<severity>']\n"
                "5. Be thorough but avoid false positives."
            ),
            "static-analyzer": (
                f"Run static analysis on the repository at '{self.repo_path}'.\n"
                "1. Use repo_grep_secrets to find hardcoded secrets.\n"
                "2. Use repo_dependency_audit to check for vulnerable deps.\n"
                "3. Use repo_config_scan to check Docker/CI/env configs.\n"
                "4. Use repo_git_history_secrets to check git history.\n"
                "5. If semgrep is available, use repo_semgrep_run.\n"
                "6. For each finding, call contribute_memory with content:\n"
                '   JSON: {"title": "...", "severity": "...", "file_path": "...",\n'
                '          "line_start": N, "description": "...", "cwe_id": N,\n'
                '          "remediation": "..."}\n'
                "   Tags: ['finding', '<severity>']\n"
                "7. Focus on real secrets, not placeholders/examples."
            ),
            "report-synthesizer": (
                f"Read the repository at '{self.repo_path}' to understand its architecture.\n"
                "1. Use repo_tree and repo_file_stats for overview.\n"
                "2. Read key files: README, main entry points, config files.\n"
                "3. Understand the project's purpose, dependencies, and attack surface.\n"
                "4. Store your architectural analysis in FIRM memory with tags:\n"
                "   ['architecture', 'context']\n"
                "5. This context will help you write the final report later."
            ),
        }

        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            futures = {}
            for agent_name, task_prompt in tasks.items():
                agent = self.agents[agent_name]
                future = executor.submit(agent.execute_task, task_prompt)
                futures[future] = agent_name

            for future in as_completed(futures):
                agent_name = futures[future]
                try:
                    result = future.result()
                    logger.info(
                        "Agent '%s' finished: %s (tokens=%d, tools=%s)",
                        agent_name, result.status.value,
                        result.total_tokens,
                        ", ".join(result.tools_used) if result.tools_used else "none",
                    )
                    # Extract findings from agent's final output text
                    self._extract_findings_from_output(result.output, agent_name)
                    # Extract findings from tool execution results
                    self._extract_findings_from_tool_results(result, agent_name)
                except Exception as exc:
                    logger.error("Agent '%s' failed: %s", agent_name, exc)

    # ── Phase 3: Triage ─────────────────────────────────────────────

    def _phase_triage(self) -> None:
        """Director recalls all findings, deduplicates, triages."""
        logger.info("Phase 3: Triage and deduplication...")
        director = self.agents["security-director"]

        task = (
            "Recall all findings from FIRM memory.\n"
            "1. Use firm recall_memory with query='finding' to get all findings.\n"
            "2. For each finding in memory, parse the JSON content.\n"
            "3. Evaluate each finding:\n"
            "   - Is it a real vulnerability or a false positive?\n"
            "   - What is the correct severity?\n"
            "   - Can you add CVSS vector and score?\n"
            "4. Produce a final JSON list of confirmed findings.\n"
            "5. Store the confirmed list in memory with tags ['triage', 'confirmed']."
        )
        result = director.execute_task(task)
        logger.info(
            "Phase 3 complete: %s (tokens=%d)",
            result.status.value, result.total_tokens,
        )

        # Extract findings from the director's output and populate DB
        self._extract_findings_from_output(result.output, "security-director")

        # Also extract from memory contributions
        self._extract_findings_from_memory()

    def _extract_findings_from_output(self, output: str, agent_name: str) -> None:
        """Parse JSON findings from agent output text."""
        if not output:
            return
        count = 0
        # Try to find JSON arrays in the output
        for match in _find_json_arrays(output):
            try:
                items = json.loads(match)
                for item in items:
                    if isinstance(item, dict) and "title" in item:
                        finding = self._dict_to_finding(item, agent_name)
                        self.db.add(finding)
                        count += 1
            except (json.JSONDecodeError, TypeError):
                continue
        # Try to find individual JSON objects (agents often emit one finding at a time)
        for match in _find_json_objects(output):
            try:
                obj = json.loads(match)
                if isinstance(obj, dict) and "title" in obj:
                    finding = self._dict_to_finding(obj, agent_name)
                    self.db.add(finding)
                    count += 1
            except (json.JSONDecodeError, TypeError):
                continue
        if count:
            logger.info("Extracted %d findings from %s output", count, agent_name)

    def _extract_findings_from_tool_results(
        self, result: "ExecutionResult", agent_name: str,
    ) -> None:
        """Extract findings from tool execution results (contribute_memory calls)."""
        for te in result.tool_executions:
            if te.tool_name == "contribute_memory":
                content = te.arguments.get("content", "")
                if not content:
                    continue
                try:
                    data = json.loads(content) if isinstance(content, str) else content
                    if isinstance(data, dict) and "title" in data:
                        self.db.add(self._dict_to_finding(data, agent_name))
                    elif isinstance(data, list):
                        for item in data:
                            if isinstance(item, dict) and "title" in item:
                                self.db.add(self._dict_to_finding(item, agent_name))
                except (json.JSONDecodeError, TypeError):
                    pass
            # Also try recall_memory results — they may contain finding JSON
            if te.result and te.result.output:
                self._extract_findings_from_output(te.result.output, agent_name)

    def _extract_findings_from_memory(self) -> None:
        """Pull findings from FIRM shared memory."""
        count = 0
        for tag in ["finding", "vulnerability", "triage", "confirmed"]:
            try:
                memories = self.firm.recall_memory([tag], top_k=200)
                for mem in memories:
                    # MemoryEntry is a dataclass — access .content, not dict
                    content = getattr(mem, "content", "") or (
                        mem.get("content", "") if isinstance(mem, dict) else str(mem)
                    )
                    try:
                        data = json.loads(content) if isinstance(content, str) else content
                        if isinstance(data, dict) and "title" in data:
                            agent = data.get("found_by", getattr(mem, "contributor_id", "memory"))
                            if hasattr(agent, "value"):  # AgentId
                                agent = agent.value or "memory"
                            finding = self._dict_to_finding(data, str(agent))
                            self.db.add(finding)
                            count += 1
                        elif isinstance(data, list):
                            for item in data:
                                if isinstance(item, dict) and "title" in item:
                                    self.db.add(self._dict_to_finding(item, "memory"))
                                    count += 1
                    except (json.JSONDecodeError, TypeError, AttributeError):
                        continue
            except Exception as exc:
                logger.warning("Could not extract from memory (tag=%s): %s", tag, exc)
        if count:
            logger.info("Extracted %d findings from shared memory", count)

    @staticmethod
    def _dict_to_finding(d: dict, default_agent: str) -> Finding:
        """Convert a dict (from agent output) to a Finding."""
        severity = d.get("severity", "medium")
        try:
            sev = Severity(severity.lower())
        except ValueError:
            sev = Severity.MEDIUM
        return Finding(
            title=d.get("title", "Untitled finding"),
            description=d.get("description", ""),
            severity=sev,
            file_path=d.get("file_path", ""),
            line_start=int(d.get("line_start", 0)),
            line_end=int(d.get("line_end", 0)),
            code_snippet=d.get("code_snippet", ""),
            cwe_id=int(d.get("cwe_id", 0)),
            cvss_vector=d.get("cvss_vector", ""),
            cvss_score=float(d.get("cvss_score", 0.0)),
            impact=d.get("impact", ""),
            reproduction_steps=d.get("reproduction_steps", ""),
            remediation=d.get("remediation", ""),
            found_by=d.get("found_by", default_agent),
            tags=d.get("tags", []),
        )

    # ── Phase 4: Report ─────────────────────────────────────────────

    def _phase_report(self) -> str:
        """Generate the final Markdown report."""
        logger.info("Phase 4: Generating report...")

        elapsed = time.time() - self._start_time

        # Collect agent stats
        agent_stats = []
        for name, agent in self.agents.items():
            stats = agent.get_stats()
            stats["findings_count"] = len(self.db.by_agent(name))
            agent_stats.append(stats)

        generator = ReportGenerator(
            db=self.db,
            repo_name=self.repo_name,
            repo_path=self.repo_path,
            agent_stats=agent_stats,
            scan_duration_s=elapsed,
        )

        return generator.generate()

    # ── Accessors ───────────────────────────────────────────────────

    @property
    def findings(self) -> list[Finding]:
        return self.db.all(exclude_status=["duplicate", "false_positive"])

    @property
    def stats(self) -> dict:
        return self.db.stats()


# ---------------------------------------------------------------------------
# JSON extraction helpers
# ---------------------------------------------------------------------------

def _find_json_arrays(text: str) -> list[str]:
    """Extract JSON array substrings from text."""
    results: list[str] = []
    depth = 0
    start = -1
    for i, ch in enumerate(text):
        if ch == "[":
            if depth == 0:
                start = i
            depth += 1
        elif ch == "]":
            depth -= 1
            if depth == 0 and start >= 0:
                candidate = text[start : i + 1]
                if len(candidate) > 10:  # skip trivially small
                    results.append(candidate)
                start = -1
    return results


def _find_json_objects(text: str) -> list[str]:
    """Extract top-level JSON object substrings `{...}` from text."""
    results: list[str] = []
    depth = 0
    start = -1
    in_string = False
    escape_next = False
    for i, ch in enumerate(text):
        if escape_next:
            escape_next = False
            continue
        if ch == "\\" and in_string:
            escape_next = True
            continue
        if ch == '"' and not escape_next:
            in_string = not in_string
            continue
        if in_string:
            continue
        if ch == "{":
            if depth == 0:
                start = i
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0 and start >= 0:
                candidate = text[start : i + 1]
                if len(candidate) > 20:  # skip trivially small
                    results.append(candidate)
                start = -1
    return results
