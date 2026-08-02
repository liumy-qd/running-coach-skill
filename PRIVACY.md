# Privacy and Data Safety

This repository is designed to be safe for public use and contribution.

## Do Not Commit

Never commit:

- COROS access tokens or refresh tokens.
- OAuth callback URLs or state parameters.
- Passwords, API keys, or secrets.
- Real health exports.
- Private activity files such as FIT, GPX, TCX, or screenshots with personal details.
- Location traces that reveal home, workplace, or private routes.
- Menstrual-cycle data or notes. This skill queries them only for an explicit user request and does not archive them by default.

## Use Synthetic Data

Examples in this repository are synthetic. When reporting issues, use synthetic, anonymized, or heavily redacted samples.

## Local COROS Access

Real COROS access should stay local to your machine through your MCP or CLI configuration. This skill only documents how an agent should use that local toolchain; it does not require credentials to be stored in the repository.

FIT downloads are opt-in for a key activity analysis. Do not download or retain them for ordinary daily checks.

## Health Disclaimer

The skill provides training guidance, not medical advice. For chest pain, fainting, abnormal heart rhythm, acute injury, persistent pain, or other concerning symptoms, stop training and consult a qualified professional.
