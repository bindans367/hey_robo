# Robo Eye Display

This folder is a standalone, static-only Vercel project. It contains just the eye display page, styles, and browser script; it does not include Robo Brain, the knowledge base, Python code, or model files.

## Deploy with Vercel

From PowerShell, run:

```powershell
cd C:\Users\Admin\Desktop\Humanoid\eye-site
npx vercel
```

Follow the prompts to sign in and create/link the eye-only Vercel project. To publish the production URL, run:

```powershell
npx vercel --prod
```

You can also import this folder as its own project in Vercel. Set the project root to `eye-site`; it is plain HTML/CSS/JavaScript and needs no build command or dependencies.

## Live robot status

The deployed page animates its eyes by itself. To synchronize it with a live Robo Brain, provide a publicly reachable HTTPS status endpoint that returns the same JSON shape as `/api/status`, and permits browser requests from the Vercel site with CORS. Add it as the `status` query parameter, for example:

```text
https://your-eye-site.vercel.app/?status=https%3A%2F%2Fyour-secure-status-host.example%2Fapi%2Fstatus
```

The Python Robo Brain currently listens on this computer’s `127.0.0.1`, so a Vercel deployment cannot reach that local endpoint by itself. Do not put private API keys in the URL.
