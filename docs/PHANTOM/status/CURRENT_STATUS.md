# Текущее состояние реализации PHANTOM

## Физический Stage-3 gate от 2026-09-06

Физический запуск network-only candidate `4c842f9a4916389fd5b2898320f840a30763b7ec`
не дал Stage-3 PASS. PRE-INSTALL прошёл, exact Quest Diagnostic APK был установлен и его bytes
подтверждены обратным pull/hash. Quest DEVICE AUTO остаётся `NOT_RUN`: Horizon Guardian перехватил
фокус по `TRACKING_LOST` до старта scene runner и app report не был создан; safety UI не обходился.

EV3 installer проверил exact package и дошёл до DEVICE AUTO, где выявил несовместимость runner с
deterministic build manifest (`built_at` отсутствует по контракту). Installer выполнил rollback;
наблюдаемые duty/speed всех найденных motor nodes оставались нулевыми. Исправление и regression
подготовлены, но DEVICE/HIL PASS переносится только после clean rebuild и повторной установки exact candidate.
Текущий итог физической приёмки Stage 3 — **NOT COMPLETE**. Рабочая последовательность и точные
оставшиеся evidence описаны в `exec-plans/STAGE3_HARDWARE_ACCEPTANCE.md`.

> **Ревизия источника состояния:** 2026-09-06.
> **Тип:** ненормативное summary. Источником PASS/FAIL являются versioned machine-readable
> reports в repository `results/**`; этот файл никогда не заменяет PRE-INSTALL/DEVICE/HIL/manual
> evidence.

## Текущий подтверждённый split-spec software/build baseline

Для clean source candidate выполнен полный Stage-3 PRE-INSTALL:

```text
source candidate commit: 565da0ac0e022b8c931fcdb24a986d931b602025
source_tree_hash:
156b12318d179d7a88c507f2faf07f6439d8c96739407c8deffec29c786aaefe
split specification_sha256:
c665c4c48d108a607b3812bb8eadbe6b9bdeede08fd5efd08d8f28963064371c
protocol_schema_hash:
48d85291e972cb6a954c7a8549349ba28c39f8f5b411d8e2a056f64bfb3317e3
PRE-INSTALL report: results/pre-install/report.json
report SHA-256:
bc2f741715a59485b19d460c631ca2fabaac3606cb6562b55a6fa6dd1ee92f26
worktree_dirty: false
install_authorized: true
```

`powershell scripts/pre-install-auto.ps1 -Stage 3` завершился `PASS`: 20/20 обязательных
software/build checks. Golden wire vectors — `21/21 PASS`; Quest exact decode/re-encode —
`21/21 PASS`; Python protocol `5/5`; EV3 network/security `9/9`; simulator `9/9`;
tracking replay `2/2`; Quest pure core `81` checks; localhost UDP `9` scenarios;
Unity EditMode `26/26`; EV3 host Release/Diagnostic `2/2` каждый; ASan/UBSan `2/2`;
ARMEL Release/Diagnostic build PASS; secret scan PASS.

## Stage status

| Область | Состояние на split candidate `565da0a` |
|---|---|
| Stage 1 specification consistency | `PASS` |
| Stage 1 implementation/regression | `PASS` |
| Stage 2 specification consistency | `PASS` |
| Stage 2 implementation/regression | `PASS` |
| Stage 3 specification consistency | `PASS` |
| Stage 3 EV3-side implementation | `PASS` |
| Stage 3 Quest-side implementation | `PASS` |
| Stage 3 protocol interoperability | `PASS` |
| Stage 3 host/simulator validation | `PASS` |
| Stage 3 build validation | `PASS` |
| Real Quest 3 validation | `NOT_RUN` |
| Real EV3 new-build DEVICE AUTO | `NOT_RUN` |
| Quest ↔ real EV3 integration | `NOT_RUN` |
| Stage 3 physical acceptance | **NOT COMPLETE** |

Stage 3 остаётся строго network-only:
`qualification_only=true`, `actuator_scope_mask=0x00`,
`safety_observation_mask=0x00`, `required_user_inputs=NONE`.
Этот scope не создаёт motor authority и не допускает product `READY/TRACKING`.

## Исторический pre-migration provenance

До migration Stage 1–3 software/build gate проходил на commit
`eb1339842045548c7224e2a8ae4da7b5158b9508` с monolithic
`specification_sha256=419d936d5ddede106332d46abac98e0650de6b90aee0d86f898bc757826c7e3d`.
Его report имел SHA-256
`b573f5dc773cb67c7e5853086b8034054d37875c7f24bc1f30a1550d7ff6775f`.

Этот PASS и старые artifact/build identities остаются только provenance: новый split
candidate прошёл собственную генерацию, сборку и PRE-INSTALL и не наследует их.

## Зафиксированные implementation facts, которые нельзя потерять

- `phantom-network` не имеет motor-write authority; `phantom-controller` является
  authoritative для session/scope/state/safety admission.
- Stage-3 IPC использует фиксированный versioned contract, peer credentials, boot/session
  generation, freshness и bounded drain; malformed/stale/lost IPC fail-safe.
- Runtime identities разделены на `phantom-ctrl`, `phantom-net`, `phantom-mdns` и отдельные
  DAC groups; network process не входит в motor-I/O group.
- Quest CONTROL credential хранится как AES-GCM ciphertext в app-private preferences;
  wrapping key non-exportable в Android Keystore; storage/decrypt failure fail-closed.
- Quest discovery использует `_phantom-ev3._udp.local.`, IPv4-only Stage-3 contract и
  инвалидирует endpoint/session state при service/endpoint/boot lifecycle changes.
- Network-only TELEMETRY не выдумывает reference/payload/safety readiness: неприменимые
  значения canonical `N_A`/zero, `PayloadState.UNKNOWN`.
- Release package/install остаётся заблокированным без valid qualification evidence; compile
  или APK/ELF build сам по себе не является production qualification.

## Текущие split-spec artifacts

Artifacts ниже относятся к clean candidate `565da0a`, split
`specification_sha256=c665c4c4...` и текущему `protocol_schema_hash=48d85291...`:

| Artifact | Profile | SHA-256 | Build ID |
|---|---|---|---|
| `PhantomQuest-diagnostic.apk` | Diagnostic network-only | `b2402ee274afc8b2694d4f8d662616dc2923b6aa0a31b5721ef4545c04b54f22` | `c636fbdf7a507dbd0a1ccaeacc92fcee508b5313320c1ddfcf70ca8accbf61b4` |
| `PhantomQuest-release.apk` | Release compile artifact | `467b60e4b92d3328a80eb0a3611779360569be73d9c2e272a2a9007d7893df9b` | `b55f5f0e8a95a3380a0c1bc3a4c327d5ea534ff224e1d0fbf6e2089a6bc19a60` |
| EV3 Stage-3 Diagnostic package | ARMEL network-only | `a6e110607e4370a7391733995f9df9ba858505a2881d2a26287abdbbdeaf1bc6` | `c66d18b8768ebd217b6a2f65228bc7cb010ea4becc7fb87ca390c8bfa343beef` |

EV3 Release ARMEL binaries также собраны (`build_id=57cda0afb8213639d06c8010f267e3220fb9c6986d4170de35dc0cc44f534644`),
но installable Release tar намеренно не выпускался: qualification evidence отсутствует.

## Следующий физический gate Stage 3

Для физического acceptance текущего split-spec candidate:

1. deploy нового EV3 Diagnostic network-only package;
2. установить новый Quest Diagnostic APK;
3. выполнить EV3 new-build DEVICE AUTO;
4. проверить Quest Android lifecycle и real NSD discovery;
5. проверить real CONTROL HELLO/HELLO_ACK, PING/PONG и live TELEMETRY/freshness;
6. проверить reconnect, controller restart/session invalidation, EV3 reboot, IP change,
   service remove/re-add;
7. доказать `nonzero_motor_writes=0` во всём Stage-3 network-only сценарии;
8. зафиксировать Stage-3 physical acceptance.

До фактического выполнения этих случаев:

```text
Quest physical tests = NOT_RUN
EV3 physical tests = NOT_RUN
Quest↔EV3 physical integration = NOT_RUN
Stage 3 = NOT COMPLETE
```

## Будущий full-arm blocker

Pinned Meta XR Core 205 содержит explicit SDK guard, несовместимый с требуемым будущим
simultaneous hands/controllers full multimodal actuator profile. Для Stage-3 network-only
Diagnostic это `N_A`; полный `FULL_ARM_USER`/Release motion path остаётся не
квалифицированным до выбора совместимой provider/platform matrix и real Quest P0.
