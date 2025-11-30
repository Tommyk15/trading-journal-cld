# Contributing to Trading Journal

Thank you for your interest in contributing to Trading Journal! This document provides guidelines and instructions for contributing.

## Development Setup

### Prerequisites

- Python 3.11 or higher
- Docker & Docker Compose
- Git
- Interactive Brokers TWS/IB Gateway (for IBKR integration testing)

### Setting Up Your Development Environment

1. **Fork and clone the repository**
   ```bash
   git clone https://github.com/yourusername/trading-journal-cld.git
   cd trading-journal-cld
   ```

2. **Create a virtual environment**
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

3. **Install development dependencies**
   ```bash
   pip install -r requirements-dev.txt
   pip install -e .
   ```

4. **Set up pre-commit hooks**
   ```bash
   pre-commit install
   ```

5. **Copy environment configuration**
   ```bash
   cp .env.example .env
   # Edit .env with your local settings
   ```

6. **Start the development environment**
   ```bash
   docker-compose up -d postgres
   alembic upgrade head
   ```

## Development Workflow

### Branching Strategy

- `main` - Production-ready code
- `develop` - Integration branch for features
- `feature/*` - New features
- `bugfix/*` - Bug fixes
- `hotfix/*` - Critical production fixes

### Making Changes

1. **Create a feature branch**
   ```bash
   git checkout -b feature/your-feature-name
   ```

2. **Make your changes**
   - Write clean, readable code
   - Follow the project's coding standards
   - Add tests for new functionality
   - Update documentation as needed

3. **Run code quality checks**
   ```bash
   # Format code
   black src/ tests/

   # Lint code
   ruff check src/ tests/ --fix

   # Run tests
   pytest --cov=trading_journal
   ```

4. **Commit your changes**
   ```bash
   git add .
   git commit -m "feat: add new feature description"
   ```

   Follow [Conventional Commits](https://www.conventionalcommits.org/):
   - `feat:` - New feature
   - `fix:` - Bug fix
   - `docs:` - Documentation changes
   - `style:` - Code style changes (formatting)
   - `refactor:` - Code refactoring
   - `test:` - Adding or updating tests
   - `chore:` - Maintenance tasks

5. **Push and create a pull request**
   ```bash
   git push origin feature/your-feature-name
   ```

## Code Standards

### Python Style Guide

- Follow [PEP 8](https://pep8.org/)
- Use type hints for all function signatures
- Maximum line length: 100 characters
- Use Black for code formatting
- Use Ruff for linting

### Example Code Style

```python
from decimal import Decimal
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession


async def calculate_trade_pnl(
    session: AsyncSession,
    trade_id: int,
    current_price: Optional[Decimal] = None,
) -> Decimal:
    """Calculate total P&L for a trade.

    Args:
        session: Database session
        trade_id: ID of the trade
        current_price: Current price for unrealized P&L calculation

    Returns:
        Total P&L (realized + unrealized)

    Raises:
        ValueError: If trade not found
    """
    # Implementation here
    pass
```

### Testing Standards

- Write tests for all new features
- Maintain test coverage above 80%
- Use pytest fixtures for common setup
- Test both success and error cases
- Use meaningful test names

```python
async def test_calculate_trade_pnl_with_open_position(db_session):
    """Test P&L calculation for trade with open position."""
    # Arrange
    trade = await create_test_trade(db_session)

    # Act
    pnl = await calculate_trade_pnl(db_session, trade.id)

    # Assert
    assert pnl == Decimal("100.00")
```

### Documentation

- Add docstrings to all public functions and classes
- Use Google-style docstrings
- Update README.md for new features
- Add inline comments for complex logic only

## Database Changes

### Creating Migrations

1. **Make changes to SQLAlchemy models**
   ```python
   # src/trading_journal/models/trade.py
   class Trade(Base):
       # Add new field
       new_field: Mapped[str] = mapped_column(String(50))
   ```

2. **Generate migration**
   ```bash
   alembic revision --autogenerate -m "Add new_field to Trade model"
   ```

3. **Review and edit migration**
   - Check the generated migration in `alembic/versions/`
   - Ensure upgrade and downgrade functions are correct
   - Test the migration locally

4. **Apply migration**
   ```bash
   alembic upgrade head
   ```

## Testing

### Running Tests

```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=trading_journal --cov-report=html

# Run specific test file
pytest tests/test_api.py -v

# Run specific test
pytest tests/test_api.py::test_root_endpoint -v
```

### Writing Tests

Place tests in the `tests/` directory mirroring the source structure:

```
tests/
├── test_api.py           # API endpoint tests
├── test_models.py        # Model tests
├── test_services.py      # Service layer tests
└── conftest.py          # Shared fixtures
```

## Pull Request Process

1. **Ensure all checks pass**
   - All tests pass
   - Code is formatted with Black
   - No linting errors from Ruff
   - Documentation is updated

2. **Create a descriptive PR**
   - Clear title summarizing the change
   - Description of what and why
   - Link to related issues
   - Screenshots for UI changes

3. **Address review feedback**
   - Respond to comments
   - Make requested changes
   - Re-request review when ready

4. **Merge requirements**
   - At least one approval
   - All CI checks passing
   - No merge conflicts
   - Up to date with base branch

## CI/CD Pipeline

The project uses GitHub Actions for CI/CD:

- **Linting**: Black and Ruff checks
- **Testing**: pytest with coverage reporting
- **Docker Build**: Validates Docker image builds

See `.github/workflows/ci.yml` for details.

## Reporting Bugs

### Before Submitting

1. Check existing issues
2. Verify it's reproducible
3. Test on the latest version

### Bug Report Template

```markdown
**Description**
Clear description of the bug

**To Reproduce**
Steps to reproduce:
1. Step one
2. Step two
3. See error

**Expected Behavior**
What should happen

**Actual Behavior**
What actually happens

**Environment**
- OS: [e.g., macOS 14.0]
- Python version: [e.g., 3.11.5]
- Trading Journal version: [e.g., 0.1.0]

**Additional Context**
Any other relevant information
```

## Feature Requests

We welcome feature requests! Please:

1. Check if it's already requested
2. Describe the use case
3. Explain the expected behavior
4. Consider implementation approach

## Code Review Guidelines

When reviewing PRs:

- Be respectful and constructive
- Focus on code quality and standards
- Test the changes locally if possible
- Approve when satisfied with the changes

## Questions?

- Open a GitHub Discussion
- Create an issue with the `question` label
- Check existing documentation

## License

By contributing, you agree that your contributions will be licensed under the MIT License.
