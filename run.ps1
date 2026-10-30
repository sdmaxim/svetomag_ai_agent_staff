<#
Svetomag support agent - one entry point for everything. Run from this folder:

    .\run.ps1 setup                  create .venv (Python 3.12) and install packages
    .\run.ps1 build                  build catalog.db from data\
    .\run.ps1 chat                   chat with the agent in the terminal
    .\run.ps1 web                    web chat http://127.0.0.1:8000  and admin page  /admin
    .\run.ps1 admin list             open difficult questions (also: list all | answer <id> "text" | reject <id>)
    .\run.ps1 evaluate               run every test suite and write EVALUATION.md (about 15 min)
    .\run.ps1 test                   all tests
    .\run.ps1 test catalog           only catalogue search tests      (no API cost)
    .\run.ps1 test conversations     only the conversation tests      (optional case numbers: ... 3 7)
    .\run.ps1 test knowledge         only the difficult-questions loop test
    .\run.ps1 test guardrail         only the guardrail test (wrong facts must never reach the customer)
    .\run.ps1 test web               only the web server test
#>
param([Parameter(Position = 0)][string]$Command = "help",
      [Parameter(Position = 1, ValueFromRemainingArguments = $true)][string[]]$Rest)

# "Continue", not "Stop": Windows PowerShell 5.1 turns any stderr text of a program (crewai prints
# warnings there) into a fatal error under "Stop". Our own checks use `throw`; Python's real
# result is passed on through its exit code.
$ErrorActionPreference = "Continue"
Set-Location $PSScriptRoot
$env:PYTHONIOENCODING = "utf-8"
$py = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"

function Assert-Venv {
    if (-not (Test-Path $py)) { throw "No .venv yet. Run:  .\run.ps1 setup" }
}

switch ($Command) {
    "setup" {
        if (-not (Test-Path $py)) { py -3.12 -m venv .venv }   # plain "python" on this PC is 3.15 - never use it here
        $v = & $py --version
        if ($v -notmatch "Python 3\.12") { throw "Wrong Python in .venv: $v (need 3.12). Delete .venv and run setup again." }
        & $py -m pip install --no-cache-dir -r requirements.txt
        Write-Host "Ready: $v"
    }
    "build" { Assert-Venv; & $py build_catalog.py }
    "chat"  { Assert-Venv; & $py chat.py }
    "evaluate" { Assert-Venv; & $py evaluate.py }
    "web"   {
        Assert-Venv
        Write-Host "Chat:  http://127.0.0.1:8000"
        Write-Host "Admin: http://127.0.0.1:8000/admin    (stop the server with Ctrl+C)"
        & $py -m uvicorn server:app --host 127.0.0.1 --port 8000
    }
    "admin" { Assert-Venv; & $py admin.py @Rest }
    "test" {
        Assert-Venv
        $which = if ($Rest) { $Rest[0] } else { "all" }
        $more = if ($Rest -and $Rest.Count -gt 1) { $Rest[1..($Rest.Count - 1)] } else { @() }
        $failed = 0
        if ($which -in "all", "catalog")       { & $py test_catalog.py;             if ($LASTEXITCODE) { $failed++ } }
        if ($which -in "all", "conversations") { & $py test_conversations.py @more; if ($LASTEXITCODE) { $failed++ } }
        if ($which -in "all", "knowledge")     { & $py test_knowledge_loop.py;      if ($LASTEXITCODE) { $failed++ } }
        if ($which -in "all", "guardrail")     { & $py test_guardrail.py;           if ($LASTEXITCODE) { $failed++ } }
        if ($which -in "all", "web")           { & $py test_web.py;                 if ($LASTEXITCODE) { $failed++ } }
        if ($failed) { Write-Host "$failed test script(s) crashed"; exit 1 }
    }
    default { Get-Help $PSCommandPath -Detailed | Out-Null; (Get-Content $PSCommandPath -TotalCount 12) -join "`n" | Write-Host }
}
