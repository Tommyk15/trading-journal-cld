# Trading Journal

A comprehensive trading journal for tracking and analyzing options trading activity with Interactive Brokers.

## Features

- **Trade Tracking**: Automatically sync executions from Interactive Brokers
- **Smart Grouping**: Intelligent trade grouping algorithm that detects:
  - Vertical spreads
  - Iron condors
  - Butterflies
  - Complex multi-leg strategies
  - Rolls (position adjustments)
- **Greeks Tracking**: Real-time Greeks data for open positions
- **P&L Analysis**: Detailed profit & loss tracking (realized and unrealized)
- **REST API**: FastAPI-powered backend for integration
- **CLI Tools**: Command-line interface for common operations

## Architecture

- **Backend**: FastAPI (Python 3.11+)
- **Database**: PostgreSQL with SQLAlchemy 2.0 (async)
- **IBKR Integration**: ib-insync library
- **CLI**: Typer with Rich output
- **Containerization**: Docker Compose

## Quick Start

### Prerequisites

- Python 3.11+
- Docker & Docker Compose
- Interactive Brokers TWS or IB Gateway running
- PostgreSQL (or use Docker Compose)

### Installation

1. **Clone the repository**
   ```bash
   git clone https://github.com/yourusername/trading-journal-cld.git
   cd trading-journal-cld
   ```

2. **Set up environment variables**
   ```bash
   cp .env.example .env
   # Edit .env with your settings
   ```

3. **Option A: Using Docker Compose (Recommended)**
   ```bash
   docker-compose up -d
   ```

4. **Option B: Local Development**
   ```bash
   # Create virtual environment
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate

   # Install dependencies
   pip install -r requirements-dev.txt

   # Install package in editable mode
   pip install -e .

   # Run database migrations
   alembic upgrade head

   # Start the API server
   trading-journal serve --reload
   ```

### Verify Installation

```bash
# Check CLI
trading-journal --version

# Check API health
curl http://localhost:8000/health

# Check database
docker-compose exec postgres psql -U trading_journal -c "\dt"
```

## Usage

### CLI Commands

```bash
# Start the API server
trading-journal serve --host 0.0.0.0 --port 8000 --reload

# Sync trades from IBKR (coming soon)
trading-journal sync

# Fetch Greeks for open positions (coming soon)
trading-journal fetch-greeks

# Show status
trading-journal status
```

### API Endpoints

- `GET /` - Root endpoint
- `GET /health` - Health check
- More endpoints coming in Phase 1

## Development

### Project Structure

```
trading-journal-cld/
├── src/
│   └── trading_journal/
│       ├── api/              # API routes
│       ├── core/             # Core configuration
│       ├── models/           # SQLAlchemy models
│       ├── schemas/          # Pydantic schemas
│       ├── services/         # Business logic
│       ├── config.py         # Settings
│       ├── main.py           # FastAPI app
│       └── cli.py            # CLI commands
├── tests/                    # Test suite
├── alembic/                  # Database migrations
├── docker/                   # Docker configuration
├── .github/                  # GitHub Actions CI/CD
└── pyproject.toml           # Project metadata
```

### Running Tests

```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=trading_journal --cov-report=html

# Run specific test file
pytest tests/test_api.py -v
```

### Code Quality

```bash
# Format code
black src/ tests/

# Lint code
ruff check src/ tests/ --fix

# Install pre-commit hooks
pre-commit install

# Run pre-commit on all files
pre-commit run --all-files
```

### Database Migrations

```bash
# Create a new migration
alembic revision --autogenerate -m "Description of changes"

# Apply migrations
alembic upgrade head

# Rollback one migration
alembic downgrade -1

# Show current revision
alembic current
```

## Database Schema

### Core Tables

- **executions**: Raw execution data from IBKR
- **trades**: Grouped trades with strategy classification
- **positions**: Current open positions
- **greeks**: Historical Greeks data

See [Database Schema Documentation](docs/database-schema.md) for details.

## Configuration

Key environment variables (see `.env.example` for full list):

```env
# Database
POSTGRES_HOST=localhost
POSTGRES_PORT=5432
POSTGRES_USER=trading_journal
POSTGRES_PASSWORD=trading_journal
POSTGRES_DB=trading_journal

# IBKR
IBKR_HOST=127.0.0.1
IBKR_PORT=7496          # 7496 for live, 7497 for paper
IBKR_CLIENT_ID=1

# API
API_HOST=0.0.0.0
API_PORT=8000
```

## Roadmap

### Phase 0: Project Setup ✅
- [x] Backend scaffolding
- [x] Docker environment
- [x] Database schema
- [x] CI/CD pipeline
- [x] Development tooling

### Phase 1: Core Features (In Progress)
- [ ] IBKR execution sync
- [ ] Trade grouping algorithm integration
- [ ] P&L calculation
- [ ] Greeks fetching
- [ ] Basic API endpoints

### Phase 2: Advanced Features
- [ ] Web dashboard
- [ ] Trade analytics
- [ ] Performance metrics
- [ ] Export/reporting

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for development guidelines.

## License

MIT License - see LICENSE file for details

## Support

For issues and questions:
- GitHub Issues: [Create an issue](https://github.com/yourusername/trading-journal-cld/issues)
- Documentation: [View docs](docs/)

## Acknowledgments

- Built with [FastAPI](https://fastapi.tiangolo.com/)
- IBKR integration via [ib-insync](https://github.com/erdewit/ib_insync)
- Database powered by [PostgreSQL](https://www.postgresql.org/)
