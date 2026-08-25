# PHANTOM Quest 3 — техническое ревью v20

Дата: 2026-08-25

## Итог

Release APK собран и подписан. Редакторский аудит, компиляция и 14 EditMode-тестов пройдены. Физическая проверка изображения, рук и контроллера на Quest 3 остаётся обязательной: статический аудит не может подтвердить отсутствие мерцания на дисплее шлема.

## Ответы по tracking/rendering

- В сцену добавлены два официальных `OVRRuntimeControllerPrefab` под `LeftControllerAnchor` и `RightControllerAnchor`. При подключённом Touch-контроллере Meta runtime загружает подходящую виртуальную модель и анимирует кнопки. Модель отображается по состоянию подключения и input focus.
- В Unity должна быть одна активная render-камера — `CenterEyeAnchor` внутри одного `OVRCameraRig`. Это не количество физических tracking-камер Quest 3: сенсорные камеры обрабатываются Horizon OS/OpenXR и продолжают участвовать в tracking рук и контроллеров.
- Руки обновляются в `BeforeRender`, контроллеры — с `LateControllerUpdate`. `Hand Tracking Frequency = Low` оставлен намеренно: в Meta SDK это рекомендуемый balanced default, а High/Max — Fast Motion Mode с дополнительной стоимостью и ограничениями для simultaneous hands + controllers.

## Найденные и исправленные проблемы

1. Удалён Google Android XR package `com.unity.xr.androidxr-openxr` и все оставшиеся serialized Android XR features. Они не относятся к Meta Quest.
2. Добавлены официальные runtime-модели левого и правого Touch-контроллера; включён Render Model Support.
3. Сохранена одна камера, один `OVRCameraRig`, один `OVRManager`, один `AudioListener` и один passthrough background layer. `XROrigin`, FixedUpdate tracking и demo locomotion запрещены аудитом.
4. HUD остаётся обычным world-space Canvas в eye buffer. OpenXR Composition Layers feature сохранена как зависимость Meta OpenXR, но активные `Unity.XR.CompositionLayers.CompositionLayer` в сцене запрещены.
5. Foveation, SpaceWarp, subsampled layout, late latching и dynamic resolution выключены для диагностического baseline; используется только OpenGLES3, URP 4x MSAA, без HDR/depth/opaque textures.
6. Устаревший и не поддерживаемый OpenXR вызов `OVRBoundary.OuterBoundary` удалён. Приложение требует локализованную текущую MRUK-комнату, валидный floor и многоугольник активной границы от единственного running `XRInputSubsystem`; малая stationary boundary отклоняется.
7. Исправлены тексты Space Setup: закрытие системного окна больше не трактуется автоматически как успешная настройка.
8. Уменьшен шрифт HUD, включено вертикальное обрезание переполнения, увеличена длина переноса.
9. Убраны синхронные flush каждой JSONL-записи: данные сбрасываются не реже одного раза в секунду и при `Dispose`.
10. Исправлена область действия define: Meta CPU/GPU/compositor metrics теперь действительно входят в `Phantom.Runtime` и release APK.

## Совместимость

- Unity 6000.3.22f1.
- Meta XR Core SDK 205.0.0 и MRUK 205.0.0 — одинаковая версия.
- Unity OpenXR 1.17.1, Meta OpenXR 2.5.1, XR Hands 1.8.1.
- Android XR package отсутствует в manifest и lock-файле.
- Package name: `dev.phantom.questprototype`.
- Meta App ID в Oculus Platform Settings: `1405011949353501`.

## Проверки и артефакт

- Scene/build audit: PASS — rigs=1, managers=1, cameras=1, listeners=1, passthrough=1, hand visuals=2, controller visuals=2.
- Unity EditMode: 14/14 PASS.
- Android release build: Success, ARM64, target SDK 34, versionCode 20.
- APK signature v2: PASS; один RSA-4096 signer.
- Certificate SHA-256: `2374d7eeeaa983ae4b8bf7d24721b4f410d9eb83264b03ca7a6271099c3c1dd7`.
- APK SHA-256: `718b01b8c2748ca8c4a9fe31b007b5ff1b87260b6e1c4fd2ee0a8260a972b4d8`.
- APK: `build/quest/PhantomQuest-release-v20.apk`.
- Test report: `results/quest/editmode-v20.xml`.

## Документация

- Meta, OVRCameraRig: https://developers.meta.com/horizon/documentation/unity/unity-ovrcamerarig/
- Meta, runtime controller models: https://developers.meta.com/horizon/documentation/unity/unity-runtime-controller/
- Meta, Fast Motion Mode: https://developers.meta.com/horizon/documentation/unity/fast-motion-mode/
- Unity OpenXR 1.17: https://docs.unity3d.com/Packages/com.unity.xr.openxr@1.17/manual/index.html
- Unity Android XR 1.3: https://docs.unity3d.com/Packages/com.unity.xr.androidxr-openxr@1.3/manual/index.html
- Unity Meta OpenXR 2.5: https://docs.unity3d.com/Packages/com.unity.xr.meta-openxr@2.5/manual/index.html
