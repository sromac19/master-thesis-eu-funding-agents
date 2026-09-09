# EU Funding Call Recommender

Local research prototype accompanying the master's thesis *An Intelligent
Multi-Agent System for Discovering and Ranking EU Funding Calls Based on
User-Provided Project Descriptions*.

The prototype accepts a short project description in Croatian or English and
returns a ranked set of current EU funding calls. Each result links to the
official call page and presents the available deadline, call budget and a
plain-language explanation of thematic relevance. A PDF summary can be
downloaded for further discussion.

## Scope of the demonstration

- filters calls by confirmed status and deadline;
- uses multilingual lexical and semantic retrieval for ranking;
- accepts project descriptions written in Croatian or English;
- shows official EU links and locally available evidence excerpts;
- creates a local PDF opportunity report;
- keeps thematic relevance separate from formal eligibility.

This is a decision-support prototype. It does not submit applications, give
legal advice, guarantee funding or confirm eligibility for a specific call.
The official call page remains the authoritative source for all application
requirements and deadlines.

## Requirements

- Windows PowerShell
- Python 3.11 or 3.12
- Docker Desktop
- internet access on the first run, to download the local multilingual model

No API key is needed for the local demonstration. The public preview does not
send the entered project description to an external language model and does not
store it permanently.

## Run the local demonstration

Open PowerShell in the repository root. Create the local configuration and
install the dependencies:

```powershell
Copy-Item .env.example .env
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -e ".[dev,ml,agents,ui]"
```

Start PostgreSQL, initialise the schema and load the small public demo catalogue:

```powershell
docker compose up -d db
alembic upgrade head
python scripts/load_demo_catalog.py
```

Start the API in the first PowerShell window:

```powershell
python -m eu_funding_agents.server
```

Open a second PowerShell window in the same repository, activate the virtual
environment and start the user interface:

```powershell
.\.venv\Scripts\Activate.ps1
streamlit run app.py
```

Open the address printed by Streamlit, normally `http://127.0.0.1:8501`.
The first search can take longer because it loads the multilingual model.

## Suggested demonstration input

Select country `HR`, organisation type `Small or medium-sized company` and the
area `Energy and environment`. Enter the following project description:

```text
Razvijamo digitalnu platformu za praćenje i smanjenje ugljičnog otiska zgrada.
Rješenje povezuje podatke o potrošnji energije, obnovi zgrada i procjeni životnog
ciklusa radi energetski učinkovite obnove i održivog upravljanja javnim zgradama.
```

Open the first recommendation, review the explanation and official link, then
download the PDF report.

## Reproduce the implemented checks

The following focused tests verify the demo catalogue, API response, Streamlit
interface, PDF report, formal-rule logic and controlled workflow scenarios:

```powershell
pytest tests/test_demo_catalog.py tests/test_client_pdf.py tests/test_recommendations_api.py tests/test_streamlit_app.py tests/test_synthetic_eligibility.py tests/test_workflow_ablation.py
ruff check .
```

The two commands below reproduce the controlled synthetic checks used for the
rule engine and workflow ablation. They write local JSON reports under
`data/processed/`, which is intentionally excluded from Git:

```powershell
python scripts/evaluate_synthetic_eligibility.py
python scripts/evaluate_workflow_ablation.py
```

The public Streamlit preview demonstrates retrieval and reporting on a small
current-call catalogue. The formal-rule and controlled-workflow evaluations are
separate controlled scenarios; they are not presented as legal validation of
all real EU calls.

## Technology

Python, FastAPI, Streamlit, PostgreSQL with pgvector, SQLAlchemy, Alembic,
Sentence Transformers, LangGraph, ReportLab, pytest and Ruff.

## Data and privacy

The repository contains only a small public demo catalogue. Raw source
snapshots, processed datasets, local databases, API keys, user profiles and
thesis-writing materials are excluded from version control.

To stop the local database after the demonstration:

```powershell
docker compose stop db
```
