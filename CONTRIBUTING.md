# Contributing to NeoStation

Thank you for your interest in contributing to NeoStation! This document will help you get started.

## How to contribute

### Reporting bugs

1. Use the issue search to verify the bug has not been reported before.
2. If it is new, open an issue using the **Bug Report** template.
3. Include:
   - NeoStation version
   - Platform (Windows, Linux, macOS, Android)
   - Steps to reproduce
   - Expected vs. actual behavior
   - Logs or screenshots if applicable

### Proposing new features

1. Open an issue using the **Feature Request** template.
2. Clearly describe the problem the feature solves.
3. If possible, include mockups or usage examples.

### Pull Requests

1. **Fork** the repository.
2. Create a branch from `main`. Use the following naming convention:
   - `feature/your-feature-name`
   - `fix/bug-description`
   - `docs/topic-name`
   - `refactor/what-changed`
   ```bash
   git checkout -b feature/your-feature-name
   ```
3. Make your changes following the [code conventions](#code-conventions) and [commit format](#commit-format).
4. Ensure `flutter analyze` reports no errors.
5. If possible, add tests for your change.
6. Update documentation if necessary.
7. Open a Pull Request using the provided template.

## Code conventions

- **Files and folders**: `snake_case`
- **Variables and functions**: `camelCase`
- **Classes and widgets**: `PascalCase`
- **Constants**: `camelCase` or `SCREAMING_SNAKE_CASE` depending on context
- Use `Color.withValues(alpha: …)` instead of `withOpacity()` (deprecated).
- Always check `mounted` before using `BuildContext` after an `await`.
- Use `flutter_screenutil` for sizing and spacing.
- Write comments in **English** and UI text must use the localization system (`AppLocale`).

## Commit format

We follow the [Conventional Commits](https://www.conventionalcommits.org/) specification:

- `feat`: A new feature.
- `fix`: A bug fix.
- `docs`: Documentation only changes.
- `style`: Changes that do not affect the meaning of the code (white-space, formatting, etc).
- `refactor`: A code change that neither fixes a bug nor adds a feature.
- `perf`: A code change that improves performance.
- `test`: Adding missing tests or correcting existing tests.
- `chore`: Changes to the build process or auxiliary tools and libraries.

Example: `feat(ui): add support for custom wallpapers`

## Architecture

- **`lib/screens/`**: UI pages.
- **`lib/widgets/`**: Reusable UI blocks and shared widgets.
- **`lib/providers/`**: State with `ChangeNotifier` (consumed by screens via Provider).
- **`lib/services/`**: Business logic and external APIs. **Never access SQLite directly** — use repositories.
- **`lib/repositories/`**: Data access abstraction. The only layer that may call data sources.
- **`lib/data/datasources/`**: Direct SQLite access, migrations, and raw queries.
- **`lib/models/`**: Immutable data models.
- **`lib/utils/`**: Helpers and utilities.

## Tests

- Add unit tests for business logic in `test/`.
- Use `flutter_test` for widget tests.
- Run all tests before submitting a PR:
  ```bash
  flutter test
  ```

## License

By contributing to NeoStation, you agree that your contributions will be licensed under the **GNU General Public License v3.0 (GPL-3.0)**.
