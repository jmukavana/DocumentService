# PageQuay console

TanStack Start frontend for the PageQuay document API. It uses file routes, server routes,
request scoped TanStack Query hydration, TanStack Table, Tailwind CSS, and shadcn/ui.

The visual layout follows the spacing and component structure of Altitude's public site;
all copy and document workflows are specific to this service.

## Local development

Run the API on port 8000. Set `API_KEY`, `API_SECRET`, `UI_USERNAME`, `UI_PASSWORD`,
and `UI_SESSION_SECRET` in the frontend environment. Then:

```bash
pnpm install
pnpm dev
```

Open <http://localhost:3000>. `DOCUMENT_API_URL` defaults to `http://localhost:8000`.

## Production

```bash
pnpm build
pnpm start
```

Nitro serves the built app on `PORT` (3000 in Docker Compose). The browser never receives
administrator API credentials; TanStack Start server routes attach them to upstream requests.
