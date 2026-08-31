# Contributing to llm-brain

## Conventional Commits

This project uses [Conventional Commits](https://www.conventionalcommits.org/) for commit messages.
Every commit message must follow this format:

```
<type>(<scope>): <description>

[optional body]

[optional footer(s)]
```

### Types

- **feat**: A new feature
- **fix**: A bug fix
- **docs**: Documentation only changes
- **style**: Changes that do not affect the meaning of the code (white-space, formatting, etc.)
- **refactor**: A code change that neither fixes a bug nor adds a feature
- **perf**: A code change that improves performance
- **test**: Adding missing tests or correcting existing tests
- **chore**: Changes to the build process or auxiliary tools and libraries
- **ci**: Changes to CI configuration files and scripts

### Scopes

- **api**: FastAPI backend
- **etl**: Memory distillation pipeline
- **rag**: RAG service (LangChain + vector store)
- **agents**: MCP agents (Ingestor/Razonador/Evaluador)
- **simulator**: Decision-support simulator
- **shield**: Privacy & scam shield
- **mobile**: React Native mobile app
- **web**: React web dashboard
- **infra**: Infrastructure (Docker, CI/CD)
- **openspec**: OpenSpec documentation

### Examples

```bash
feat(api): add JWT authentication endpoint
fix(etl): handle PDF parsing error for corrupt files
docs(openspec): update Frame 2 design with triple extraction
test(rag): add unit tests for vector store operations
chore(infra): update Docker Compose with health checks
```

## Development Workflow

1. Create a feature branch from `main`
2. Make changes and commit with conventional commits
3. Push to remote and create a Pull Request
4. CI will run tests, linting, and security scans (Snyk)
5. After review, merge into `main`

## Code Quality

- **Linting**: Run `ruff check .` before committing
- **Formatting**: Run `ruff format .` before committing
- **Tests**: Run `pytest` before pushing
- **Security**: CI runs Snyk dependency scan and SAST on every push/PR

## Architecture

This project uses an architecture-first approach. Before writing code:

1. Check the OpenSpec frame for the current objective
2. Read the `design.md` for architecture decisions
3. Read the `tasks.md` for task breakdown
4. Follow the architecture decisions in `design.md`
5. Update OpenSpec artifacts if implementation diverges

See `openspec/` for the full specification-driven development workflow.
