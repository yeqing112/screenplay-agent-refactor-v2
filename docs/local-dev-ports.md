# Local Dev Ports

When `8765` is blocked on Windows, use a fallback frontend/backend pair instead of the default port.

## Recommended fallback

- Backend: `127.0.0.1:18765`
- Frontend: `127.0.0.1:5175`

## Start manually

```powershell
python -m uvicorn api.server:app --host 127.0.0.1 --port 18765

cd web
npm run dev:local18765
```

## Start both with the helper script

Default dev mode:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\start-local-dev.ps1
```

Custom ports:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\start-local-dev.ps1 -BackendPort 18767 -FrontendPort 4178
```

Stable preview mode for acceptance:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\start-local-dev.ps1 -BackendPort 18766 -FrontendPort 4177 -FrontendMode preview
```

## Notes

- The script now accepts `-BackendPort`, `-FrontendPort`, and `-FrontendMode`.
- `preview` mode runs `npm run build` first, then starts `vite preview`, which is usually more stable for browser acceptance than `vite dev`.
- If a port is already occupied, the script will print a warning before it starts the new process.
- The project list page displays the current `API Proxy` target so you can confirm the frontend is pointing at the expected backend before acceptance.
