import sys


def main(argv: list[str] | None = None) -> int:
    """Main CLI dispatcher: parse subcommand and delegate."""
    if argv is None:
        argv = sys.argv[1:]
    
    if not argv or argv[0] in ("--help", "-h", "help"):
        print("Leasora CLI - Lease analysis tool")
        print()
        print("Usage: leasora <subcommand> [args]")
        print()
        print("Subcommands:")
        print("  ingest   Ingest a lease PDF")
        print("  query    Ask a question about leases")
        print("  eval     Run evaluation suites")
        print()
        print("Run 'leasora <subcommand> --help' for subcommand help.")
        return 0
    
    subcommand = argv[0]
    subcommand_argv = argv[1:]
    
    if subcommand == "ingest":
        from leasora_api.cli.ingest import run
        return run(subcommand_argv)
    elif subcommand == "query":
        from leasora_api.cli.query import run
        return run(subcommand_argv)
    elif subcommand == "eval":
        from leasora_api.cli.eval import run
        return run(subcommand_argv)
    else:
        print(f"Error: Unknown subcommand '{subcommand}'", file=sys.stderr)
        print("Run 'leasora --help' for usage.", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
