# Operator sees figures, not questions

The Compliance Advisor gains an Operator who runs it: watches how it performs and starts Update Runs. The Operator sees figures and technical data across all Accounts (number of questions, answer times, errors, costs per Answer Model and Search Strategy, retrieval scores, how many questions were refused and why, Update Runs and Change Records), but never a question text or an answer. This extends ADR 0005: an Account's answers stay private to it, also from the people running the app. Logs follow the same rule and hold no question texts. Operators are accounts with the role granted by whoever runs the backend (`compliance-advisor-accounts operator grant <email>`); there is no page for assigning roles. Decided in the design session of 2026-10-28.

## Considered Options

Letting the Operator read question texts would make support and quality control easier: a bad answer could be looked at directly. It was rejected because a Compliance Officer's question often reveals what their Firm is working on, and a bank's or insurer's first question about any such tool is who can read it. Answer quality is checked instead with the Golden Set and RAGAs, which need no real questions.

## Amended 2026-10-28

The first version named Operators in a server setting (`OPERATOR_EMAILS`). Registration is open and unverified (ADR 0005), so whoever registered a listed address first would have become an Operator. The role is now a flag on the account that only a command run next to the database can set.
