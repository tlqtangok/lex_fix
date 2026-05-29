# Wubi .lex 词库编辑器

> 📖 [English Version](README_EN.md)

微软五笔输入法 `.lex` 词库查看 / 搜索 / 编辑工具，同时支持图形界面与命令行两种使用方式。  
特别支持 **`now`（当前时间）** 和 **`date`（当前日期）** 快捷词条的自动刷新。

---

## 功能特性

- 支持两种 `.lex` 格式：`mschxudp`（用户词库 user.lex）和 `imscwubi`（主词库 ChsWubiNew.lex）
- 图形界面：查看、搜索、添加、编辑、删除词条
- 命令行：批量编辑、删除、添加词条
- 打开最近文件（自动记忆上次打开的词库）
- 启动时自动加载上次打开的文件
- Perl 脚本自动刷新时间/日期词条

---

## 快速开始

### 方式一：直接运行 exe（推荐，无需安装 Python）

前往 [Releases 页面](https://github.com/tlqtangok/lex_fix/releases) 下载最新版 `lex_editor.exe`，双击运行即可。

### 方式二：运行 Python 脚本

```bash
# 需要 Python 3.8+，无第三方依赖
python lex_editor.py
```

---

## 图形界面使用说明

1. **打开词库**：菜单 `File → Open…`，选择 `.lex` 文件；或使用 `File → Open Recent` 快速打开历史记录
2. **搜索词条**：工具栏搜索框输入关键词，支持按 `全部 / 词语 / 编码` 三种模式过滤
3. **添加词条**：菜单 `Edit → Add Entry`（或 `Ctrl+N`），填写编码和词语后保存
4. **编辑词条**：双击列表中的词条，或菜单 `Edit → Edit Entry`（或 `F2`）
5. **删除词条**：选中词条后按 `Del` 键，或菜单 `Edit → Delete Entry`
6. **保存**：`Ctrl+S` 直接保存；`File → Save As…` 另存为新文件
7. 标题栏带 `*` 表示有未保存修改

---

## 命令行使用说明

```
python lex_editor.py --input <词库文件> [--output <输出文件>] --op <操作> [选项]
```

### 查看帮助

```bash
python lex_editor.py --help
```

### 搜索词条

```bash
# 按编码搜索
python lex_editor.py --input user.lex --op search --query now --by code

# 按词语搜索
python lex_editor.py --input user.lex --op search --query 今天 --by word
```

### 编辑词条（支持同时修改多个键）

```bash
# 修改单个词条
python lex_editor.py --input user.lex --output user.lex --op edit --key now --value "2024-01-01 12:00:00"

# 同时修改多个词条（--key / --value 可重复）
python lex_editor.py --input user.lex --output user.lex \
  --op edit \
  --key now   --value "2024-01-01 12:00:00" \
  --key date  --value "2024-01-01"
```

### 删除词条

```bash
# 删除单个词条（按编码）
python lex_editor.py --input user.lex --output user.lex --op del --key now

# 删除多个词条
python lex_editor.py --input user.lex --output user.lex --op del --key now --key date
```

### 添加词条

```bash
python lex_editor.py --input user.lex --output user.lex --op add --key aaaa --value 工
```

---

## 设置 `now` / `date` 时间快捷词条

微软五笔输入法的用户词库支持自定义快捷词条，但**不会自动更新时间**。  
本项目提供 Perl 脚本 `loop_now_data_lex.PL`，在后台定期刷新 `now` 和 `date` 词条，  
使其始终显示为当前时间和日期。

### 原理

| 编码 | 词条值 | 说明 |
|------|--------|------|
| `now` | `%yyyy%-%MM%-%dd% %HH%:%mm%:%ss%` | 当前日期时间（输入法动态解析） |
| `date` | `%yyyy%-%MM%-%dd%` | 当前日期 |

> 微软五笔输入法会自动将 `%yyyy%`、`%MM%`、`%dd%`、`%HH%`、`%mm%`、`%ss%` 替换为对应的时间值。

### 默认词库路径

微软内置输入法的用户词库默认位于：

```
%userprofile%\AppData\Roaming\Microsoft\InputMethod\Chs\ChsWubiEUDPv1.lex
```

即：`C:\Users\<用户名>\AppData\Roaming\Microsoft\InputMethod\Chs\ChsWubiEUDPv1.lex`

### 使用步骤

**1. 用图形界面添加词条**：  
打开上述词库文件 → `Edit → Add Entry`  
- 编码填 `now`，词语填 `%yyyy%-%MM%-%dd% %HH%:%mm%:%ss%` → 保存  
- 编码填 `date`，词语填 `%yyyy%-%MM%-%dd%` → 保存

也可以用命令行一次完成：
```bash
python lex_editor.py ^
  --input "%userprofile%\AppData\Roaming\Microsoft\InputMethod\Chs\ChsWubiEUDPv1.lex" ^
  --output "%userprofile%\AppData\Roaming\Microsoft\InputMethod\Chs\ChsWubiEUDPv1.lex" ^
  --op add --key now  --value "%yyyy%-%MM%-%dd% %HH%:%mm%:%ss%" ^
  --op add --key date --value "%yyyy%-%MM%-%dd%"
```

**2. 启动后台刷新脚本**（需安装 [Strawberry Perl](https://strawberryperl.com/)）：
```bash
perl loop_now_data_lex.PL
```
脚本每 30 秒自动更新一次，控制台打印 `OK` 表示刷新成功。

**3. 开机自动启动（可选）**：  
将以下内容保存为 `start_lex_loop.bat`，放入 Windows 启动文件夹  
（`Win+R` 输入 `shell:startup`）：
```bat
@echo off
start /min perl "D:\path\to\loop_now_data_lex.PL"
```

### 在输入法中使用

打开五笔输入法，输入 `now` 即可上屏当前时间，输入 `date` 即可上屏当前日期。

---

## 构建 exe 安装包

```bash
# 双击运行，自动打包为单文件 exe
deploy.bat
```

输出位于 `release\lex_editor.exe`（或 `release\WubiLexEditor.zip`）。

---

## 项目结构

```
lex_reader/
├── lex_editor.py          # 主程序（图形界面 + 命令行）
├── loop_now_data_lex.PL   # Perl 后台刷新脚本
├── deploy.bat             # 打包脚本
├── user.lex               # 示例用户词库
└── release/
    ├── lex_editor.exe     # 打包好的独立 exe
    └── WubiLexEditor.zip  # 压缩包版本
```

---

## 作者

- **Author**: Jidor Tang  
- **Email**: tlqtangok@126.com  
- **Source**: https://github.com/tlqtangok/lex_fix
