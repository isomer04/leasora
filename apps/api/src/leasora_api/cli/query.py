import argparse
import asyncio
import json
import sys

from leasora_api.core.exceptions import LeasoraError
from leasora_api.services.rag.query_service import rag_service


def run(argv: list[str] | None = None) -> int:
    """Query subcommand: `leasora query "<question>" --lease-id ID`"""
    parser = argparse.ArgumentParser(
        prog="leasora query",
        description="Ask a question about a lease.",
    )
    parser.add_argument("question", help="Question to ask about the lease")
    parser.add_argument(
        "--lease-id",
        required=True,
        help="Lease ID to query (a lease previously ingested with `leasora ingest`)",
    )

    if argv is None:
        argv = sys.argv[1:]

    try:
        args = parser.parse_args(argv)
    except SystemExit as e:
        return e.code if isinstance(e.code, int) else 0

    try:
        response = asyncio.run(rag_service.answer_question(args.lease_id, args.question))
    except LeasoraError as error:
        print(f"Error: {error.message}", file=sys.stderr)
        return 1

    result = {
        "question": args.question,
        "lease_id": args.lease_id,
        "answer": response.answer,
        "confidence": response.confidence,
        "sources": [source.model_dump() for source in response.sources],
    }
    print(json.dumps(result, indent=2))

    return 0
