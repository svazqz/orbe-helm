# OrbeHelm Project Instructions

Keep durable documentation and source comments in English. Keep generated artifacts and runtime state inside this checkout. Do not modify global agent configuration or read credential contents as part of routine development.

Definitions are authoritative. Do not hand-edit generated output. Preserve the legacy directory as historical reference. Keep the portable resolver independent of agent-specific CLI details.

Run `python3 -m unittest discover -s tests -v` after behavior changes. Use dry runs and isolated verification homes for CLI checks. Starting an authenticated model session is a separate integration action and must be reported accurately. Never claim exclusive isolation while any adapter cannot guarantee it.
