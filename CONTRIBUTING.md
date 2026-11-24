# Contributing

## Run the same checks as CI

```bash
pip install ruff==0.17.6
ruff check .
python .github/scripts/check_markdown_links.py

cd <project>
python -m venv .venv && source .venv/bin/activate      # on Windows: .venv\Scripts\Activate.ps1
pip install -r requirements.txt pytest
python -m pytest
```

Tests that need the raw dataset, a database or a local model are skipped with a message that says what is missing.

## Documentation rules

- `README.md` is English and `README.es.md` is Spanish. Update both when a result changes.
- Some Spanish READMEs are generated, and a test compares them with the generator. Do not edit them by hand: `delitos-chicago-analisis-espacial` (`python -m delitos_chicago.cifras_readme`), `mercado-laboral-ecuador-enemdu` (`python -m empleo_enemdu.cifras_readme`) and `nyc311-analisis-supervivencia` (`python -m nyc311.cifras_readme`).
  Change the template or script and run the command.
- Every figure must come from `reports/` or from a test. Do not add a number that cannot be reproduced.
- Do not commit raw data, `.env` files, credentials or personal data.
