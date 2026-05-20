# -*- coding: utf-8 -*-
import json

with open("config/config.jsonc", "r", encoding="utf-8") as f:
    data = json.load(f)

lines = []
lines.append("{")

# header
lines.append("  // ============================================================")
lines.append("  // 大麦抢票 - 全局配置文件")
lines.append("  // 支持 .jsonc 格式（可包含注释），亦可用纯 .json")
lines.append("  // 本文件为完整参考示例，所有字段均带说明")
lines.append("  // ============================================================")
lines.append("")

# App mode
lines.append("  // ---------- App 模式字段 ----------")
lines.append("")
lines.append(f'  "server_url": {json.dumps(data["server_url"])},\t\t\t// Appium 服务地址')
lines.append(f'  "device_caps": {{                                // 设备能力（Appium 必填）')
lines.append(f'    "deviceName": {json.dumps(data["device_caps"]["deviceName"])},\t\t\t//   设备名称（可自定义）')
lines.append(f'    "udid": {json.dumps(data["device_caps"]["udid"])},\t\t\t\t//   设备 UDID（通过 adb devices 获取）')
lines.append(f'    "automationName": {json.dumps(data["device_caps"]["automationName"])}\t\t//   自动化引擎（Android 建议 UiAutomator2）')
lines.append(f'  }},')
lines.append(f'  "wait_timeout": {data["wait_timeout"]},\t\t\t\t// 元素等待超时（秒），建议 3-10')
lines.append(f'  "retry_delay": {data["retry_delay"]},\t\t\t\t// 重试延迟（秒），建议 1-3')
lines.append(f'  "max_retries": {data["max_retries"]},\t\t\t\t// 最大重试次数')
lines.append(f'  "warmup_sec": {data["warmup_sec"]},\t\t\t\t// 预热等待（秒），开售前提前进入详情页')
lines.append("")
lines.append("  // ---------- Web 模式字段 ----------")
lines.append("")
lines.append(f'  "target_url": {json.dumps(data["target_url"])},\t\t\t\t// 目标演出链接（大麦网演出详情页 URL）')
lines.append(f'  "price": {json.dumps(data["price"])},\t\t\t\t\t// 票价文本，用于匹配票价（如 "380元"）')
lines.append("")
lines.append("  // ---------- 通用字段（App & Web 共用） ----------")
lines.append("")
lines.append(f'  "keyword": {json.dumps(data["keyword"])},\t\t\t\t// 演出搜索关键词')
lines.append(f'  "city": {json.dumps(data["city"])},\t\t\t\t\t// 演出城市')
lines.append(f'  "date": {json.dumps(data["date"])},\t\t\t\t\t// 演出日期，格式 "YYYY-MM-DD HH:MM:SS"')
lines.append(f'  "session_index": {data["session_index"]},\t\t\t\t// 场次索引（从 0 开始）')
lines.append(f'  "session_text": {json.dumps(data["session_text"])},\t\t\t// 场次文本，用于匹配（如 "2025-12-28 19:30"）')
lines.append(f'  "price_index": {data["price_index"]},\t\t\t\t// 票价索引（从 0 开始，优于 price 文本匹配）')
lines.append(f'  "ticket_quantity": {data["ticket_quantity"]},\t\t\t\t// 购票张数')
lines.append(f'  "if_commit_order": {"true" if data["if_commit_order"] else "false"},\t\t\t// true=自动提交订单，false=仅下单不提交')
lines.append("")
lines.append("  // ---------- 定时抢票 ----------")
lines.append("")
lines.append(f'  "schedule_time": {json.dumps(data["schedule_time"])},\t\t\t// 定时抢票时间，格式 "YYYY-MM-DD HH:MM:SS"')
lines.append("")
lines.append("  // ---------- 观演人（App 模式） ----------")
lines.append("")
lines.append(f'  "users": {json.dumps(data["users"])}\t\t\t\t\t// 观演人列表，留空默认选择全部')

lines.append("}")

with open("config/config.jsonc", "w", encoding="utf-8") as f:
    f.write("\n".join(lines))

print("Generated config/config.jsonc with comments")
