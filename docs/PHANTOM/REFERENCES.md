# PHANTOM — технические источники

> **Роль:** Ненормативная трассировка к внешним техническим источникам и пояснения к platform/API evidence. Требования PHANTOM задаются соответствующими specs/tests; этот файл не может их переопределять.
> **Владелец правил:** см. [`README.md`](README.md).


---

<a id="sec-11-5"></a>
## 11.5. Технические источники

Технические источники задают платформенные API/возможности; требования PHANTOM определяются этой спецификацией и собственными приёмочными тестами. Для конфликтующих страниц одного вендора применяется более новая специализированная документация, а exact pinned combination всё равно подтверждается P0 gate §9.6.

<a id="sec-11-5-1"></a>
### 11.5.1. Meta Quest / OpenXR

- **Meta — Simultaneous Hands and Controllers / Multimodality**
  https://developers.meta.com/horizon/documentation/unity/unity-multimodal/

- **Meta — Unity and OpenXR compatibility**
  https://developers.meta.com/horizon/documentation/unity/unity-and-openxr-compatibility/

- **Meta — MRUK Sample Overview / Trackables**
  QR/trackable configuration в используемой SDK-ветке должна быть pinned и P0/HIL-проверена; `configureTrackers()` на актуальной странице помечен как experimental/API subject to change.
  https://developers.meta.com/horizon/documentation/spatial-sdk/spatial-sdk-sample-mruk/

- **Khronos — OpenXR `XR_REFERENCE_SPACE_TYPE_LOCAL_FLOOR`**
  https://registry.khronos.org/OpenXR/specs/1.1/man/html/XR_REFERENCE_SPACE_TYPE_LOCAL_FLOOR.html

- **Unity — OpenXR Hand Interaction профиль**
  https://docs.unity.cn/Packages/com.unity.xr.openxr@1.18/manual/features/handinteractionprofile.html

- **Khronos — OpenXR 1.1, `XR_EXT_hand_interaction`**
  Стандартный `grasp_ext/value` является primary v1 grasp signal; PHANTOM использует identity mapping по умолчанию, а пользовательский endpoint remap является опциональным профилем.
  https://registry.khronos.org/OpenXR/specs/1.1/man/html/XR_EXT_hand_interaction.html

- **Meta — Body Tracking for Movement SDK for Unity**
  Body Tracking предоставляет обновляемый body skeleton; верхний joint set содержит `Body_RightShoulder`. Конкретный provider/API (`OVRBody` либо иной Movement SDK provider) и его совместимость с `Controllers and Hands`/Multimodal не предполагаются по названию функции, а фиксируются exact package matrix и P0. Если source/runtime конкретной pinned package revision содержит guard, отключающий выбранный provider при Multimodal, такая revision считается несовместимой до подтверждённого provider/version решения на реальном Quest 3; локальное наблюдение не формулируется как универсальное свойство всех Meta XR Core версий.
  https://developers.meta.com/horizon/documentation/unity/move-body-tracking/

- **Meta — Simultaneous Hands and Controllers (Multimodal), compatibility**
  Актуальная документация указывает несовместимость Multimodal с IOBT/FBS и FMM, а также ограничение passthrough + Multimodal + WMM. Это не доказывает совместимость конкретного `OVRBody` в каждой версии SDK. Поэтому actuator profile v1 фиксирует эти функции выключенными, квалифицирует выбранный базовый Body Tracking provider отдельно и остаётся заблокированным при расхождении документации с фактическим package source/runtime.
  https://developers.meta.com/horizon/documentation/unity/unity-multimodal/

- **Meta — MRUK / Trackables / spatial capabilities**
  https://developers.meta.com/horizon/documentation/spatial-sdk/spatial-sdk-mruk/

- **Meta — Scene/Space Setup**
  `Space Setup` относится к Scene/Room данным и используется PHANTOM только для включённых scene-aware UX-возможностей; core actuator gate не требует сохранённой room mesh/floor anchor. После системной операции приложение повторно проверяет именно capability/anchors, требуемые этой опциональной функцией.
  https://developers.meta.com/horizon/documentation/unity/unity-mr-utility-kit-manage-scene-data/

- **Meta — MRUK Spatial Testing**
  Средство автоматического тестирования пространственно-зависимой логики на нескольких конфигурациях помещений; интегрируется с Unity Test Runner и подходит для CI.
  https://developers.meta.com/horizon/documentation/unity/unity-mr-utility-kit-debug/


- **Meta — Unity MRUK QR Trackables**
  QR detection на Quest 3/3S требует Meta XR Core SDK v83+ и MRUK v83+, Spatial Data permission, Scene Support и Anchor Support. API предоставляет `MRUKTrackable`, 6DoF pose, `PlaneRect`/`PlaneBoundary2D` и payload; moving QR updates не являются realtime.
  https://developers.meta.com/horizon/documentation/unity/unity-mr-utility-kit-qrcode-detection/

- **Meta — Track QR codes in MR Utility Kit**
  QR tracking используется для инженерной калибровки и привязки при запуске; документация отдельно указывает, что moving QR pose обновляется не с частотой кадра и не подходит для realtime tracking.
  https://developers.meta.com/horizon/documentation/unity/unity-mr-utility-kit-qrcode-detection/

- **Android — Network обнаружение сервиса (`NsdManager`, DNS-SD/mDNS)**
  `NsdManager` принимает service type вида `_service._udp`/`_service._tcp`; PHANTOM поэтому передаёт `_phantom-ev3._udp`, а `local.` остаётся DNS-SD domain. Lifecycle discovery/resolve выполняется через platform NSD, а IP не является стабильной identity.
  https://developer.android.com/develop/connectivity/wifi/use-nsd

- **Android — Local network permission / `NsdManager` API**
  Android 17 (target SDK 37+) требует runtime `ACCESS_LOCAL_NETWORK` для broad LAN access; Android 16 restriction opt-in использует `NEARBY_WIFI_DEVICES`. System-mediated NSD picker может дать per-service access без broad permission, но PHANTOM v1 default использует explicit broad permission, пока picker UX не квалифицирован отдельно.
  https://developer.android.com/privacy-and-security/local-network-permission
  https://developer.android.com/reference/android/net/nsd/NsdManager

<a id="sec-11-5-2"></a>
### 11.5.2. EV3

- **LEGO Education — EV3 User Guide**
  Встроенный Rotation Sensor Large/Medium Motor имеет разрешение `1°`; это измерение вала мотора, а физический угол сустава определяется через фактическую передачу.
  https://assets.education.lego.com/v3/assets/blt293eea581807678a/blta17299b86de85c10/5f8806b7ed5ccb12e4342e8e/ev3_user_guide_engb.pdf?locale=en-gb

- **ev3dev — Using the Tacho-Motor Class**
  Для LEGO NXT/EV3 motors один tacho pulse соответствует одному градусу вал мотора, `count_per_rot=360`; `position` используется как абсолютный tacho count. При запуск PHANTOM проверяет motor `address` и `count_per_rot`, а не полагается на имя `motorN`.
  https://www.ev3dev.org/docs/tutorials/tacho-motors/

- **ev3dev — EV3 sensor data**
  https://docs.ev3dev.org/projects/lego-linux-drivers/en/ev3dev-stretch/sensor_data.html

- **ev3dev — Networking**
  https://www.ev3dev.org/docs/networking/

- **Avahi — service publishing/browsing API**
  Avahi принимает service `type` (например `_http._tcp`) и `domain` отдельными параметрами; default domain обычно `.local`. PHANTOM v1 использует `type=_phantom-ev3._udp`, `domain=local.` и IPv4-only publication до отдельной IPv6 qualification.
  https://avahi.org/doxygen/html/publish_8h.html
  https://avahi.org/doxygen/html/lookup_8h.html

<a id="sec-11-5-3"></a>
### 11.5.3. Сетевой протокол и аутентификация

- **RFC 768 — User Datagram Protocol**
  https://www.rfc-editor.org/info/rfc768/

- **RFC 2104 — HMAC**
  https://www.rfc-editor.org/info/rfc2104/

- **RFC 7518 — HMAC SHA-256 key-size guidance**
  https://www.rfc-editor.org/rfc/rfc7518.html

<a id="sec-11-5-4"></a>
### 11.5.4. Visual Studio Code / Mermaid

- **Visual Studio Code — Markdown diagram rendering**
  https://code.visualstudio.com/docs/languages/markdown#_mermaid-diagram-rendering

- **Visual Studio Code 1.121 — Mermaid Markdown Features встроен в VS Code**
  https://code.visualstudio.com/updates/v1_121#_mermaid-diagrams-in-markdown-preview-and-notebooks
