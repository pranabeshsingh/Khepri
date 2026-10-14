## Description

<!-- Provide a concise summary of the change, motivation, and which issue(s) it resolves. -->
Closes #

## Type of Change

- [ ] 🐛 Bug fix (non-breaking change which fixes an issue)
- [ ] ✨ New feature or agent tool (non-breaking change adding functionality)
- [ ] ⚡ Performance optimization (latency, CPU, or RAM footprint improvement)
- [ ] 💥 Breaking change (fix or feature that would cause existing behavior/APIs to change)
- [ ] 📝 Documentation update
- [ ] 🔧 CI/CD or build infrastructure update
- [ ] ♿ Accessibility improvement

## Hardware & Environment Tested

- [ ] Raspberry Pi 4 (4GB RAM)
- [ ] Raspberry Pi 5
- [ ] Linux x86_64
- [ ] macOS (Apple Silicon)
- [ ] Docker Multi-Arch (amd64 / arm64)
- [ ] Simulated Mock Mode (`:mock:` model)

## Quality & Verification Checklist

- [ ] Python syntax and bytecode compilation pass (`python3 -m compileall pithon tests`)
- [ ] Static type checking passes (`mypy pithon`)
- [ ] Code formatting and linting pass (`ruff check pithon tests`)
- [ ] Unit and integration tests pass (`pytest tests/ -m "not e2e" -v`)
- [ ] Memory footprint verified to stay within Raspberry Pi limits (< 750MB process RSS for 0.5B models)
- [ ] Any new tools, endpoints, or CLI arguments are documented in `README.md` or `docs/`
- [ ] Security boundaries preserved (path traversal containment, no arbitrary eval, auth verified)
