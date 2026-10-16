"""Unified command-line interface for Pithon."""

import argparse
import os
import sys
from pithon.engine import LlamaEngine
from pithon.pipe import run_pipe
from pithon.chat import run_chat
from pithon.server import run_server

DEFAULT_MODEL = os.environ.get("PITHON_MODEL", "models/qwen2.5-0.5b-instruct-q4_k_m.gguf")

def build_parser() -> argparse.ArgumentParser:
    """Construct command-line argument parser."""
    parser = argparse.ArgumentParser(
        prog="pithon",
        description="Pithon: Ultra-lightweight SLM runtime for Raspberry Pi 4/5"
    )
    
    subparsers = parser.add_subparsers(dest="subcommand", help="Operational mode")

    # Pipe subcommand
    pipe_parser = subparsers.add_parser("pipe", help="Process piped stdin (logs, text) and stream output")
    pipe_parser.add_argument("prompt", nargs="?", default="", help="Optional user query or instruction")
    pipe_parser.add_argument("--preset", default="log-analyzer", help="System prompt preset (default: log-analyzer)")
    pipe_parser.add_argument("--model", default=DEFAULT_MODEL, help="Path to GGUF model file")
    pipe_parser.add_argument("--threads", type=int, default=3, help="Worker CPU threads (default: 3)")
    pipe_parser.add_argument("--batch", type=int, default=128, help="Batch evaluation size (default: 128)")
    pipe_parser.add_argument("--mock", action="store_true", help="Run in mock simulation mode (no model needed)")

    # Chat subcommand
    chat_parser = subparsers.add_parser("chat", help="Start interactive terminal chat session")
    chat_parser.add_argument("--preset", default="default", help="System prompt preset (default: default)")
    chat_parser.add_argument("--model", default=DEFAULT_MODEL, help="Path to GGUF model file")
    chat_parser.add_argument("--threads", type=int, default=3, help="Worker CPU threads (default: 3)")
    chat_parser.add_argument("--batch", type=int, default=128, help="Batch evaluation size (default: 128)")
    chat_parser.add_argument("--mock", action="store_true", help="Run in mock simulation mode (no model needed)")

    # Serve subcommand
    serve_parser = subparsers.add_parser("serve", help="Start background OpenAI-compatible loopback daemon")
    serve_parser.add_argument("--port", type=int, default=8080, help="Listen port (default: 8080)")
    serve_parser.add_argument("--host", default="127.0.0.1", help="Bind address (default: 127.0.0.1)")
    serve_parser.add_argument("--model", default=DEFAULT_MODEL, help="Path to GGUF model file")
    serve_parser.add_argument("--threads", type=int, default=3, help="Worker CPU threads (default: 3)")
    serve_parser.add_argument("--batch", type=int, default=128, help="Batch evaluation size (default: 128)")
    serve_parser.add_argument("--mock", action="store_true", help="Run in mock simulation mode (no model needed)")

    return parser

def main() -> int:
    """CLI entrypoint."""
    parser = build_parser()
    if len(sys.argv) == 1:
        parser.print_help()
        return 0

    args = parser.parse_args()

    if not args.subcommand:
        parser.print_help()
        return 0

    engine = LlamaEngine(
        model_path=args.model,
        n_threads=getattr(args, "threads", 3),
        n_batch=getattr(args, "batch", 128),
        mock_mode=getattr(args, "mock", False)
    )

    if args.subcommand == "pipe":
        stdin_content = ""
        if not sys.stdin.isatty():
            stdin_content = sys.stdin.read()
        return run_pipe(
            engine=engine,
            user_prompt=args.prompt,
            preset=args.preset,
            stdin_content=stdin_content
        )
    elif args.subcommand == "chat":
        return run_chat(engine=engine, preset=args.preset)
    elif args.subcommand == "serve":
        run_server(engine=engine, host=args.host, port=args.port)
        return 0

    return 0

if __name__ == "__main__":
    sys.exit(main())
