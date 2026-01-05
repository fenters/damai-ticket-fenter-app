# Windows 安装依赖指南

> 建议使用 PowerShell 7+ 或 Windows Terminal 执行以下命令。

## 1. 准备 Python 环境

1. 确保已安装 Python 3.8 及以上版本，可以在终端执行 `python --version` 检查。
2. 勾选 “Add Python to PATH”，或手动将 Python 安装目录加入系统 PATH。

## 2. 安装项目依赖

在项目根目录执行以下命令：

```powershell
cd "C:\path\to\damai-ticket-assistant"
pip install --upgrade pip
pip install -r requirements.txt
```

> 如使用 Poetry，可运行 `poetry install` 自动创建虚拟环境。

## 3. 可选依赖

- **App 模式**：需要 Node.js、Appium CLI 以及 adb，详见 `docs/guides/APP_MODE_README.md`
- **开发工具**：若使用 Poetry，可执行 `poetry install --with dev` 安装测试与 lint 工具（可选）。

## 4. 常见问题

- 如果提示没有权限，请在 PowerShell 中使用管理员身份运行。
- 如果 `pip` 执行失败，可尝试使用 `python -m pip install ...`。
- 如果网络受限，可配置国内镜像源，如 `pip install -i https://pypi.tuna.tsinghua.edu.cn/simple -r requirements.txt`。
