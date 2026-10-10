Autonomous Multi-Agent AI Software Engineering System

An AI-assisted software engineering workflow that turns a natural-language requirement into a planned, tested, reviewed code change and prepares a GitHub Pull Request after explicit human approval.

Overview

The system uses a FastAPI backend and a LangGraph workflow to coordinate specialized agents. It is designed to work against an existing local Git repository.

Workflow

Natural-language requirement
          |
          v
 Repository Analyst
          |
          v
 Repository Intelligence
          |
          v
       Planner
          |
          v
        Coder
          |
          v
     Test Agent
          |
          +------ Tests fail ------> Debugger
          |                             |
          |                             v
          |                       Coder repair
          |                             |
          +<----------------------------+
          |
     Tests pass
          |
          v
     Code Review
          |
          v
   Human approval
          |
          v
 GitHub Pull Request

The debugger/repair cycle is bounded by the configured maximum retry count. GitHub Pull Request creation is performed only after the approval endpoint accepts an explicit approval for a run that is waiting for human approval.

Main capabilities

Repository analysis: scans the target repository to discover project files.

Repository intelligence: identifies relevant files and summarizes the repository's architecture and relationships.

Task planning: converts a requirement into an ordered implementation plan.

Code generation: creates or modifies files authorized by the plan.

Automated testing: runs the project's tests and records the results.

Debugging loop: diagnoses test failures and sends the repair context back to the coder, subject to a retry limit.

Code review: evaluates the proposed changes before approval.

Human approval: pauses the workflow until a reviewer approves or rejects the proposed change.

GitHub PR creation: creates or detects an existing pull request after approval.

Run persistence: saves workflow state to run_store.json so run status can be retrieved after a backend restart.

Technology stack

Python 3.11

FastAPI

LangGraph

Pydantic

Groq / langchain-groq for supported LLM workflows

Pytest

Git and GitHub API integration

JWT-based authentication utilities

Check the project's requirements.txt and .env loading code for the exact versions and configuration required by your checkout.

Project structure

The main components are organized approximately as follows:

AI-Software-Engineer/
├── backend/
│   ├── agents/
│   │   ├── repository.py
│   │   ├── repository_intelligence.py
│   │   ├── planner.py
│   │   ├── coder.py
│   │   ├── test_agent.py
│   │   ├── debugger.py
│   │   ├── code_review.py
│   │   └── human_approval.py
│   ├── auth/
│   ├── github/
│   ├── graph/
│   │   ├── state.py
│   │   └── workflow.py
│   ├── tools/
│   ├── utils/
│   └── main.py
├── test-target-repo/
├── requirements.txt
├── run_store.json
└── README.md

The exact file list may differ slightly by branch.

Prerequisites

Python 3.11

Git

A Groq API key if your configured agents use Groq

A GitHub token with appropriate repository permissions if you want to create pull requests

Access to a Git repository that you are authorized to modify

Docker is optional if the test runner supports a Docker execution mode in your current checkout. Local test execution is the default in the described setup.

Installation on Windows

Open PowerShell in the project directory.

1. Create and activate a virtual environment

cd D:\pro\AI-Software-Engineer

py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1

2. Install dependencies

python -m pip install --upgrade pip
pip install -r requirements.txt

3. Configure environment variables

Create a local .env file using the variable names expected by the project's configuration code. Common settings for this project include:

LLM_PROVIDER=groq
GROQ_API_KEY=your_groq_api_key
MODEL=openai/gpt-oss-20b
SECRET_KEY=replace_with_a_long_random_secret
GITHUB_TOKEN=your_github_token
GITHUB_OWNER=your_github_username_or_organization
GITHUB_REPO=your_target_repository
GITHUB_BASE_BRANCH=main

These are example values, not a guarantee that every variable name is consumed by every module. Verify names against your current configuration code before running. Never commit .env, API keys, access tokens, or real secrets to Git.

4. Start the API

uvicorn backend.main:app --reload

The API should be available at:

Swagger UI: http://127.0.0.1:8000/docs

Root endpoint: http://127.0.0.1:8000/

Health endpoint: http://127.0.0.1:8000/health

Stop the development server with Ctrl+C.

API workflow

Start a software engineering run

Use POST /run with a JSON body similar to:

{
  "requirement": "Add a multiply(a, b) function to app.py and add pytest tests for it.",
  "repository_path": "D:\\path\\to\\your\\target-repository",
  "max_debug_retries": 3
}

Use an existing repository path that the process can access. The retry count must be between 0 and 10; the default is 3.

The response includes the run ID, current step/status, plan, analyzed files, test results, review results, approval information, GitHub result, and any errors reported by the workflow.

Retrieve run status

Use GET /runs/{run_id}, replacing {run_id} with the ID returned by POST /run.

Approve a run

Only approve a run after checking the proposed change and confirming that its status is waiting for human approval.

POST /runs/{run_id}/approve

Example body:

{
  "reviewer": "human",
  "comment": "Reviewed and approved."
}

The backend attempts GitHub Pull Request creation after approval.

Reject a run

POST /runs/{run_id}/reject

Example body:

{
  "reviewer": "human",
  "comment": "Changes need further review."
}

Explore /docs for the exact request and response schemas in the running version.

Run tests

From the project root:

$env:PYTEST_DISABLE_PLUGIN_AUTOLOAD = "1"
python -m pytest -q

To validate the retry request model:

python -c "from backend.main import TaskRequest; print(TaskRequest(requirement='Add a function', repository_path='.', max_debug_retries=5).max_debug_retries)"

Expected output:

5

A retry value greater than 10 should fail Pydantic validation.

Safety and operational notes

Run the system only against repositories you own or are authorized to modify.

Review generated changes before approval; automated tests and code review are not a guarantee of correctness or security.

Keep credentials in environment variables or a secrets manager, not in source control.

The repository scanner excludes selected directories and .env; verify the current scanner and filesystem safeguards before using this system with sensitive repositories.

Local test execution runs code from the target repository. Use a disposable checkout or a properly isolated environment for untrusted code.

GitHub permissions should be limited to what the workflow requires.

The Google OAuth endpoints in the current development implementation are placeholders; they are not a production-ready Google OAuth integration.

run_store.json may contain repository paths, requirements, generated content, and run details. Protect it and avoid committing sensitive run data.

Current limitations

LLM output quality depends on the selected model, prompts, available context, and API availability.

The system relies on the target repository's test setup; it does not guarantee that all project-specific dependencies are installed.

Human approval is an explicit workflow gate, but reviewers must still inspect the actual changes and CI results.

Production deployment would require additional work around real OAuth integration, secret management, access controls, concurrency, audit logging, and isolation of untrusted code execution.

Demonstration scenario

Use a disposable target repository for the demonstration:

Start the FastAPI server and open /docs.

Submit a requirement to add a small function and its tests.

Show the repository analysis, generated plan, and changed files.

Show the automated test results and code review status.

Demonstrate that the workflow pauses for human approval.

Approve the run and show the resulting GitHub Pull Request.

Open the PR and inspect the diff and tests.

Future improvements

Potential next steps, not currently claimed as implemented:

Add CI checks for linting, type checking, and security scanning.

Improve sandboxing for test execution.

Add richer run observability and structured logs.

Add integration tests for approval and GitHub PR creation.

Replace placeholder OAuth behavior with a verified OAuth flow before production deployment.

Add deployment instructions and screenshots from the actual running application.

Author

Chirag

Add your preferred GitHub profile and contact details here before publishing.