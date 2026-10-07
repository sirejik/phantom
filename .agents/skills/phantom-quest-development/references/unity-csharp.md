# C# и Unity assets

- Проверяй `.asmdef` и существующие compile symbols. Editor API остаётся в Editor assembly;
  чистая mapping/kinematics/state logic не зависит от MonoBehaviour/prefabs.
- Unity использует свою C#/BCL/IL2CPP матрицу. Не применяй .NET 8/C#12, primary constructors,
  `Task.Run` вокруг Unity API или NuGet web patterns без проверки поддержки target.
- SDK callbacks и network workers передают bounded snapshots. UnityEngine objects и UI
  изменяются на main thread; не блокируй его `.Wait()`/`.Result`. Отменяй или игнорируй
  устаревшие async результаты после disable/destroy/session change.
- В горячем frame/control path избегай повторной discovery, LINQ materialization, boxing и
  строкового logging. Измеряй alloc/time в соответствующем path, не переписывай всё ради GC.
- `JsonUtility` не равен произвольному JSON serializer: проверь null/empty, missing field,
  array/enum cases реальным Unity test, если на них зависит конфигурация/credential readiness.
- Сохраняй `.meta` GUID при перемещении assets. Для component/scene изменения сначала найди
  repo-owned scene builder; не переписывай prefab YAML или generated scene вслепую.
- При доступном Editor serialized property изменяется через `SerializedObject` и
  `ApplyModifiedProperties`, с корректным prefab override/save. Проверь persisted value
  после reload; одно успешное `SaveScene` не доказывает сохранение изменения.
- Для JNI/Android bridge проверь thread attachment, освобождение wrappers, lifecycle
  callbacks, permission-denied и resource-release paths. Исходники bridge находятся в
  `PhantomQuest/Assets/Plugins/Android`; generated Gradle outputs не являются владельцем.

Смена feature settings требует проверки итогового manifest, а не универсального вызова
новейшего SDK helper. Используй API именно установленной revision и существующий PHANTOM build path.
