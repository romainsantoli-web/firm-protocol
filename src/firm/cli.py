"""
firm.cli — Command-line interface for the FIRM Protocol.

Provides an interactive way to create and operate a FIRM organization.
Supports both one-shot commands and an interactive REPL mode.

Usage:
    firm init <name>           Create a new FIRM organization
    firm agent add <name>      Add an agent
    firm agent list            List agents
    firm action <agent> <ok|fail> <description>   Record an action
    firm status                Show organization status
    firm propose <agent> <title> <description>    Create a proposal
    firm vote <proposal> <agent> <approve|reject> Vote on a proposal
    firm role define <name> <description>         Define a role
    firm role assign <agent> <role>               Assign a role
    firm evolve propose <agent> <param> <value>   Propose parameter change
    firm market post <agent> <title> <bounty>     Post a market task
    firm amend <agent> <type> <text>              Propose a constitutional amendment
    firm audit                 Run a full audit
    firm repl                  Interactive REPL mode
"""

from __future__ import annotations

import argparse
import json
import sys
import textwrap
from typing import Any

from firm import __version__
from firm.runtime import Firm
from firm.core.types import VoteChoice

# ── Global firm instance for REPL ────────────────────────────────────────────

_firm: Firm | None = None


def _get_firm() -> Firm:
    """Return the global firm instance, or raise."""
    if _firm is None:
        print("Error: No FIRM loaded. Run 'firm init <name>' first.", file=sys.stderr)
        sys.exit(1)
    return _firm


def _json_out(data: Any) -> None:
    """Pretty-print a dict/list as JSON."""
    print(json.dumps(data, indent=2, default=str))


# ── Subcommand handlers ─────────────────────────────────────────────────────


def cmd_init(args: argparse.Namespace) -> None:
    """Create a new FIRM organization."""
    global _firm
    _firm = Firm(name=args.name)
    print(f"FIRM '{args.name}' created (id={_firm.id})")


def cmd_agent_add(args: argparse.Namespace) -> None:
    """Add an agent to the FIRM."""
    firm = _get_firm()
    authority = getattr(args, "authority", 0.5)
    agent = firm.add_agent(args.name, authority=authority)
    print(f"Agent '{agent.name}' added (id={agent.id}, authority={agent.authority:.2f})")


def cmd_agent_list(args: argparse.Namespace) -> None:
    """List agents in the FIRM."""
    firm = _get_firm()
    show_all = getattr(args, "all", False)
    agents = firm.get_agents(active_only=not show_all)
    if not agents:
        print("No agents.")
        return
    print(f"{'Name':<20} {'ID':<40} {'Authority':>10} {'Status':<12} {'Credits':>8}")
    print("-" * 92)
    for a in sorted(agents, key=lambda x: x.authority, reverse=True):
        print(
            f"{a.name:<20} {a.id:<40} {a.authority:>10.4f} "
            f"{a.status.value:<12} {a.credits:>8.1f}"
        )


def cmd_action(args: argparse.Namespace) -> None:
    """Record an agent action."""
    firm = _get_firm()
    success = args.outcome.lower() in ("ok", "success", "true", "1")
    result = firm.record_action(args.agent, success=success, description=args.description)
    if result.get("blocked"):
        print(f"[!] Action blocked: {result['message']}")
        return
    symbol = "+" if success else "-"
    auth = result["authority"]
    print(
        f"[{symbol}] {args.agent}: {args.description} "
        f"(authority {auth['old_value']:.4f} → {auth['new_value']:.4f})"
    )


def cmd_status(args: argparse.Namespace) -> None:
    """Show FIRM status."""
    firm = _get_firm()
    s = firm.status()
    print(f"═══ FIRM: {s['name']} ═══")
    agents = s.get("agents", {})
    print(f"  Agents:          {agents.get('active', 0)} active / {agents.get('total', 0)} total")
    ledger = s.get("ledger", {})
    print(f"  Ledger entries:  {ledger.get('total_entries', 0)}")
    print(f"  Chain valid:     {'✓' if ledger.get('chain_valid', False) else '✗'}")
    constitution = s.get("constitution", {})
    print(f"  Kill switch:     {'ACTIVE ⚠' if constitution.get('kill_switch', False) else 'off'}")
    governance = s.get("governance", {})
    print(f"  Proposals:       {governance.get('total_proposals', 0)}")
    roles = s.get("roles", {})
    print(f"  Roles defined:   {roles.get('defined', roles.get('total_definitions', 0))}")
    memory = s.get("memory", {})
    print(f"  Memory entries:  {memory.get('total_entries', memory.get('entries', 0))}")
    federation = s.get("federation", {})
    print(f"  Federation peers:{federation.get('peer_count', federation.get('peers', 0))}")
    evo = s.get("evolution", {})
    print(f"  Evolution gen:   {evo.get('generation', 0)}")
    mkt = s.get("market", {})
    print(f"  Market tasks:    {mkt.get('total_tasks', 0)}")
    meta = s.get("meta_constitutional", {})
    print(f"  Amendments:      {meta.get('total_amendments', meta.get('total', 0))}")


def cmd_propose(args: argparse.Namespace) -> None:
    """Create a governance proposal."""
    firm = _get_firm()
    proposal = firm.propose(args.agent, title=args.title, description=args.description)
    print(f"Proposal created: {proposal.id}")
    print(f"  Title:  {proposal.title}")
    print(f"  Status: {proposal.status.value}")


def cmd_vote(args: argparse.Namespace) -> None:
    """Vote on a proposal."""
    firm = _get_firm()
    choice_map = {
        "approve": VoteChoice.APPROVE,
        "reject": VoteChoice.REJECT,
        "abstain": VoteChoice.ABSTAIN,
    }
    choice_str = args.choice.lower()
    if choice_str not in choice_map:
        print(f"Error: choice must be approve/reject/abstain, got '{args.choice}'", file=sys.stderr)
        sys.exit(1)
    vote = firm.vote(args.proposal, args.agent, choice_str)
    print(f"Vote recorded: {args.agent} → {choice_str} on {args.proposal}")


def cmd_finalize(args: argparse.Namespace) -> None:
    """Finalize a proposal (advance through governance cycles)."""
    firm = _get_firm()
    result = firm.finalize_proposal(args.proposal)
    print(f"Proposal {args.proposal}: {result.get('status', 'unknown')}")
    if result.get("violations"):
        print(f"  Constitutional violations: {len(result['violations'])}")
        for v in result["violations"]:
            print(f"    - {v}")


def cmd_role_define(args: argparse.Namespace) -> None:
    """Define a new role."""
    firm = _get_firm()
    role = firm.define_role(
        args.name, min_authority=args.min_authority, description=args.description,
    )
    print(f"Role defined: {role.role} (min authority: {role.min_authority:.2f})")


def cmd_role_assign(args: argparse.Namespace) -> None:
    """Assign a role to an agent."""
    firm = _get_firm()
    assignment = firm.assign_role(args.agent, args.role)
    print(f"Role '{args.role}' assigned to {args.agent}")


def cmd_memory_add(args: argparse.Namespace) -> None:
    """Contribute a memory entry."""
    firm = _get_firm()
    entry = firm.contribute_memory(
        agent_id=args.agent,
        content=args.content,
        tags=args.tags.split(",") if args.tags else [],
    )
    print(f"Memory contributed: {entry.id} (tags: {entry.tags})")


def cmd_memory_recall(args: argparse.Namespace) -> None:
    """Recall memories by tag."""
    firm = _get_firm()
    entries = firm.recall_memory(tags=[args.tag])
    if not entries:
        print(f"No memories found for tag '{args.tag}'.")
        return
    for e in entries:
        print(f"  [{e.id[:8]}] ({e.contributor_id}) {e.content[:80]}")


def cmd_audit(args: argparse.Namespace) -> None:
    """Run a full organization audit."""
    firm = _get_firm()
    report = firm.run_audit()
    print(f"═══ Audit Report ═══")
    print(f"  Generated:  {report.generated_at}")
    print(f"  Chain valid: {'✓' if report.chain_valid else '✗'}")
    print(f"  Findings:   {len(report.findings)}")
    for f in report.findings:
        print(f"    [{f.severity}] {f.category}: {f.title}")


def cmd_evolve_propose(args: argparse.Namespace) -> None:
    """Propose a parameter evolution."""
    firm = _get_firm()
    value = float(args.value)
    # Parse "category.param" format (e.g. "authority.learning_rate")
    if "." in args.param:
        category, param_name = args.param.split(".", 1)
    else:
        category, param_name = "authority", args.param
    proposal = firm.propose_evolution(
        proposer_id=args.agent,
        changes=[{"category": category, "parameter_name": param_name, "new_value": value}],
        rationale=f"Change {category}.{param_name} to {value}",
    )
    print(f"Evolution proposal: {proposal.id}")
    print(f"  Parameter: {category}.{param_name} → {value}")
    print(f"  Status:    {proposal.status.value}")


def cmd_evolve_vote(args: argparse.Namespace) -> None:
    """Vote on an evolution proposal."""
    firm = _get_firm()
    approve = args.choice.lower() == "approve"
    firm.vote_evolution(args.proposal, args.agent, approve)
    print(f"Evolution vote: {args.agent} → {args.choice} on {args.proposal}")


def cmd_evolve_apply(args: argparse.Namespace) -> None:
    """Apply an approved evolution."""
    firm = _get_firm()
    changes = firm.apply_evolution(args.proposal)
    print(f"Evolution applied: {len(changes)} parameter(s) changed")
    for c in changes:
        print(f"  {c.parameter}: {c.old_value} → {c.new_value}")


def cmd_market_post(args: argparse.Namespace) -> None:
    """Post a task on the internal market."""
    firm = _get_firm()
    task = firm.post_task(
        poster_id=args.agent,
        title=args.title,
        description=args.description or args.title,
        bounty=float(args.bounty),
    )
    print(f"Market task posted: {task.id}")
    print(f"  Title:  {task.title}")
    print(f"  Bounty: {task.bounty:.1f} credits")


def cmd_market_bid(args: argparse.Namespace) -> None:
    """Place a bid on a market task."""
    firm = _get_firm()
    bid = firm.bid_on_task(args.task, args.agent, float(args.amount))
    print(f"Bid placed: {bid.id} ({args.agent} → {args.amount} credits)")


def cmd_amend(args: argparse.Namespace) -> None:
    """Propose a constitutional amendment."""
    firm = _get_firm()
    kwargs: dict[str, Any] = {
        "proposer_id": args.agent,
        "amendment_type": args.type,
        "rationale": args.rationale or "",
    }
    # Route text to the correct parameter based on amendment type
    if args.type == "add_invariant":
        kwargs["invariant_id"] = args.text.split(":")[0] if ":" in args.text else args.text[:8]
        kwargs["description"] = args.text
        kwargs["keywords"] = []
    elif args.type == "remove_invariant":
        kwargs["invariant_id"] = args.text
    elif args.type in ("add_keywords", "remove_keywords"):
        parts = args.text.split(":", 1)
        kwargs["invariant_id"] = parts[0]
        kwargs["keywords"] = parts[1].split(",") if len(parts) > 1 else []
    amendment = firm.propose_amendment(**kwargs)
    print(f"Amendment proposed: {amendment.id}")
    print(f"  Type: {amendment.amendment_type.value}")
    print(f"  Status: {amendment.status.value}")


def cmd_repl(args: argparse.Namespace) -> None:
    """Interactive REPL mode."""
    global _firm
    print(f"FIRM Protocol v{__version__} — Interactive Mode")
    print("Type 'help' for commands, 'quit' to exit.\n")

    if _firm is None:
        name = input("Enter FIRM name: ").strip() or "my-firm"
        _firm = Firm(name=name)
        print(f"FIRM '{name}' created.\n")

    while True:
        try:
            line = input("firm> ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nGoodbye.")
            break

        if not line:
            continue
        if line in ("quit", "exit", "q"):
            print("Goodbye.")
            break
        if line == "help":
            _repl_help()
            continue

        parts = line.split(maxsplit=3)
        cmd = parts[0].lower()

        try:
            if cmd == "status":
                cmd_status(argparse.Namespace())
            elif cmd == "agents":
                cmd_agent_list(argparse.Namespace(all=False))
            elif cmd == "audit":
                cmd_audit(argparse.Namespace())
            elif cmd == "add" and len(parts) >= 2:
                authority = float(parts[2]) if len(parts) >= 3 else 0.5
                cmd_agent_add(argparse.Namespace(name=parts[1], authority=authority))
            elif cmd == "action" and len(parts) >= 3:
                desc = parts[3] if len(parts) >= 4 else ""
                cmd_action(
                    argparse.Namespace(agent=parts[1], outcome=parts[2], description=desc)
                )
            elif cmd == "propose" and len(parts) >= 3:
                desc = parts[3] if len(parts) >= 4 else parts[2]
                cmd_propose(argparse.Namespace(agent=parts[1], title=parts[2], description=desc))
            elif cmd == "vote" and len(parts) >= 4:
                cmd_vote(
                    argparse.Namespace(proposal=parts[1], agent=parts[2], choice=parts[3])
                )
            elif cmd == "params":
                _json_out(_firm.get_firm_parameters())
            elif cmd == "ledger":
                entries = _firm.ledger.get_entries()
                for e in entries[-10:]:
                    print(f"  [{e['action']}] {e['agent_id']}: {e['description'][:60]}")
                if len(entries) > 10:
                    print(f"  ... ({len(entries) - 10} more entries)")
            else:
                print(f"Unknown command: {line}. Type 'help' for commands.")
        except Exception as e:
            print(f"Error: {e}")


def _repl_help() -> None:
    """Print REPL help."""
    print(
        textwrap.dedent("""\
        Commands:
          add <name> [authority]     Add an agent (default authority 0.5)
          action <agent> ok|fail <desc>  Record an action
          agents                     List active agents
          status                     Show FIRM status
          propose <agent> <title> [desc] Create a governance proposal
          vote <proposal> <agent> approve|reject  Vote on a proposal
          params                     Show current parameters
          ledger                     Show last 10 ledger entries
          audit                      Run full audit
          help                       Show this help
          quit                       Exit
        """)
    )


# ── Argument parser ──────────────────────────────────────────────────────────


def build_parser() -> argparse.ArgumentParser:
    """Build the CLI argument parser."""
    parser = argparse.ArgumentParser(
        prog="firm",
        description="FIRM Protocol — Self-Evolving Autonomous Organization Runtime",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")

    sub = parser.add_subparsers(dest="command", help="Available commands")

    # init
    p_init = sub.add_parser("init", help="Create a new FIRM organization")
    p_init.add_argument("name", help="Organization name")

    # agent
    p_agent = sub.add_parser("agent", help="Agent management")
    agent_sub = p_agent.add_subparsers(dest="agent_cmd")

    p_add = agent_sub.add_parser("add", help="Add an agent")
    p_add.add_argument("name", help="Agent name")
    p_add.add_argument("--authority", type=float, default=0.5, help="Initial authority (0-1)")

    p_list = agent_sub.add_parser("list", help="List agents")
    p_list.add_argument("--all", action="store_true", help="Include inactive agents")

    # action
    p_action = sub.add_parser("action", help="Record an agent action")
    p_action.add_argument("agent", help="Agent ID")
    p_action.add_argument("outcome", choices=["ok", "fail"], help="Action outcome")
    p_action.add_argument("description", help="Action description")

    # status
    sub.add_parser("status", help="Show FIRM status")

    # propose
    p_propose = sub.add_parser("propose", help="Create a governance proposal")
    p_propose.add_argument("agent", help="Proposer agent ID")
    p_propose.add_argument("title", help="Proposal title")
    p_propose.add_argument("description", help="Proposal description")

    # vote
    p_vote = sub.add_parser("vote", help="Vote on a proposal")
    p_vote.add_argument("proposal", help="Proposal ID")
    p_vote.add_argument("agent", help="Voter agent ID")
    p_vote.add_argument("choice", choices=["approve", "reject", "abstain"])

    # finalize
    p_finalize = sub.add_parser("finalize", help="Finalize a proposal")
    p_finalize.add_argument("proposal", help="Proposal ID")

    # role
    p_role = sub.add_parser("role", help="Role management")
    role_sub = p_role.add_subparsers(dest="role_cmd")

    p_rdef = role_sub.add_parser("define", help="Define a new role")
    p_rdef.add_argument("name", help="Role name")
    p_rdef.add_argument("description", help="Role description")
    p_rdef.add_argument("--min-authority", type=float, default=0.3, help="Min authority required")

    p_rassign = role_sub.add_parser("assign", help="Assign a role")
    p_rassign.add_argument("agent", help="Agent ID")
    p_rassign.add_argument("role", help="Role name")

    # memory
    p_mem = sub.add_parser("memory", help="Memory management")
    mem_sub = p_mem.add_subparsers(dest="mem_cmd")

    p_madd = mem_sub.add_parser("add", help="Contribute a memory")
    p_madd.add_argument("agent", help="Contributor agent ID")
    p_madd.add_argument("content", help="Memory content text")
    p_madd.add_argument("--tags", default="", help="Comma-separated tags")

    p_mrecall = mem_sub.add_parser("recall", help="Recall memories by tag")
    p_mrecall.add_argument("tag", help="Tag to search")

    # audit
    sub.add_parser("audit", help="Run a full organization audit")

    # evolve
    p_evolve = sub.add_parser("evolve", help="Parameter evolution")
    evo_sub = p_evolve.add_subparsers(dest="evolve_cmd")

    p_eprop = evo_sub.add_parser("propose", help="Propose a parameter change")
    p_eprop.add_argument("agent", help="Proposer agent ID")
    p_eprop.add_argument("param", help="Parameter name")
    p_eprop.add_argument("value", help="New value")

    p_evote = evo_sub.add_parser("vote", help="Vote on evolution")
    p_evote.add_argument("proposal", help="Evolution proposal ID")
    p_evote.add_argument("agent", help="Voter agent ID")
    p_evote.add_argument("choice", choices=["approve", "reject"])

    p_eapply = evo_sub.add_parser("apply", help="Apply approved evolution")
    p_eapply.add_argument("proposal", help="Evolution proposal ID")

    # market
    p_market = sub.add_parser("market", help="Internal market")
    mkt_sub = p_market.add_subparsers(dest="market_cmd")

    p_mpost = mkt_sub.add_parser("post", help="Post a task")
    p_mpost.add_argument("agent", help="Poster agent ID")
    p_mpost.add_argument("title", help="Task title")
    p_mpost.add_argument("bounty", type=float, help="Bounty amount in credits")
    p_mpost.add_argument("--description", default="", help="Task description")

    p_mbid = mkt_sub.add_parser("bid", help="Bid on a task")
    p_mbid.add_argument("task", help="Task ID")
    p_mbid.add_argument("agent", help="Bidder agent ID")
    p_mbid.add_argument("amount", type=float, help="Bid amount")

    # amend
    p_amend = sub.add_parser("amend", help="Propose a constitutional amendment")
    p_amend.add_argument("agent", help="Proposer agent ID")
    p_amend.add_argument("type", choices=["add_invariant", "remove_invariant", "add_keywords", "remove_keywords"])
    p_amend.add_argument("text", help="Amendment text")
    p_amend.add_argument("--rationale", default="", help="Rationale for the amendment")

    # repl
    sub.add_parser("repl", help="Interactive REPL mode")

    return parser


# ── Dispatch ─────────────────────────────────────────────────────────────────

_DISPATCH = {
    "init": cmd_init,
    "action": cmd_action,
    "status": cmd_status,
    "propose": cmd_propose,
    "vote": cmd_vote,
    "finalize": cmd_finalize,
    "audit": cmd_audit,
    "amend": cmd_amend,
    "repl": cmd_repl,
}


def main(argv: list[str] | None = None) -> None:
    """CLI entry point."""
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command is None:
        parser.print_help()
        sys.exit(0)

    # Nested subcommand dispatch
    if args.command == "agent":
        if args.agent_cmd == "add":
            cmd_agent_add(args)
        elif args.agent_cmd == "list":
            cmd_agent_list(args)
        else:
            parser.parse_args(["agent", "--help"])
    elif args.command == "role":
        if args.role_cmd == "define":
            cmd_role_define(args)
        elif args.role_cmd == "assign":
            cmd_role_assign(args)
        else:
            parser.parse_args(["role", "--help"])
    elif args.command == "memory":
        if args.mem_cmd == "add":
            cmd_memory_add(args)
        elif args.mem_cmd == "recall":
            cmd_memory_recall(args)
        else:
            parser.parse_args(["memory", "--help"])
    elif args.command == "evolve":
        if args.evolve_cmd == "propose":
            cmd_evolve_propose(args)
        elif args.evolve_cmd == "vote":
            cmd_evolve_vote(args)
        elif args.evolve_cmd == "apply":
            cmd_evolve_apply(args)
        else:
            parser.parse_args(["evolve", "--help"])
    elif args.command == "market":
        if args.market_cmd == "post":
            cmd_market_post(args)
        elif args.market_cmd == "bid":
            cmd_market_bid(args)
        else:
            parser.parse_args(["market", "--help"])
    elif args.command in _DISPATCH:
        _DISPATCH[args.command](args)
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
