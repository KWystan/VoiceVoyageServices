# Runtime safety

The two FastAPI services are local-friendly in development and fail closed in
production:

- APP_ENV=production requires VV_AUTH_MODE=firebase or VV_AUTH_MODE=token.
- Wildcard CORS is rejected; production origins must be explicit HTTPS origins.
- The phoneme endpoint requires a bounded Content-Length, a bounded audio
  body, an allowlisted content type, and a maximum decoded duration.
- The module endpoint bounds the JSON payload, item count, field lengths, and
  candidate output. Unknown LLM fields and out-of-catalog text are rejected.
- The Flutter release build requires HTTPS service URLs and refuses bundled
  service tokens; it obtains Firebase ID tokens from the signed-in user.

For a local run, copy .env.example, keep APP_ENV=development, and use
VV_AUTH_MODE=off only on a trusted development machine. Never commit .env,
Firebase credentials, model tokens, or service tokens.
