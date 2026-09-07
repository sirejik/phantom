# Phantom EV3 bench characterization

This is an **experimental measurement harness**, not the Phantom production motor controller. It targets ev3dev Stretch, armel/ARMv5TEJ, C++14, and direct `/sys/class/tacho-motor` access. It works over an EV3 USB network link; Wi-Fi is not required.

## Non-negotiable safety rules

- Disconnect the long/heavy robot arm. Use a free shaft or a short, light LEGO pointer only.
- Never hold or stop a shaft with fingers. E7 needs a short beam that meets a firmly mounted soft stop.
- Begin at low duty. Tests have bounded phases; Ctrl+C/SIGTERM sets a stop request and every normal/exception exit applies duty 0, `stop_action=brake`, `command=stop`.
- `--arm` means the operator has inspected the rig and intentionally enables motion. E7 additionally requires `--stall-fixture`; E9 requires `--crash-ack`.
- E9 baseline is intentionally dangerous: it tests whether `run-direct` survives process death. It uses 12% duty and an independent parent watchdog stops it after 150 ms. Keep physical access to the brick.

## Relationship to production PHANTOM

This harness is **not** part of the production runtime and is outside the PHANTOM
safety perimeter. It has its own wiring, its own port mapping and its own
privilege model, none of which describe the assembled robot:

| | bench harness | production PHANTOM |
|---|---|---|
| port mapping | Large=`outB`, Medium=`outA` (whatever the current rig is wired as) | `outA` Base, `outB` Shoulder, `outC` Elbow, `outD` Gripper, fixed by `config/source/ev3.json` |
| motor authority | direct `run-direct` writes from `ev3-bench` | only `phantom-controller`, masked by `actuator_scope_mask` |
| privileges | `robot` via a NOPASSWD sudo rule | dedicated `phantom-ctrl` / `phantom-net` service identities and DAC groups |
| results | `results/ev3/**` characterization captures | `results/**` gate evidence tied to a build identity |

A bench port mapping is never evidence about production wiring, and a bench
result is never a DEVICE/HIL gate result.

**Do not leave the bench sudo rule on a brick that will run production.**
`deploy/scripts/install-release` removes `/etc/sudoers.d/phantom-ev3-bench`
before installing and refuses to continue if it cannot, because that rule grants
NOPASSWD root on a `robot`-writable path and would bypass the privilege
separation the production safety argument relies on.

The currently measured bench mapping is Large=`outB`, Medium=`outA`. Discovery always matches sysfs `address` and verifies `driver_name`; it never relies on `motor0`/`motor1` numbering. Override ports only with `--large-address` and `--medium-address` after a new E0 capture.

## USB setup and build

The scripts default to `robot@192.168.0.1`, the usual ev3dev USB gadget address. Override it for the current shell if needed.

Linux, macOS, WSL, or Git Bash:

```sh
export EV3_HOST=robot@ev3dev.local
```

PowerShell:

```powershell
$env:EV3_HOST = 'robot@ev3dev.local'
```

Do not add backslashes before `_` or `@`; they are not special in either assignment. The deployment scripts are POSIX shell scripts. From PowerShell, run them through Git Bash (or use WSL):

```powershell
$bash = 'C:\Program Files\Git\bin\bash.exe'
& $bash scripts/ev3-bench-build --on-brick
if ($LASTEXITCODE -ne 0) { throw 'EV3 build failed' }
& $bash scripts/ev3-bench-run e0
```

Environment variables set through `$env:` are inherited by Git Bash. The assignment lasts for the current PowerShell session.

The scripts store the accepted EV3 host key in the repository-local, ignored `.ev3-ssh/known_hosts`. This avoids Git for Windows failures when the Windows profile path contains non-ASCII characters. On the first connection, verify the displayed fingerprint belongs to your brick and answer `yes`; subsequent script calls should not ask again. The post-quantum key-exchange warning comes from the old SSH server in ev3dev Stretch and does not indicate a failed connection.

To stop password prompts, provision the bench-only SSH key once. It creates an unencrypted private key in the ignored `.ev3-ssh/` directory and asks for the `robot` password only for this setup step. Do not put a password in a script, command line, or password manager integration.

```powershell
& $bash scripts/ev3-bench-setup-key
```

After E0, use the observed `address` fields to pass the current port mapping explicitly. The example below uses the currently measured rig mapping (Large=`outB`, Medium=`outA`); substitute whatever E0 reported for your rig:

```sh
scripts/ev3-bench-run e1 --large-address outB --medium-address outA --motor all --mode persistent --rate 50
```

Motor sysfs command attributes are normally root-writable on ev3dev. Provision a restricted rule once before the first test that executes the bench binary. It asks for the `robot` password on the brick once, validates the sudoers fragment, and grants passwordless root access only to `/home/robot/phantom-bench/bin/ev3-bench`—not general passwordless sudo.

```powershell
& $bash scripts/ev3-bench-setup-sudo
```

The run script then uses `sudo -n`; it fails rather than waiting for a hidden password prompt if that rule is absent.

Cross-build with an `arm-linux-gnueabi` GCC toolchain and deploy:

```sh
scripts/ev3-bench-build
scripts/ev3-bench-deploy
```

When Docker is available, the recommended Windows workflow uses the ev3dev Stretch cross-toolchain image and does not require CMake or an ARM compiler on Windows or the brick:

```powershell
$env:EV3_HOST = 'robot@ev3dev.local'
$bash = 'C:\Program Files\Git\bin\bash.exe'

& $bash scripts/ev3-bench-build --docker
if ($LASTEXITCODE -ne 0) { throw 'EV3 Docker build failed' }

& $bash scripts/ev3-bench-deploy
if ($LASTEXITCODE -ne 0) { throw 'EV3 deploy failed' }

& $bash scripts/ev3-bench-run e0
```

The default image is `ev3dev/debian-stretch-cross:latest`; override it with `EV3_DOCKER_IMAGE` if the same toolchain is stored under another local tag. The resulting binary is `build/ev3-bench-armel/ev3-bench`.

If CMake and a compiler are installed on the brick, build there instead:

```sh
scripts/ev3-bench-build --on-brick
```

The on-brick build uses CMake when available and otherwise compiles directly with `g++`. If neither is installed, it exits with a clear error. Future timestamps from an incorrectly set EV3 wall clock are discarded during source extraction; benchmark timestamps use a monotonic clock and do not depend on wall-clock synchronization.

The runner uses only SSH over USB. Start with environment capture and stationary timing:

```sh
scripts/ev3-bench-run e0
scripts/ev3-bench-run e0 --manual-e0
scripts/ev3-bench-run smoke
scripts/ev3-bench-run e1 --mode persistent --rate 50 --duration 60
scripts/ev3-bench-run e1 --mode naive --rate 50 --duration 60
scripts/ev3-bench-run e1 --mode timing-only --rate 50 --duration 60
scripts/ev3-bench-run e1 --mode persistent --rate 50 --duration 60 --motor large
```

Only after inspecting the free-shaft rig:

```sh
scripts/ev3-bench-run e2 --arm --motor large
scripts/ev3-bench-run e4 --arm --motor medium
scripts/ev3-bench-run e7 --arm --stall-fixture --motor medium
scripts/ev3-bench-run e9 --arm --crash-ack --motor medium --fault sigkill
```

Use `--duration` for a short smoke run before the specified full run. It changes phase length, so label and exclude smoke logs from final claims. E11 is analysis-only because voltage is recorded in every motor row. E12 runs 120 s stationary without `--arm`; passing `--arm` adds the 30 s free-spin phase.

Pull and analyze:

```sh
scripts/ev3-bench-pull-logs
scripts/ev3-bench-validate
```

`results/ev3/raw/` and `results/ev3/environment.*` are local captures and are
ignored by Git. The small Markdown/SVG outputs in `results/ev3/summaries/` are
the reviewable artifacts. This keeps a commit reproducible without trying to
store every hardware-specific CSV capture.

Raw CSV contains a monotonic timestamp, test/run identity, address and driver, battery voltage, command/duty, encoder position/speed/state, loop interval, target/error, events and faults. The logger buffers in RAM and writes once at test completion. A sudden power loss can therefore lose the current test; this is deliberate so filesystem I/O does not contaminate loop timing.

## Test matrix

| Test | Purpose | Motion gate |
|---|---|---|
| E0 | Environment, ABI, sysfs capabilities | none |
| E1 | 25/50/75/100 Hz jitter; reopen vs persistent FD; optional 20% spin | `--arm` for spin only |
| E2 | Bidirectional duty/speed curves | `--arm` |
| E3 | Step response and coast/brake/hold | `--arm` |
| E4 | Conservative P/PD `run-direct` feasibility | `--arm` |
| E5 | 100 absolute-target cycles (no software accumulation) | `--arm` |
| E6 | Low-speed threshold and stick-slip | `--arm` |
| E7 | Medium controlled-stall raw data | `--arm --stall-fixture` |
| E8 | Medium triangle/sine proportional tracking | `--arm` |
| E9 | Separate controller/safety processes and crash modes | `--arm --crash-ack` |
| E10 | Local trigger-to-brake path | `--arm` |
| E11 | Battery sensitivity, offline | none |
| E12 | Two-motor scheduler/I/O stress | optional `--arm` spin |
| E13 | `run-to-abs-pos` reference | `--arm` |

The free-motor bench cannot establish loaded torque, gear ratios, gravity compensation, backlash, loaded speed, homing repeatability, or four-motor schedulability. Those remain open until the mechanical prototype and full motor set exist.

For E9 the runner forks two OS processes and names them `bench-controller` and `bench-safety`. The controller is the normal sysfs writer and emits a 20 ms pipe heartbeat. After fault injection the safety process first kills/quiesces that writer, then writes duty 0 + brake + stop, avoiding a two-writer race.
