# Deployment

## Recommended: Render API + Vercel frontend

Render is the primary target because this implementation expects a persistent POSIX disk for SQLite and saved models. `render.yaml` requests a paid Starter web service and a 1 GB persistent disk; review current charges and size before applying. **No paid service or public deployment has been created by this build.**

1. Push application files to your chosen Git remote only after reviewing the existing tracked datasets. Some source files were committed before this build; `.gitignore` does not remove them from history. Avoid uploading multi-gigabyte data by accident. Prefer a clean app-only deployment repository if necessary.
2. Create a Render Blueprint from `render.yaml` or a Docker web service manually. Attach the persistent disk at `/app/runtime`.
3. Set `MULEGRAPH_API_KEY` to a strong random secret and `CORS_ORIGINS` to the exact frontend origin (for example `https://your-app.vercel.app`). Never use `*` for a protected workspace.
4. Deploy. `/health` should return OK. Keep one Uvicorn worker; job recovery and SQLite are designed around this process model.
5. In Vercel, choose `frontend` as the root directory. Framework: Vite. Build: `npm run build`. Output: `dist`. Set `VITE_API_URL=https://your-api.onrender.com` before building.
6. Open the frontend connection dialog and enter the API key. Do not create `VITE_API_KEY`: frontend environment variables are public build content.
7. Upload a prepared subset or create the illustrative sandbox. Local source folders intentionally are not copied into the image. For labeled data, use the CLI on the server with separately supplied files, or upload supported raw CSV with its original label column.
8. Test import → analysis → alert → note → export, then restart the API and verify persistence.

Official references: [Render FastAPI](https://render.com/docs/deploy-fastapi), [Render disks](https://render.com/docs/disks), [Vite on Vercel](https://vercel.com/docs/frameworks/frontend/vite).

## Hugging Face alternative

The root README has Docker Space metadata (`sdk: docker`, `app_port: 7860`). Copy the app-only repository into a Docker Space. Docker listens on port 7860 by default. Set the same API key and CORS settings as above. The frontend remains separately deployed on Vercel; the Space exposes the API, not the React application.

Default container storage is ephemeral. Treat this option as a demo unless you configure storage and verify restart behavior. A bucket is not automatically equivalent to a POSIX disk suitable for a live SQLite database: do not point SQLite at an object-storage URL. Use explicit backup/restore or adapt to an external relational database before relying on it for durable investigations. Review current Space eligibility, hardware and storage pricing; no assumption of free compute is made.

Official reference: [Docker Spaces](https://huggingface.co/docs/hub/spaces-sdks-docker).

## Security and operations

- Synthetic/research data only until authentication, access control, retention, encryption, legal review and operational procedures are completed.
- The API key is a single shared workspace credential, not individual user authentication. Notes are not signed by a verified analyst identity.
- API docs and health are public; application data routes require the key when configured. TLS is provided by the hosting platform.
- Keep dependencies locked after verification. Models are generated locally; never accept uploaded pickle/joblib files.
- Job submission is bounded but not distributed rate limiting. Use host-level request limits and trusted access.
- Back up the persistent volume regularly. Audit logs are not tamper-resistant.
- Fonts load from Google Fonts with local fallbacks; remove external font requests for a privacy-constrained deployment.
