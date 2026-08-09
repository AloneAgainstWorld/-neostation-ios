# AI Assistance Guidelines for NeoStation

To maintain the quality and security of NeoStation, we welcome the use of AI tools (GitHub Copilot, ChatGPT, Claude, Gemini, etc.) under the following conditions:

## 1. Human Responsibility
You are the owner of your contribution. AI-generated code must be fully understood, reviewed, and tested by you. 
* **Never "blindly" copy-paste:** Ensure the code follows our Flutter architecture (`lib/services/`, `lib/providers/`, etc.).
* **Security:** Ensure the AI hasn't introduced hardcoded keys, mock data, or insecure logic.

## 2. Licensing and DCO
Only humans can legally certify a contribution. 
* AI agents **MUST NOT** sign commits. 
* By submitting a PR, you certify that the AI-generated code is compatible with our **GPL-3.0** license and does not infringe on third-party intellectual property.

## 3. Transparency (Optional but Recommended)
For significant changes or new features generated primarily by an AI, please add a tag at the end of your commit message:

`AI-Assisted: NAME_OF_AI:VERSION`

*Example:*
`AI-Assisted: ChatGPT:GPT-4o`

## 4. Quality Standards
AI-generated code must pass:
* `flutter analyze` (no errors/warnings).
* `flutter test` (all tests passing).
* Our naming conventions (`PascalCase` for Widgets, `camelCase` for variables).