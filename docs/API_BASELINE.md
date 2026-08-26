# API baseline

The SDK does not define the NR2301 protocol independently. Its canonical protocol source is the public API project:

- Repository: <https://github.com/MarcLeinenDE/nr2301-api>
- Initial pinned release: `v0.1.0`
- Release tag commit: `ee2233599a7646c501a7e5d86962bcc52fa1d8ba`
- API inventory: 157 methods across 16 namespaces
- Tested firmware baseline: `V1.00(ACIY.3)C0`
- Hardware runtime: `MIFI.NR2301.H01`

## Precedence

When SDK behavior and the pinned API reference disagree, treat the API reference as the protocol evidence source and investigate the SDK implementation. Do not silently redefine API semantics in this repository.

Future SDK releases may move to newer API-reference releases, but each SDK release should record the API baseline it was tested against.
