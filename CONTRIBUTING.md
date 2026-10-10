# Contributing to Aura

Aura is being built by teammates working on the frontend, ingestion, API/AI, and database layers. Keep changes within the module you own where possible, and coordinate before changing shared contracts.

## Get the project

Clone the team's GitHub repository, then install the frontend and backend dependencies using the instructions in [README.md](README.md). Do not commit `.env` files, uploaded materials, credentials, local databases, or generated build files. Use `.env.example` as a placeholder reference.

## Make a change

1. Update your local `main` branch before starting work.
2. Create a focused branch, for example `feat/upload-history` or `fix/pdf-validation`.
3. Work in your module. Coordinate first if another teammate is editing the same files.
4. Run the relevant checks from the README and review `git status` so private or generated files are not included.
5. Commit with a short message describing the change, push your branch, and open a pull request against `main`.
6. Ask a teammate to review the change before merging.

## Shared contracts

Before changing API routes, upload response fields, course/source identifiers, or ingestion content-unit fields, discuss the change with the teammates who consume that contract. Frontend, API, ingestion, and database code depend on those shapes agreeing. Avoid having two people edit the same shared file at once; split work by module or agree on ownership first.

## Current boundaries

- Frontend: `src/`
- FastAPI API and service boundaries: `backend/app/`
- File extraction and content-unit output: `ingestion/`
- Tests: `tests/`
- Database, RAG, learner-model, and assessment integrations are not implemented in this prototype yet.
