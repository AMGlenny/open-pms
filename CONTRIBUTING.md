# Contributing

Contributions are welcome: bug reports, ideas, documentation and code.

1. Open an issue first for anything bigger than a small fix, so we can agree the approach.
2. Keep it simple. Open PMS deliberately does a few things well. Features that most organisations won't need are better as options or left out.
3. Run the tests before opening a pull request:
   ```bash
   pip install -e .
   python -m unittest discover -s tests -t .
   ```
4. New pages must pass the accessibility tests (`tests/test_accessibility.py`). Use the existing form and table patterns in `openpms/templates/macros.html`.
5. Data model changes go in `openpms/schema.py`. Never add a way to delete rows: retire or deactivate instead.

By contributing you agree your work is shared under the MIT licence.
