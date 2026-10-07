# NicoTools — Android Studio 插件

## 开源许可

NicoTools 插件源码、图标和随插件提供的模板参考资源采用 [MIT License](LICENSE)。允许使用、修改、分发和商业使用，须保留完整的版权及许可声明；软件按原样提供，不提供担保。

Copyright (c) 2026 popkter。公开源码：[popkter/PopToolProject — plugins/jetbrains](https://github.com/popkter/PopToolProject/tree/develop/plugins/jetbrains)。

许可范围为此插件目录，不改变 PopToolProject 其他目录的授权条款。IDE、Android 插件及外部运行工具保留各自的许可，详见 [依赖说明](THIRD_PARTY_NOTICES.md)。安装包根目录及插件 JAR 的 `META-INF` 中均包含许可文本。

首版面向 Windows、Android Studio 2026.1.1 Patch 2 及更高版本，编译与验证基准为 `AI-261.23567.138.2611.15646644`，使用 IDE 自带的 Java 运行插件，字节码要求 Java 21 或更高。插件不打包脚本解释器、adb 或 scrcpy。

## 本地安装

1. 在仓库根目录执行：

   ```powershell
   ./plugins/jetbrains/build.ps1 -IdePath '你的 Android Studio 安装目录' -Test
   ```

2. 在 Android Studio 中打开 **Settings → Plugins → 齿轮 → Install Plugin from Disk**。
3. 选择 `plugins/jetbrains/build/nicotools-0.1.0.zip`，按 IDE 提示重启。
4. 从 **Tools → NicoTools** 或右侧 **NicoTools** 工具窗口开始使用。

构建直接使用指定 IDE 的 JDK 和 API 库，不需要另外安装 Gradle，也不会下载或打包 IDE 本体。构建接受 Android Studio AI-261 及更高平台版本。发布包默认使用上述最低版本基准编译，以避免引入仅新版本存在的 API。

插件目录也可单独构建：在此目录执行 `./build.ps1 -IdePath '你的 Android Studio 安装目录' -Test`。运行时模板资源已包含在插件源码中；仅下文的可选 PopTool 对照数据生成器需要原项目的 Python 开发环境。

插件声明最低平台版本为 `261`，不设置最高版本，允许后续版本加载。当前已验证 Android Studio 2026.1.1 Patch 2；未来版本仍需进行终端选区、Android 设备选择和脚本执行回归验证，API 变化时需要更新适配。其他 JetBrains 产品尚未验证，且当前插件依赖 Android 和 Terminal 插件。

## 使用

- **终端选区**：在本地终端选中文本，右键选择“新建 NicoTools 自定义脚本”。选区进入脚本正文，保存前不执行。支持经典终端和 Reworked 终端。
- **全局操作**：顶部原生图标工具栏仅保留新建脚本、批量操作、导入和环境路径四项，悬停显示操作说明。
- **脚本管理**：列表按名称、类型、说明展示，使用 IDE 原生表格及主题选中效果。右键脚本行可执行、编辑、分享或删除该脚本；菜单采用原生图标和分隔线。双击脚本直接进入执行流程，有参数时仍先填写参数。右键或双击列表空白处不会操作脚本；选中后可用 Shift+F10 打开菜单。
- **脚本模板**：在新建或编辑弹窗中打开“脚本模板与参数语法”，复用原项目帮助页的示例代码，可预览参数替换结果并复制代码；不新增独立模板库或“保存为模板”功能。
- **参数**：保存时根据正文、参数数组、环境变量和工作目录生成输入表单。支持 `${名称}`、`${名称:默认值}`、`${名称=旧格式默认值}`、`${模式:开启=1|关闭=0}`、`${路径@file}`、`${路径@dir}`，以及 `Var/pVal` 声明。声明行在执行前移除，替换保留 PopTool 的字面语义。
- **执行配置**：可设置工作目录、解释器、依赖工具、输出编码、超时、参数数组及环境变量。高级参数元数据保留 PopTool 的必填、文本、多行、数字、布尔、下拉、文件、目录、密码和 Android 设备类型。
- **输出**：当前项目中每个脚本复用一个 IDE Run 标签，显示打印、错误和退出码，可停止或再次运行。完成后重新执行会清空旧输出；脚本改名后仍按脚本 ID 复用标签。启动中或运行中重复点击会切回已有控制台，不额外启动进程。不同脚本可并发运行且各自保留标签，关闭标签后下次执行会重新创建。参数在运行前填写；运行中的标准输入关闭，不支持交互菜单。

示例：

```text
Var message = ${消息:你好}
Var mode = ${模式:开启=1|关闭=0}
Write-Output '${message}'
Write-Output '${mode}'
```

参数值按原语法直接替换；脚本作者负责按照目标语言正确处理引号。

## 环境路径

打开 **Settings → NicoTools**，或点击脚本管理界面的“环境路径”，可指定 Python、PowerShell、Bash、cmd、adb 和 scrcpy 可执行文件的绝对路径。

优先级：**脚本解释器路径 → 插件设置路径 → IDE 进程继承的系统 PATH**。显式路径无效时报错，不自动回退。系统 PATH 中 PowerShell 优先查找 `pwsh`，再查找 `powershell`；Python 查找 `python`，再查找 `python3`。

修改系统 PATH 后通常需要重新启动 IDE。插件不继承终端中临时激活的虚拟环境，不自动搜索项目 Android SDK，不安装环境或管理 adb 服务。声明依赖时填工具名称，例如 `adb, scrcpy`。只有当前脚本所需依赖会阻止运行。

配置工具目录会加入本次运行的 PATH；同时提供 `POPTOOLS_ADB`、`POPTOOLS_SCRCPY` 等完整路径环境变量。工具文件名与调用名不同的脚本，应使用对应完整路径变量。

## Android 设备

设备模式：

- `use`：要求当前项目运行工具栏选择一个在线 Android 设备。
- `none`：不从 IDE 获取设备，适用于 `adb devices` 等命令。
- `auto`：识别直接 adb 命令；单条 `adb devices`、`adb version`、`adb help` 不要求设备。通过 Python、包装程序或动态命令调用 adb 时，应明确设为 `use`。

运行前读取所选设备序列号并设置本次子进程的 `ANDROID_SERIAL`。未选、离线、未授权、尚未就绪或选择多个设备时提示并停止启动。执行中切换 IDE 设备不改变本次默认目标。脚本中的显式设备参数或环境变量仍按工具自身规则覆盖默认目标。

scrcpy 脚本应设置 `use` 并显式传递所选设备，例如 PowerShell 使用 `scrcpy -s $env:ANDROID_SERIAL`。插件不新增设备列表，不连接设备，不调用服务重启命令。

## 数据导入与存储

“导入”读取剪贴板中的脚本定义；“分享”将当前脚本复制到剪贴板，并像原 PopTool 一样移除参数默认值、保留下拉选项定义。支持 PopTool `poptools.custom-script` v1 分享 JSON、原始 v1 工具 JSON、工具 JSON 数组，以及包含 `scripts` 数组的对象。

冲突时选择覆盖、另存或跳过；批量导入逐条报告失败，不修改原文件。未知字段、未知参数类型或不支持的执行类型会明确报错；`internal`、`url` 运行方式不属于本次脚本迁移范围。PopTool 内部资源路径、托管环境和专用环境变量不能直接在 IDE 中复用，需要在导入后改为系统路径。

脚本和工具路径使用 IDE 用户级配置 `options/poptool-scripts.xml` 持久化，跨项目共享。默认工作目录在每次运行时解析为当前项目根目录；相对目录基于项目根目录。

“批量操作”提供批量目录导入和导出，保留默认值。导入前将当前库备份到 IDE 配置目录的 `poptool-backups`，读取所选目录（优先使用其中的 `tools` 子目录）的脚本 JSON，不修改来源文件。直接引用导出目录内 `.py/.ps1/.sh/.bat/.cmd` 文件的脚本会复制到 IDE 配置目录的 `poptool-assets`，保留同目录依赖并调整入口路径。导出在所选目录内新建带时间戳的目录，定义存入 `tools`；直接引用绝对路径脚本文件时，复制其所在目录的文件到 `scripts` 并改为相对入口，以便重新导入。动态引用、工作目录之外的资源及外部解释器路径仍需用户自行迁移或配置。

## 验证

`build.ps1 -Test` 运行核心语法、数据格式和环境解析检查。

在 PopTool 仓库开发环境中，还可生成与原实现对照的测试数据：

```powershell
./.venv/Scripts/python.exe ./plugins/jetbrains/verify_poptool_compatibility.py ./plugins/jetbrains/build/poptool-compatibility.json
./plugins/jetbrains/build.ps1 -IdePath '你的 Android Studio 安装目录' -Test -CompatibilityFixture ./plugins/jetbrains/build/poptool-compatibility.json
```

```powershell
./plugins/jetbrains/smoke.ps1 -IdePath '你的 Android Studio 安装目录'
```

此命令启动独立 Android Studio 开发实例，配置、缓存、插件和测试项目都位于 `build/smoke-时间戳`，不安装到日常 IDE 配置中。测试包额外包含集成检查类，发布 ZIP 不包含该类。检查结果写入该目录的 `report.txt`，日志位于 `log/idea.log`；测试结束自动退出开发实例。

人工验收应覆盖真实设备的在线、离线、授权和多设备选择，以及已安装的 Python/Bash/scrcpy 实际脚本。使用停止操作时只终止本次运行的可追踪进程树，不停止共享 adb 服务；脚本主动脱离父进程的程序不保证可以追踪。
