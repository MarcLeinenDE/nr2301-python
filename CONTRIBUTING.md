# Contributing

Contributions, corrections and reproducible observations are welcome.

## Evidence first

The SDK follows the public reverse-engineered API reference at <https://github.com/MarcLeinenDE/nr2301-api>. Please avoid adding guessed router semantics. If a new SDK behavior depends on an API fact that is not documented there yet, update or discuss the API evidence first.

## AI coding agents

AI coding agents and automated contributors should read [`AGENTS.md`](AGENTS.md) before changing the SDK. It documents the upstream source-of-truth rule, namespace conventions, write/recovery patterns, integration-test safety gates, packaging requirements, privacy rules and definition of done.

If historical application code suggests a working feature that is missing from the SDK, verify the underlying evidence and normalize any missing protocol fact in `nr2301-api` before adding the high-level helper here.

## Development

```bash
python -m pip install -e ".[test]"
pytest
```

## Safety

Never commit real router credentials, SMS data, configuration backups, subscriber/SIM identifiers, Wi-Fi keys, VPN secrets or private deployment identifiers.

## Scope

This repository contains the reusable Python SDK. GUI applications, Android applications, Home Assistant integrations and private deployment configuration belong in separate projects.
