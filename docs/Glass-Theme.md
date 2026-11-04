# Glass 系统背景材质

在“设置 → 外观与交互”中选择浅色、深色或跟随系统，再开启 **Glass 液态玻璃**。
材质与主题模式分别保存。Decade / ZIO 沿用各自外观。

## 实际实现

背景模糊交给 Windows 桌面窗口管理器 DWM：通过公开的
`DwmSetWindowAttribute(DWMWA_SYSTEMBACKDROP_TYPE, DWMSBT_TRANSIENTWINDOW)`
启用 **Desktop Acrylic**。它处理真实桌面与后方窗口，采用屏幕全局坐标；
窗口移动只是改变覆盖区域，桌面的蓝色色块不会被贴图带着移动。
Mica 主要来自壁纸，因此没有用它代替后方窗口的模糊。

应用不再启动 Windows Graphics Capture，不枚举、捕获、合成或上传后方窗口图像，
也没有用于背景刷新的轮询定时器、图像提供器或位置同步回调。
背景内容变化和窗口移动由系统合成器处理，不需要应用重绘背景帧。
这避免了原实现的 CPU 帧复制、纹理上传以及坐标同步滞后问题。

Qt 在创建窗口前分配 alpha 缓冲区，并启用 Windows QPA 的 D3D 无重定向表面路径
（`QT_QPA_DISABLE_REDIRECTION_SURFACE=1`），让 DirectComposition 透明表面显示 DWM 材质，
避免不透明 HWND 重定向位图挡住 Acrylic。保留 Win32 缩放、系统菜单及最小化/最大化样式，
移除 `WS_CAPTION`，避免最大化时 DWM 再绘制一套按钮；继续支持原生移动、缩放和 Snap。
主题/透明表面切换时进行一次设置同步，不按帧重新设置系统材质。
顶栏、侧栏共享同一个系统背景，不添加独立底板或边框。

Qt 6.11 的上述 QPA 环境开关实际作用于所有顶层原生窗口，包括使用普通位图绘制的
托盘菜单。托盘主菜单及两个子菜单会在临时排除此开关的情况下预先创建原生窗口。
每次弹出时也检查窗口；如果 Qt 因屏幕、样式变化重建了不带位图的 HWND，则在显示前重新创建，
显示准备完成后立即恢复开关。菜单淡入/滚动动画关闭，避免额外的动画窗口再次继承该开关；
菜单绘制仍保持 Qt 原有样式。仅关闭 DWM 材质不足以
恢复该缓冲，会出现只有边框、没有菜单文字的空弹窗。

## 控件的玻璃效果与边界

控件使用透明着色层绘制圆角、边缘高光和指针响应；`nativeglass.frag` 没有纹理采样器，
不会为了控件效果重新抓取桌面。终端只绘制文字、光标、选区和显式 ANSI 色块，
默认单元格与周围留白共享一块玻璃底板。

**Desktop Acrylic 是系统磨砂材质，不是 iOS 液态玻璃的桌面折射实现。**
本实现保留控件的玻璃高光与交互，不声称能通过 DWM 背景接口折射外部窗口内容。
社区液态玻璃材质仍可用于显式提供的应用内部纹理，未用于桌面取样。

Glass 下主界面的菜单、下拉框、tooltip、对话框及视频浮层统一采样主页面内容，
在 GPU 上进行高斯模糊，再叠加玻璃折射、高光和主题底色。页面与 Overlay 弹窗分层，
采样源排除弹窗自身，避免递归反馈。此路径不抓取桌面，也不对弹窗开启额外的整窗 DWM 材质。
`pagePopupOpacity`、`pageTooltipOpacity` 和 `popupBlurRadius` 分别控制底色强度及页面模糊半径；
浅色弹窗底色强度默认 0.32，使用 `lightPagePopupTint` 冷灰着色，透明页面区域用
`lightPageBackdropColor` 补底，避免页面本身偏白时弹窗仍大面积发白。
深色弹窗使用独立的 `darkPagePopupOpacity`（默认 0.72）维持可读性。
页面模糊半径默认 64，只保留大致色彩，隐藏文字和细节；玻璃材质默认关闭鼠标驱动的折射与高光移动。
tooltip 保留更强底色保障可读性。软件渲染使用主题底色回退。
悬浮卡片等没有独立页面纹理的宿主中，弹出菜单使用 97% 不透明度的主题底色，防止底层参数和输出文字透入。
新建/编辑、删除、运行确认弹窗在空闲帧异步预加载，关闭后保留实例；玻璃着色器用微小表面预热，
减少首次打开时集中创建控件及初始化图形管线的开销。

常规执行卡片使用独立的全客户区原生窗框，保留 Windows 合成及圆角裁剪协议，
不使用 Qt 的分层无边框窗口样式。Glass 下由 DWM 模糊卡片后方的桌面与其他窗口，
卡片的标题与详情共用统一材质，参数、按钮、控制台叠加玻璃高光和着色层。
材质从窗口显示起持续存在，不在入场动画结束后切换，不产生外围灰色矩形。
机械主题仍保留原有透明动画画布和窗口形状；不支持原生材质的环境使用统一实色回退。

悬浮抽屉的画布包含侧边入口下方的不规则透明区域，目前仍只在可见圆角表面绘制
统一底色和玻璃高光，暂不提供桌面模糊。托盘菜单始终保持常规位图绘制。
没有页面采样源的窗口中，tooltip 继续使用 `material.tooltipOpacity` 的 97% 不透明底色下限。

## 平台与系统策略

系统 Acrylic 需要 Windows 11 22H2（build 22621）或更新版本；Qt 使用 Direct3D 图形后端。
不支持的系统或软件/OpenGL 渲染使用实色回退，并在设置页显示原因。
系统关闭透明效果、省电策略或窗口非活动状态也可能让 Acrylic 回退为实色；不擅自更改系统设置。
模糊半径由系统材质管理，公开的 DWM 背景接口不提供半径设置。

浅/深配色及控件着色强度在 `src/poptools/ui/qml/theme/configs/glass.json` 中。
`surfaceOpacity`、`lightSurfaceOpacity`、`darkTintStrength`、`lightTintStrength` 控制应用自身的控件着色，
不代表系统背景模糊半径。

## 构建与验证

修改着色器后执行：

```console
python scripts/build-glass-shaders.py
```

QSB 随源码包和 PyInstaller 分发。已移除 windows-capture、OpenCV、NumPy 依赖和捕获打包项。

```console
python scripts/verify-desktop-glass.py
python scripts/verify-desktop-glass.py --card
python scripts/verify-desktop-glass.py --application --card --light
python scripts/verify-desktop-glass.py --application --light --settings
python scripts/verify-desktop-glass.py --application --terminal
```

验证工具创建独立测试背景进程，前景窗口带不透明识别标记，防止误把裸露的背景当成材质结果。
它使用测试期间的屏幕读回来检查 DWM 的最终合成，截图不参与应用的背景渲染。
后方窗口红/绿切换时检查前景材质变化，并统计前景窗口重绘次数；
上下、左右移动后，验证固定蓝色色块仍位于同一全局坐标。
完整应用检查必须使用合成后的屏幕画面，不能以 `QQuickWindow.grabWindow()` 代替 DWM 输出。

## 官方依据与社区来源

- [微软：DWM_SYSTEMBACKDROP_TYPE](https://learn.microsoft.com/en-us/windows/win32/api/dwmapi/ne-dwmapi-dwm_systembackdrop_type)
- [微软：系统背景材质与控制器](https://learn.microsoft.com/en-us/windows/apps/develop/ui/system-backdrops)
- [微软：Acrylic 的系统回退策略](https://learn.microsoft.com/en-us/windows/apps/design/style/acrylic)
- [Qt：Windows QPA 的 D3D 无重定向表面路径](https://github.com/qt/qtbase/blob/6.11/src/plugins/platforms/windows/qwindowswindow.cpp)
- [社区液态玻璃 Qt port](https://github.com/shayann07/liquidglass/tree/main/ports/qt)，固定版本 `2e4849fb75ab3299978825985193cf41dba4a061`，Apache-2.0。
  LICENSE / NOTICE 与源文件位于 `src/poptools/ui/qml/components/glass/LiquidGlass/`。
