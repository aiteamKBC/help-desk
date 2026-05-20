# Knowledge Base Builder Run Prompt and Commands

## Current App URL

```text
http://localhost:4173
```

## Start the Project

From the project folder:

```powershell
cd "C:\Users\KENT\OneDrive - Kent Business College\Desktop\Knowledge_Base_Builder"
```

If Node.js is available globally:

```powershell
npm start
```

If Node.js is not available globally, use the bundled local Node.js copy:

```powershell
.\.tools\node-v22.13.1-win-x64\node.exe .\server.mjs
```

The app should then open at:

```text
http://localhost:4173
```

## Start in the Background

Use this when you want the server to keep running without occupying the terminal:

```powershell
cd "C:\Users\KENT\OneDrive - Kent Business College\Desktop\Knowledge_Base_Builder"
New-Item -ItemType Directory -Force -Path .dev-server | Out-Null
Start-Process -FilePath ".\.tools\node-v22.13.1-win-x64\node.exe" -ArgumentList "server.mjs" -WorkingDirectory (Get-Location).Path -RedirectStandardOutput ".dev-server\server.out.log" -RedirectStandardError ".dev-server\server.err.log" -WindowStyle Hidden
```

## Check That It Is Running

```powershell
Invoke-WebRequest -Uri "http://localhost:4173" -UseBasicParsing
```

A successful response shows:

```text
StatusCode: 200
```

You can also check the server log:

```powershell
Get-Content .dev-server\server.out.log -Tail 20
```

## Stop the Server

Find the Node process running `server.mjs`:

```powershell
Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -like "*Knowledge_Base_Builder*server.mjs*" } | Select-Object ProcessId,Name,CommandLine
```

Stop it by replacing `<PROCESS_ID>` with the listed process ID:

```powershell
Stop-Process -Id <PROCESS_ID> -Force
```

If process lookup is blocked by Windows permissions, close the terminal running the server, or use Task Manager and end the matching `node.exe` process.

## Useful Project Commands

List saved articles:

```powershell
Get-ChildItem .\Articles
```

List evidence files:

```powershell
Get-ChildItem .\Evidence
```

View archived articles:

```powershell
Get-ChildItem .\Articles\Bin
```

## Reusable Codex Prompt

Use this prompt in the future:

```text
Please run the Knowledge Base Builder project from:
C:\Users\KENT\OneDrive - Kent Business College\Desktop\Knowledge_Base_Builder

Use the bundled local Node.js if global Node/npm is not available:
.\.tools\node-v22.13.1-win-x64\node.exe .\server.mjs

Start the server on http://localhost:4173, verify that the page returns HTTP 200, and tell me the URL. If the server fails, check .dev-server/server.err.log and fix or explain the issue.
```
