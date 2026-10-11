import pytest
from pithon.cli import build_parser

def test_cli_parser_pipe():
    parser = build_parser()
    args = parser.parse_args(["pipe", "Check for errors", "--preset", "log-analyzer", "--model", "test.gguf"])
    assert args.subcommand == "pipe"
    assert args.prompt == "Check for errors"
    assert args.preset == "log-analyzer"
    assert args.model == "test.gguf"

def test_cli_parser_chat():
    parser = build_parser()
    args = parser.parse_args(["chat", "--preset", "weather", "--threads", "2"])
    assert args.subcommand == "chat"
    assert args.preset == "weather"
    assert args.threads == 2

def test_cli_parser_serve():
    parser = build_parser()
    args = parser.parse_args(["serve", "--port", "9090", "--host", "127.0.0.1"])
    assert args.subcommand == "serve"
    assert args.port == 9090
    assert args.host == "127.0.0.1"
