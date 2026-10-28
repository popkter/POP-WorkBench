# 开发、测试与构建

本文面向项目开发者。日常安装和使用请阅读 [README](../README.md)。

悬浮窗使用分层组件：`FloatingLauncher.qml` 管理窗口、置顶和展开收起；`CustomScriptList.qml` 共用搜索、筛选、排序并按主题加载展示组件；`StandardScriptList.qml` 显示普通列表，`DecadeScriptDeck.qml` 管理卡包叠放及抽出、归还的位置与遮挡。两种展示组件通过统一的激活、归还接口与外壳交互，共用 `ScriptCollectionView.qml` 的滚动和键盘导航。`ScriptCardStore.qml` 独立持有卡面对象，生命周期不依赖列表项或主题组件，切换主题时可继续复用正在飞行或已抽出的卡面。

快速点击时，卡包同步保留卡面以合并重复请求，窗口创建在鼠标事件结束后派发，不等待其他卡牌动画。列表关闭离屏委托缓存，避免快速移除行时取消仍在异步创建的委托；首帧通知也不直接修改源列表模型。窗口关闭会取消尚未完成的表单加载。排查闪退时可结合用户数据目录下的 `logs/native-faults.log`、`logs/app.log` 和 Windows 应用程序错误事件；应用日志中的卡片请求只记录脚本 ID 和卡片数，不记录命令或参数内容。

项目使用 Python 3.11 开发，依赖 PySide6、Pydantic、Requests、platformdirs、psutil 和 pypinyin。创建开发环境：

```powershell
uv venv --python 3.11 .venv
.\.venv\Scripts\python.exe -m pip install --no-build-isolation -e ".[dev]"
.\.venv\Scripts\python.exe -m poptools
```

运行测试与静态检查：

```powershell
.\.venv\Scripts\python.exe -m pytest
.\.venv\Scripts\ruff.exe check src tests
```

视频性能可用同一段素材在目标电脑上复测（`--ui` 会打开实际播放器窗口并模拟时间轴拖动）：

```powershell
.\.venv\Scripts\python.exe scripts/benchmark_video_preview.py "sample.mp4" --ui --output build/video-benchmark.json
```

报告分别记录源视频解码、预览缓存读取、界面拖动及松手恢复原生画面的耗时。界面测量在目标图像就绪后再等待两次窗口绘制提交，作为保守延迟上界，不代表屏幕像素实际发光时间。拖动部分使用准备完成的预览，首次生成耗时另行记录；复用缓存时，该项仅为打开已有缓存的耗时。大文件或长片只准备抽样位置附近的预览，无需生成整部电影；报告中的 `proxy_mode` 区分整段和按需缓存。保留原文件以便设备间比较。可加 `--cpu-count 1` 限制进程 CPU，但这不能替代不同设备上的实测。脚本只写指定报告和缓存目录，不读取应用的播放列表。

连续交互压力测试使用独立播放列表和缓存，默认以约 60 次/秒发送鼠标移动，交替执行全片随机拖动、局部放大拖动，以及切换文件、画质、播放状态、列表与窗口大小：

```powershell
.\.venv\Scripts\python.exe scripts/stress_video_preview.py "movie.mkv" --alternate "short.mp4" --seconds 60 --output build/video-stress.json
```

可加 `--cpu-count 2` 测试 CPU 受限情况。报告包含主画面数据更新间隔、界面心跳间隔、进程内存、操作耗时和退出后残留工作线程；校验最终定位、拖动时弹窗隐藏、播放器布局稳定与 QML 错误。脚本默认使用 Qt `basic` 渲染循环，数据反映解码与界面事件处理，不代表屏幕实际呈现帧率。播放测试音量为 10%，素材和实际应用的播放列表不作修改。

完整主窗口的长时间混合压力测试按实际墙钟时间运行，默认持续一小时：

```powershell
.\.venv\Scripts\python.exe scripts/stress_application.py --seconds 3600 --tools 500 --video "movie.mkv" --alternate "short.mp4" --output build/app-soak.json
```

每分钟循环切换脚本、设置、手册、终端、调色盘、Android 空状态、视频和更新弹窗，执行无害的本地 Python 脚本，反复创建和关闭真实终端会话，并测试视频拖动、播放列表、文件切换、画质、倍速与窗口缩放。测试配置和脚本保存在报告旁的 `*-session` 新目录；视频只读，播放音量为零。输出包含逐分钟内存、线程、句柄和子进程数量，界面心跳、各操作耗时、截图、错误及退出后的残留子进程。加 `--trace-actions` 可记录每一步完成后的资源数据。再次运行需更换报告名，以免复用旧测试数据。

该脚本默认采用离屏软件渲染，能够检查界面布局和事件响应，不能测量桌面合成器帧率。真实 Android 操作、Jira/飞书网络请求、插件下载安装和应用升级需在专用设备或测试环境中另测；现有 pytest 覆盖其本地逻辑和模拟失败路径。Windows 原生窗口、桌面输入及 GPU 效果测试应在可交互桌面运行，不能以离屏结果替代。

卡牌原生窗口回归可单独运行（仅使用临时数据和合成脚本，不执行脚本）：

```powershell
.\.venv\Scripts\python.exe tests/card_motion_probe.py build/card-motion-stress.json decade
```

末尾主题也可指定 `light` 或 `dark`。测试由独立父进程监护，超过 90 秒会结束本次测试进程树，避免无响应窗口留在桌面。帧信号必须排队回到界面线程采样，不能从渲染线程同步调用 Python；否则模拟点击等待渲染时可能与 Python 锁互相等待。报告中的帧间隔是界面线程收到通知的间隔，并非 GPU 呈现时间。

Windows 构建：

需要安装 Visual Studio / Build Tools 的“使用 C++ 的桌面开发”工作负载（含 MSVC 和 Windows SDK）。脚本会自动识别安装位置（包括 Insiders / 预览版），加载 x64 编译环境，使用 NMake 构建，无需手动打开开发者终端。CMake 已包含在开发依赖中；直接运行原生构建脚本时，缺少的 CMake 也会自动安装到项目 `.venv`。未设置 `QT_ROOT_DIR` / `Qt6_DIR` 且找不到 qmake 时，脚本会自动下载 Qt C++ SDK 到 `build/qt-sdk`，首次构建需要联网。

```powershell
.\packaging\build.ps1
```

默认打包只运行功能检查，排除标记为 `gui`（窗口、布局、画面与动效）和 `hardware`（真实音频设备）的 pytest 测试，避免桌面焦点、系统动效或声卡启动时序阻断打包。视频解码、数据处理及模拟设备测试仍会运行。

```powershell
# 按需运行完整测试后打包（需要可交互桌面及可用音频设备）
.\packaging\build.ps1 -FullTests
# 跳过 Python 测试，直接打包（原生组件仍编译并运行 CTest）
.\packaging\build.ps1 -SkipTests
# 只执行默认打包使用的功能检查
.\.venv\Scripts\python.exe -m pytest -m "not gui and not hardware"
```

直接运行 `python -m pytest` 仍执行完整测试；新增界面或真实设备测试时，应添加对应的 `@pytest.mark.gui` 或 `@pytest.mark.hardware` 标记。

macOS 构建：

```bash
uv venv --python 3.11 .venv
./packaging/build.sh
```

macOS 同样默认排除界面与真实设备测试，使用 `--full-tests` 运行完整测试，或使用 `--skip-tests` 跳过 Python 测试。

版本以 `pyproject.toml` 为来源。GitHub Release 使用 `vYYYY-MM-DD_x.x.x` 标签，并构建 Windows x64、macOS arm64 和 macOS x64 资产。
