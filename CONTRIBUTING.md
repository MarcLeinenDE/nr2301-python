# Contributing

Contributions, corrections and reproducible observations are welcome.

## Evidence first

The SDK follows the public reverse-engineered API reference at <https://github.com/MarcLeinenDE/nr2301-api>. Please avoid adding guessed router semantics. If a new SDK behavior depends on an API fact that is not documented there yet, update or discuss the API evidence first.

## Development

```bash
python -m pip install -e ".[test]"
pytest
```

## Safety

Never commit real router credentials, SMS data, configuration backups, subscriber/SIM identifiers, Wi-Fi keys, VPN secrets or private deployment identifiers.

## Scope

This repository contains the reusable Python SDK. GUI applications, Android applications, Home Assistant integrations and private deployment configuration belong in separate projects.
