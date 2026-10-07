<a id="sec-11-5"></a>
# PHANTOM — технические источники

Ненормативная трассировка к внешним техническим источникам и пояснения к platform/API evidence. Требования PHANTOM задаются соответствующими specs/tests; этот файл не может их переопределять.

Технические источники задают платформенные API/возможности; требования PHANTOM определяются этой спецификацией и собственными приёмочными тестами. Для конфликтующих страниц одного вендора применяется более новая специализированная документация, а exact pinned combination всё равно подтверждается P0 gate [План проверки §6](test-plan.md#sec-9-6).

<!-- BEGIN GENERATED TOC -->
<details>
<summary>Оглавление</summary>

- [1. Meta Quest / OpenXR](#sec-11-5-1)
- [2. EV3](#sec-11-5-2)
- [3. Сетевой протокол и аутентификация](#sec-11-5-3)
- [4. Visual Studio Code / Mermaid](#sec-11-5-4)

</details>
<!-- END GENERATED TOC -->

<a id="sec-11-5-1"></a>
## 1. Meta Quest / OpenXR

- **Meta — Simultaneous Hands and Controllers / Multimodality**
  https://developers.meta.com/horizon/documentation/unity/unity-multimodal/

- **Meta — Unity and OpenXR compatibility**
  https://developers.meta.com/horizon/documentation/unity/unity-and-openxr-compatibility/

- **Meta — MRUK Sample Overview / Trackables**
  Примеры Trackables API; выбранная SDK revision фиксируется в platform matrix ([Спецификация Quest §1](quest-specification.md#sec-5-1)).
  https://developers.meta.com/horizon/documentation/spatial-sdk/spatial-sdk-sample-mruk/

- **Khronos — OpenXR `XR_REFERENCE_SPACE_TYPE_LOCAL_FLOOR`**
  https://registry.khronos.org/OpenXR/specs/1.1/man/html/XR_REFERENCE_SPACE_TYPE_LOCAL_FLOOR.html

- **Unity — OpenXR Hand Interaction профиль**
  https://docs.unity.cn/Packages/com.unity.xr.openxr@1.18/manual/features/handinteractionprofile.html

- **Khronos — OpenXR 1.1, `XR_EXT_hand_interaction`**
  Стандартный grasp signal; применение и remap в PHANTOM: [Спецификация Quest §9](quest-specification.md#sec-5-9).
  https://registry.khronos.org/OpenXR/specs/1.1/man/html/XR_EXT_hand_interaction.html

- **Meta — Body Tracking for Movement SDK for Unity**
  Body skeleton и `Body_RightShoulder`. Выбор provider и actuator profile: [Спецификация Quest §1](quest-specification.md#sec-5-1); проверка совместимости: [План проверки §6](test-plan.md#sec-9-6).
  https://developers.meta.com/horizon/documentation/unity/move-body-tracking/

- **Meta — MRUK / Trackables / spatial capabilities**
  https://developers.meta.com/horizon/documentation/spatial-sdk/spatial-sdk-mruk/

- **Meta — Scene/Space Setup**
  Scene/Room API; применимость к запуску PHANTOM: [Спецификация Quest §2](quest-specification.md#sec-5-2).
  https://developers.meta.com/horizon/documentation/unity/unity-mr-utility-kit-manage-scene-data/

- **Meta — MRUK Spatial Testing**
  Средство автоматического тестирования пространственно-зависимой логики на нескольких конфигурациях помещений; интегрируется с Unity Test Runner и подходит для CI.
  https://developers.meta.com/horizon/documentation/unity/unity-mr-utility-kit-debug/


- **Meta — Unity MRUK QR Trackables**
  QR capabilities и ограничения частоты moving-pose updates; применение: [Спецификация Quest §16](quest-specification.md#sec-5-16).
  https://developers.meta.com/horizon/documentation/unity/unity-mr-utility-kit-qrcode-detection/

- **Android — Network обнаружение сервиса (`NsdManager`, DNS-SD/mDNS)**
  Platform discovery/resolve API; контракт PHANTOM: [Спецификация протокола §1](protocol-specification.md#sec-4-6).
  https://developer.android.com/develop/connectivity/wifi/use-nsd

- **Android — Local network permission / `NsdManager` API**
  Разрешения LAN; требования выбранной Android platform matrix: [Спецификация Quest §2](quest-specification.md#sec-5-2) и [Разработка и развёртывание §8](engineering.md#sec-8-8).
  https://developer.android.com/privacy-and-security/local-network-permission
  https://developer.android.com/reference/android/net/nsd/NsdManager

**Историческое наблюдение Body provider (2026-09-05).** В Meta XR Core `205.0.0`
наблюдалось отключение `OVRBody` при `SimultaneousHandsAndControllersEnabled`;
source inspection `85.0.0` обнаружил тот же guard. Locator исходного Unity package:
`https://packages.unity.com/com.meta.xr.sdk.core`, SHA-1
`f8b4cfb2789f06cb55ea30b9a379bf52c98d1af3`. Это объясняет необходимость проверки
конкретного provider, но не доказывает совместимость или несовместимость других версий.
Без доступного immutable report qualification остаётся `NOT_RUN`; требования к новому
P0 и его identity находятся в [План проверки §6](test-plan.md#sec-9-6).

<a id="sec-11-5-2"></a>
## 2. EV3

- **LEGO Education — EV3 User Guide**
  Встроенный Rotation Sensor Large/Medium Motor имеет разрешение `1°`; это измерение вала мотора, а физический угол сустава определяется через фактическую передачу.
  https://assets.education.lego.com/v3/assets/blt293eea581807678a/blta17299b86de85c10/5f8806b7ed5ccb12e4342e8e/ev3_user_guide_engb.pdf?locale=en-gb

- **ev3dev — Using the Tacho-Motor Class**
  Tacho attributes; интерпретация и startup-проверки PHANTOM: [Спецификация EV3 §5.1](ev3-specification.md#sec-7-5-1).
  https://www.ev3dev.org/docs/tutorials/tacho-motors/

- **ev3dev — EV3 sensor data**
  https://docs.ev3dev.org/projects/lego-linux-drivers/en/ev3dev-stretch/sensor_data.html

- **ev3dev — Networking**
  https://www.ev3dev.org/docs/networking/

- **ev3dev — Connecting to ev3dev Using SSH**
  SSH endpoint и настройка доступа; maintenance trust PHANTOM: [Разработка и развёртывание §7](engineering.md#sec-8-7).
  https://www.ev3dev.org/docs/tutorials/connecting-to-ev3dev-with-ssh/

- **Avahi — service publishing/browsing API**
  API публикации и обнаружения сервисов; service type/domain PHANTOM: [Спецификация протокола §1](protocol-specification.md#sec-4-6).
  https://avahi.org/doxygen/html/publish_8h.html
  https://avahi.org/doxygen/html/lookup_8h.html

<a id="sec-11-5-3"></a>
## 3. Сетевой протокол и аутентификация

- **RFC 768 — User Datagram Protocol**
  https://www.rfc-editor.org/info/rfc768/

- **RFC 2104 — HMAC**
  https://www.rfc-editor.org/info/rfc2104/

- **RFC 7518 — HMAC SHA-256 key-size guidance**
  https://www.rfc-editor.org/rfc/rfc7518.html

<a id="sec-11-5-4"></a>
## 4. Visual Studio Code / Mermaid

- **Visual Studio Code — Markdown diagram rendering**
  https://code.visualstudio.com/docs/languages/markdown#_mermaid-diagram-rendering

- **Visual Studio Code 1.121 — Mermaid Markdown Features встроен в VS Code**
  https://code.visualstudio.com/updates/v1_121#_mermaid-diagrams-in-markdown-preview-and-notebooks
