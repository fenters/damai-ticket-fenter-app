# App 模式零基础上手指南

> 这份文档面向**完全没有自动化经验**的小白用户。照着一步一步做，就能在手机上跑起来大麦 App 的自动抢票流程。如遇到任何与文档不符的现象，优先按照“常见问题 & 故障排查”部分一步步检查。

---

## 1. 准备工作一览

| 项目 | 目的 | 推荐版本 | 下载/查看方式 |
| --- | --- | --- | --- |
| Windows 10/11 电脑 | 运行脚本与 Appium | \- | 已具备即可 |
| Android 真机或模拟器 | 执行大麦 App | Android 8.0+ | 真机需开启开发者模式；或使用 Android Studio 模拟器 |
| Python | 运行项目脚本 | 3.9 ~ 3.13 | [python.org](https://www.python.org/downloads/) |
| Git（可选） | 拉取仓库 | 最新稳定版 | [git-scm.com](https://git-scm.com/) |
| Node.js | Appium 依赖 | 18+ LTS | [nodejs.org](https://nodejs.org/) |
| Appium Server | 驱动 App | 2.x | `npm install -g appium` |
| Android Platform Tools | 提供 `adb` | 最新版 | [Google Platform Tools](https://developer.android.com/tools/releases/platform-tools) |

> **提示**：若你不熟悉上述软件的安装，可以先记录软件名称，逐个搜索“软件名 + 安装教程”后照做即可。按照顺序完成就好，不必一次性全部部署。

---

## 2. 一次性环境安装步骤

1. **安装 Python**
    - 下载官方安装包时勾选“Add Python to PATH”选项。
    - 安装完成后，在 PowerShell 输入：

       ```powershell
       python --version
       ```

    - 若看到 `Python 3.x.x` 即表示安装成功。

2. **安装 Node.js**
    - 选择 LTS 版本安装（包含 npm）。安装完成后在 PowerShell 输入：

       ```powershell
       node --version
       npm --version
       ```

3. **安装 Appium Server 与 Inspector（可选）**
   
    ```powershell
    npm install -g appium
    npm install -g appium-doctor
    ```

    - Appium 服务启动：

       ```powershell
       appium
       ```

    - 默认监听 `http://127.0.0.1:4723/`，窗口保持打开状态即可。
    - 使用 appium-doctor 检查依赖：

       ```powershell
       appium-doctor --android
       ```

4. **安装 Android Platform Tools**
   - 下载压缩包后解压，将 `platform-tools` 文件夹放在常用路径（如 `C:\Android\platform-tools`）。
   - 将路径加入系统环境变量 `PATH`。
    - 在 PowerShell 输入：

       ```powershell
       adb version
       ```

### 永久生效的环境变量（补充）

如果你希望系统级别永久生效（便于 Appium 作为服务或其他程序读取），请按以下说明设置环境变量：

1. 使用“系统属性” → “高级” → “环境变量”，在“系统变量”中新增：

   - `ANDROID_SDK_ROOT` = `C:\Android`（或你的 SDK 根目录）
   - `ANDROID_HOME` = `C:\Android`（建议同时设置以兼容旧工具）

2. 在系统变量中的 `Path` 添加：`C:\Android\platform-tools`。

3. 保存并退出后，请重启电脑以确保所有系统服务和桌面应用读取到新的环境变量。

> 注意：将 `platform-tools` 路径加入系统 `PATH` 后，已有进程（包括作为服务运行的 Appium）不会自动读取到更新，重启后这些进程才会看到新变量。

亦可使用命令行为当前用户写入（需重新打开终端或重启生效）：

```powershell
setx ANDROID_SDK_ROOT "C:\Android"
setx ANDROID_HOME "C:\Android"
```

5. **下载/克隆项目**
    - 直接下载 ZIP 并解压，或使用 Git：

       ```powershell
       git clone https://github.com/fenters/damai-ticket-fenter-app.git
       ```

6. **安装 Python 依赖**
    - 在项目根目录运行以下命令：

       ```powershell
       cd damai-ticket-assistant
       python -m pip install -r requirements.txt
       ```

---

## 3. 连接手机（或模拟器）

1. **真机准备**
   - 在手机设置中依次开启：开发者模式 → USB 调试 → 允许通过 USB 安装 App。
   - 使用原装数据线连接电脑，若弹出授权提示，请选择“始终允许”。
2. **模拟器准备**
   - Android Studio 创建虚拟设备并启动。
3. **验证连接**
   在 PowerShell 输入：

   ```powershell
   adb devices -l
   ```

      看到类似 `device` 状态且带有 `model` 信息的行，即连接成功。

---

## 4. 启动 Appium 服务

保持如下窗口开启（随项目启动一直存在）：

```powershell
appium
```

若想指定监听端口：

```powershell
appium --address 127.0.0.1 --port 4723
```

> 小贴士：App 模式默认使用 `http://127.0.0.1:4723/wd/hub`。只要 Appium 服务启动并保持运行即可。

---

## 5. 准备 config.jsonc（最简模板）

项目目录自带 `damai_appium/config.jsonc`，推荐复制一份作为备份，再按以下字段修改：

```jsonc
{
  "server_url": "http://127.0.0.1:4723/wd/hub",
  "keyword": "演出关键词，可为空",
  "users": ["观演人姓名"] ,
  "city": "北京",
  "date": "2025-10-01",
  "price": "看台",
  "price_index": 0,
  "if_commit_order": true,
  "device_caps": {
    "udid": "adb devices 中看到的序列号",
    "deviceName": "自定义的设备昵称",
    "platformVersion": "安卓版本号，例如 13"
  }
}
```

### 可选：多设备顺序执行（规划中）

~~该功能仍在规划中，原多设备顺序执行配置示例暂不适用，敬请期待后续更新。~~

---

## 6. 图形界面 App 模式操作指南

1. **启动 GUI**

   ```powershell
   python start_gui.pyw
   ```
   
2. **切换至“App 模式”标签页**
   - 首次进入请依次点击“环境检测”“刷新设备”，确认依赖与设备状态均为绿色。
3. **加载配置**
   - 点击“选择配置文件”，浏览到前文编辑好的 `config.jsonc`。
   - 也可以直接在表单中手动修改 server_url、设备信息、观演人等字段。
4. **检查运行日志面板**
   - 如有字段缺失，界面底部会提示“配置校验失败”，同时展示详细字段名。
5. **点击“开始抢票”**
   - 右侧日志将实时输出执行阶段（RunnerPhase），如 `CONNECTING`、`SELECTING_PRICE` 等。
   - 若需紧急停止，点击“停止”按钮即可。
6. **查看运行统计**
   - 抢票结束后会显示尝试次数、耗时、最终阶段等信息。
   - 如需导出日志，点击“导出日志”按钮获得 JSON 文件。

---

## 7. 命令行快速启动（可与 GUI 并行）

### 方式一：直接运行模块

```powershell
python -m damai_appium.damai_app_v2 --config damai_appium/config.jsonc --retries 3 --export-report run-report.json
```

参数说明：

- `--config`：指定配置文件；不填写时默认读取 `damai_appium/` 下的 `config.jsonc`。
- `--retries`：最多尝试次数（含首次执行）。
- `--export-report`：导出运行日志与统计的 JSON 文件。

### 方式二：使用 PowerShell 快速脚本

```powershell
pwsh ./scripts/app_mode_quickstart.ps1 -ConfigPath .\damai_appium\config.jsonc -Retries 3
```

该脚本会自动定位 Python，可直接在 Windows 中双击或在 PowerShell 执行。

#### 8. 即将上线的 CLI 示例

- 后续将新增更完整的命令行参数讲解与多场景脚本模板，确保与网页模式指南保持一致。
- 计划补充跨平台 Shell 示例、定时任务模板与环境检测脚本，便于批量执行或持续守候。
- 欢迎在 Issue 中提交希望覆盖的脚本场景，我们会在更新时优先考虑。

---

## 9. 常见问题 & 故障排查

| 现象 | 可能原因 | 解决方案 |
| --- | --- | --- |
| `server_url 不能为空` 提示 | 配置文件未填写或 Appium 未启动 | 确认 `appium` 服务窗口仍在运行，并确保 `server_url` 字段以 `http://` 开头 |
| `adb devices` 没有设备 | 数据线/驱动问题 | 换线、更新 USB 驱动、重新授权 USB 调试 |
| 日志停在 `CONNECTING` 阶段 | Appium 无法连接到设备 | 检查 `device_caps.udid` 是否与 `adb devices` 输出一致 |
| 日志提示 `NO SUCH ELEMENT` | App 页面结构发生变化 | 尝试提高 `wait_timeout`，或手动检查当前页面元素是否与大麦 App 更新保持一致 |
| CLI 直接退出，返回码 2 | 配置校验失败 | 终端会列出具体错误字段；根据提示修改配置后重试 |
| 需要多台设备同时执行 | 当前版本仅支持**顺序执行**多个会话 | 根据配置示例添加 `devices` 数组，每台设备会依次运行 |

---

## 10. 提升成功率的小技巧

- 提前登录大麦 App，并在“全部订单”里确认身份信息无误。
- 使用有线网络或稳定的 Wi-Fi，避免抢票过程掉线。
- 提前打开 App 并进入目标演出页面，可缩短自动化流程的加载时间。
- 对同一场次，可设置多台设备顺序尝试，以提高命中率。

---

## 11. 你已经完成了什么

- 搭建完整的 Appium + Python 抢票环境。
- 能够在 GUI 中加载配置、检测依赖、查看日志与统计。
- 可以使用命令行或脚本批量执行，并获得详细的运行报告。

如需扩展更多高级功能（如定时任务、远程调度、自定义脚本），欢迎继续关注仓库后续更新或参与贡献。

祝你抢票顺利！🎫

## 12. 定时抢票（App 模式）

> 本节介绍如何在 App 模式下按指定时间自动开抢，基于已提供的 CLI 入口与新增参数，无需修改 GUI。

### 功能概述

- 在命令行入口于到点时自动开始执行抢票流程，支持到点前预热检查（Appium /status 与 adb 设备状态）。
- 实现位置：入口逻辑与参数解析在 [damai_appium/damai_app_v2.py](damai_appium/damai_app_v2.py:133)，新增参数解析见 [_parse_args()](damai_appium/damai_app_v2.py:56)。

### 参数说明

- `--start-at`：定时开抢时间
  - 支持 ISO8601：如 `2025-10-01T20:00:00+08:00`、`2025-10-01T12:00:00Z`
  - 支持本地时区格式：`'YYYY-MM-DD HH:MM:SS'`（按本地时区解析）
- `--warmup-sec`：到点前预热检查窗口（秒）
  - 在到点前进入该窗口时，会快速检查 Appium `/status` 与 `adb devices -l` 是否为 `device` 状态
- 其它常用参数
  - `--config`：配置文件路径（默认读取 `damai_appium/config.jsonc`）
  - `--retries`：最大尝试次数（包含首次执行）
  - `--export-report`：导出本次运行的 JSON 报告，方便复盘

### 使用示例（命令行）

- 本地时区格式（香港/UTC+8）
  ```powershell
  python -m damai_appium.damai_app_v2 `
    --config damai_appium/config.jsonc `
    --retries 6 `
    --start-at "2025-10-01 20:00:00" `
    --warmup-sec 120 `
    --export-report run-report.json
  ```
- ISO8601（显式时区）
  ```powershell
  python -m damai_appium.damai_app_v2 `
    --config damai_appium/config.jsonc `
    --retries 6 `
    --start-at 2025-10-01T20:00:00+08:00 `
    --warmup-sec 120 `
    --export-report run-report.json
  ```

### 使用示例（PowerShell 快速脚本）

- 脚本位置与扩展参数：支持 `-StartAt` 与 `-WarmupSec` 封装调用 [scripts/app_mode_quickstart.ps1](scripts/app_mode_quickstart.ps1:1)
  ```powershell
  pwsh ./scripts/app_mode_quickstart.ps1 `
    -ConfigPath .\damai_appium\config.jsonc `
    -Retries 6 `
    -StartAt "2025-10-01 20:00:00" `
    -WarmupSec 120
  ```

### Windows 任务计划程序（Task Scheduler）示例步骤

1. 打开“任务计划程序” → “创建任务”。
2. 触发器：选择具体日期与时间（建议提前确保系统时间同步）。
3. 操作：
   - Program/script: `python`
   - Arguments: `-m damai_appium.damai_app_v2 --config "C:\path\damai_appium\config.jsonc" --retries 6 --start-at "2025-10-01 20:00:00" --warmup-sec 120 --export-report "C:\logs\run-report.json"`
   - Start in: 项目根目录（例如 `C:\path\to\damai-ticket-assistant`）
   - 或使用 PowerShell 脚本：Program/script `pwsh`，Arguments `-File "C:\path\to\scripts\app_mode_quickstart.ps1" -ConfigPath "C:\path\damai_appium\config.jsonc" -Retries 6 -StartAt "2025-10-01 20:00:00" -WarmupSec 120`
4. 条件与设置：勾选“允许按需运行”与“即使用户未登录也运行”（按需选择）；建议开启“以最高权限运行”（避免环境权限问题）。

### 参数搭配建议

- 开售冲刺：`--retries 5~6`、`--warmup-sec 60~180`；配置中 `wait_timeout≈1.4~1.6`、`retry_delay≈1.0~1.2`、`price_index` 精准。
- 守候回流：`--retries 8~10`、`--warmup-sec 120~300`；配置中 `wait_timeout≈1.8~2.2`、`retry_delay≈1.5`。

### 前置条件与健康检查

- Appium Server 建议提前常驻（如 `appium --address 127.0.0.1 --port 4723 --relaxed-security`），避免到点启动引入抖动（说明见 [damai_appium/app.md](damai_appium/app.md:4)）。
- `adb devices -l` 输出须为 `device` 状态（解析能力在 [damai_appium/config.py](damai_appium/config.py:361)）；设备需开启开发者模式、USB 调试“始终允许”。

### 报告与复盘

- 使用 `--export-report` 导出 JSON（包含最终阶段、尝试次数、失败码与耗时），导出逻辑见 [_export_reports()](damai_appium/damai_app_v2.py:104) 与运行指标来源 [DamaiAppTicketRunner.run()](damai_appium/runner.py:199)。
- 根据报告中的 `final_phase` 与 `failure_code` 调参（例如增大 `--retries`、微调 `wait_timeout`/`retry_delay`、修正 `price_index`），提升命中率与稳定性。

## ⏰ 定时抢票（App 模式）

- 功能概述：在 CLI 入口到达指定时间点时自动开始 App 模式抢票流程，支持到点前预热检查（Appium /status 与 adb 设备状态）。
- 实现位置与入口参考：[main()](damai_appium/damai_app_v2.py:133)、参数解析 [_parse_args()](damai_appium/damai_app_v2.py:56)

参数对照表
| 序号 | 参数名 | 说明 | 示例值 | 默认值 |
|---|---|---|---|---|
| 1 | --start-at | 定时开抢时间，支持 ISO8601（含时区）或本地时区的“YYYY-MM-DD HH:MM:SS” | 2025-10-01T20:00:00+08:00；"2025-10-01 20:00:00" | 未设置（立即执行） |
| 2 | --warmup-sec | 到点前预热检查窗口（秒），在窗口内检查 Appium 服务与 adb 设备状态 | 120 | 0（不启用） |
| 3 | --config | 配置文件路径 | damai_appium/config.jsonc | 默认读取 damai_appium/config.jsonc |
| 4 | --retries | 最大尝试次数（包含首次） | 6 | 3 |
| 5 | --export-report | 导出运行报告到 JSON 文件 | run-report.json | 未设置（不导出） |

使用示例（命令行）
- 本地时区格式（香港/UTC+8）
  - python -m damai_appium.damai_app_v2 --config damai_appium/config.jsonc --retries 6 --start-at "2025-10-01 20:00:00" --warmup-sec 120 --export-report run-report.json
- ISO8601（显式时区）
  - python -m damai_appium.damai_app_v2 --config damai_appium/config.jsonc --retries 6 --start-at 2025-10-01T20:00:00+08:00 --warmup-sec 120 --export-report run-report.json

使用示例（PowerShell 快速脚本）
- 已支持 `-StartAt` 与 `-WarmupSec` 参数，用于封装命令行调用：
  - pwsh ./scripts/app_mode_quickstart.ps1 -ConfigPath .\damai_appium\config.jsonc -Retries 6 -StartAt "2025-10-01 20:00:00" -WarmupSec 120
- 脚本位置：[scripts/app_mode_quickstart.ps1](scripts/app_mode_quickstart.ps1:1)

落地建议（Windows 任务计划程序）
- Program/script: python
- Arguments: -m damai_appium.damai_app_v2 --config "C:\path\damai_appium\config.jsonc" --retries 6 --start-at "2025-10-01 20:00:00" --warmup-sec 120 --export-report "C:\logs\run-report.json"
- Start in: 项目根目录（例如 C:\path\to\damai-ticket-assistant）
- 或使用 PowerShell 脚本：Program/script: pwsh；Arguments: -File "C:\path\to\scripts\app_mode_quickstart.ps1" -ConfigPath "C:\path\damai_appium\config.jsonc" -Retries 6 -StartAt "2025-10-01 20:00:00" -WarmupSec 120

参数搭配建议
- 开售冲刺：--retries 5~6；--warmup-sec 60~180；配置中 wait_timeout≈1.4~1.6、retry_delay≈1.0~1.2、price_index 精准。
- 守候回流：--retries 8~10；--warmup-sec 120~300；配置中 wait_timeout≈1.8~2.2、retry_delay≈1.5。

前置条件与健康检查
- Appium Server 建议提前常驻（如 appium --address 127.0.0.1 --port 4723 --relaxed-security），避免到点启动引入抖动，说明详见 [安卓端V2版本介绍](damai_appium/app.md:4)。
- adb devices -l 输出须为 device 状态（解析能力在 [parse_adb_devices()](damai_appium/config.py:361)），设备需开启开发者模式与 USB 调试“始终允许”。

报告与复盘
- 使用 --export-report 导出 JSON（包含最终阶段、尝试次数、失败码与耗时），导出逻辑见 [_export_reports()](damai_appium/damai_app_v2.py:104)，运行指标来源 [DamaiAppTicketRunner.run()](damai_appium/runner.py:199)。
- 根据报告中的 final_phase 与 failure_code 调参（增大 --retries、微调 wait_timeout/retry_delay、修正 price_index），提升命中率与稳定性。
