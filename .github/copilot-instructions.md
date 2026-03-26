# Copilot Instructions for This Repository
# workspace

Please follow these guidelines when using Copilot or creating code in this repository:

- Language: English.

- All comments, function and variable names, and code must be written in English and follow the Inkypi coding standards and templates. Use the same naming and documentation model across the repository to keep style consistent.

- When creating a new plugin, or if you have any questions, consult the repository documentation in the `docs/` folder first. Follow the guidance there (plugin architecture, contribution guidelines, coding standards) before opening issues or pull requests.

- When you create or modify code, always run the project's test suite and include the exact command below at the end of your chat response (so the user can run it locally):

  source ./venv/bin/activate && pytest -q

- If you add new runnable code, run the tests locally before finishing your response and report the test outcome (pass/fail and summary) in the chat.
- Keep changes small and focused; include any required instructions to reproduce test results.

These instructions are for developer convenience and to keep the repository stable when code is proposed.
