# Windows 7 Desktop carrier

This shell pins Electron **22.3.27**, Chromium108 and Node16.17.1. Its backend
is the repository's Python3.8.10 canonical Cordis composition. The original
rc.3 web application and its active ClientModules bundles are served over
`dsh-app://app`; no HTTP listener is mounted.

For a development checkout:

```powershell
<electron-22.3.27>/electron.exe apps/desktop --root . --python .venv/Scripts/python.exe
```

The application owns `$DSH_HOME/profiles/desktop` (default `~/.dsh`). Ctrl+,
opens its separate plugin manager. The Windows tray keeps the main window
available after closing it; Quit releases the Host and profile lease. Both
renderers use context isolation, sandboxing and disabled Node integration.
Only the owned top-level `dsh-app://shell` frame may invoke management IPC.
The owned app frame has separate environment/guide IPC. The preload does not
request these services while the main window temporarily displays `about:blank`.

Desktop uses the existing Python plugin ABI and accepts local folders or ZIP
packages. The original manager renderer is retained verbatim; its served input
placeholder and locale descriptions identify the supported package format.
Package mutations are serialized. A stopped-profile shadow transaction records
the exact old/new manifest and managed plugin bytes before publication. Host
readiness commits the generation; failed readiness or an interrupted pending
transaction restores the old generation. An interrupted committed transaction
finishes cleanup. Unexpected profile/plugin changes preserve the transaction
for inspection. User settings, sessions and installation junctions are outside
these snapshots. Retained upgrade generations use the canonical history store.

The upstream v3 frame format is unchanged. Windows stdio carries its binary
request/response frames; bounded stderr lifecycle messages replace Node's
fd3/fd4/fd5 process ABI. The shell streams protocol responses, propagates
cancellation and bounds buffered request bodies. Forced shutdown owns the
Windows child process tree, including a development venv redirector.

`scripts/build_desktop_inputs.mjs` reproduces the codec, locale, transport and
manager renderer from the clean pinned rc.3 Source checkout. The generated
`source-input.json` records every source/output hash. Development verification
uses `scripts/run_desktop_smoke.py --output <fresh-directory>` (optionally
`--limited-shell`); its parent owns the process through shutdown and keeps logs
in a regular file. Do not detach a GUI test with inherited temporary pipes.
The shell tolerates only `EPIPE` on inherited stdout/stderr when its launching
terminal closes; other stream errors remain errors. Packaged applications reject all
development overrides. The smoke entry verifies real RPC/streaming, renderer
isolation and actual plugin rollback. Expected control-stream errors during
Host replacement remain separately recorded, followed by a fresh baseline
check. Installer, update/release integration, x86 and physical Win7 acceptance
are separate milestones.

Standard installation may continue with a limited environment. Its finish page
and a dismissible first-launch notice point to the local `win7-setup.html` guide.
Build the separate x86/x64 prerequisite ZIP with
`scripts/build_windows_upgrade.py --external-prereq-dir <verified-inputs> --output-dir <fresh-directory>`.
This ZIP contains Microsoft prerequisites and the explicit administrator entry
`upgrade-win7.bat`; it does not add x86 application runtime support. AIO embeds
the matching prerequisite set. Neither builder executes the system installers.
