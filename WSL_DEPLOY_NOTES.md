# WSL 部署问题记录

> 记录把本仓库（lewislulu/terminal-setup 的个人 fork）部署到 **WSL2** 时踩到的坑。
> 分两类：**一、WSL/网络特有**（本机环境导致，非仓库 bug）与 **二、仓库本身 bug**（与 WSL 无关，任何 Linux 都会触发，多数已在本轮修复）。
> 日期：2026-07-17 ｜ 机器：WSL2 Ubuntu 22.04，用户 `lys` ｜ 对照：原部署环境是原生 Linux 服务器。

---

## 一、WSL / 网络特有问题（非仓库 bug）

### 1. `sudo` 在非交互环境无 TTY

- **现象**：在 Claude Code 会话里用 `! ./setup.sh --zsh`（或任何非交互方式）执行，第一步就报：
  ```
  sudo: a terminal is required to read the password
  ```
- **根因**：非交互执行没有分配 TTY，`sudo` 无法读取密码。
- **解决**：**另开一个真实的 WSL/Windows Terminal 窗口**运行 `./setup.sh`，那里有 TTY，能正常输 sudo 密码。
- **教训**：凡是要 `sudo` 的步骤，都得在真实终端跑，不能靠会话内非交互执行。

### 2. Clash fake-ip 让 `apt` 解析到假 IP（核心卡点）

- **现象**：`sudo apt-get update` 反复报
  ```
  Connection failed [IP: 198.18.0.11 80]
  ```
  但 `curl` / `ping 8.8.8.8` 都正常。
- **根因**（`.wslconfig` 三项叠加 + Windows 端 Clash）：
  - `networkingMode=mirrored` + `dnsTunneling=true` → WSL 的 DNS 走 Windows → **Clash TUN/fake-ip 介入** → `mirrors.tuna.tsinghua.edu.cn` 被解析成假 IP `198.18.0.11`（`198.18.0.0/15` 是 fake-ip 段）。
  - `autoProxy=true` → WSL 自动注入 `http_proxy=http://127.0.0.1:7890` → **curl/wget/git/npm 读环境变量，走代理，正常**。
  - 但 **`apt` 在 `setup.sh` 里是 `sudo apt-get ...` 跑的，`sudo` 默认清掉环境变量**，于是 apt 既没代理、又只能连假 IP `198.18.0.11` → 卡死。
- **与原生 Linux 服务器的区别**（为什么旧机器没这问题）：旧机器代理是 SSH 隧道 `127.0.0.1:18888`，**只转发端口、不改 DNS**，DNS 返回镜像站真实 IP；即便某工具不走代理，直连真实 IP 也通。WSL+Clash 的 fake-ip 让「不走代理的工具」只能拿到假 IP，必须显式喂代理。
- **解决**：给 apt 写死代理（不靠环境变量，sudo 也认）：
  ```bash
  echo 'Acquire::http::Proxy "http://127.0.0.1:7890";
  Acquire::https::Proxy "http://127.0.0.1:7890";' | sudo tee /etc/apt/apt.conf.d/95proxy
  sudo apt-get update   # 这次全是 Get/Hit，不再报 198.18.0.11
  ```
- **⚠ 注意**：这个 `95proxy` 只在 **Clash 开着时**有效；若**关掉 Clash**，apt 会失败，那时 `sudo rm /etc/apt/apt.conf.d/95proxy` 即可（关 Clash 后 DNS 不再 fake-ip，直连就通）。

### 3. `git clone` 回退在 `sudo` 下同样无代理

- **现象**：zsh 插件 apt 包「不可用」时回退到 `sudo git clone`，报 `github.com ... SSL connection timeout`。
- **根因**：同上——`sudo git` 丢了 `http_proxy` 环境变量。
- **解决**：配好 `95proxy` 后，插件经 apt（jammy universe 里有 `zsh-autosuggestions`/`zsh-syntax-highlighting`）安装，**不再触发 git clone**。

### 4.（顺手做的）换清华源

- 原始 `archive.ubuntu.com` / `security.ubuntu.com` 在国内无代理直连不稳。换清华源后配合 `95proxy` 双保险：
  ```bash
  sudo cp /etc/apt/sources.list /etc/apt/sources.list.bak.$(date +%s)
  sudo sed -i 's@//.*archive.ubuntu.com@//mirrors.tuna.tsinghua.edu.cn@g; s@//security.ubuntu.com@//mirrors.tuna.tsinghua.edu.cn@g' /etc/apt/sources.list
  ```
- 注：单有 `95proxy`（让 apt 走 Clash、用真 DNS）其实就够用；换源是为了国内直连更快。

---

## 二、仓库本身的 bug（与 WSL 无关，本轮已修复）

> 这些在**任何 Linux** 上都会触发，不是 WSL 特有。已修复并提交推送（commit `4c693fc`、`0357d57`）。

### 1. `setup.sh` 在函数外使用 `local` 【已修复】

- **现象**：交互问 `Install Zellij? (y/N)` 选 `y` 后报
  ```
  ./setup.sh: line 746: local: can only be used in a function
  ```
  `set -e` 让脚本**在 Step 8（zellij）中止**，导致 **Step 9（部署 `.zshrc`/starship/git-delta 配置）根本没跑**。
- **根因**：starship 与 zellij 的「GitHub 下载」代码块在**顶层脚本作用域**（非函数内）用了 `local`，而 bash 的 `local` 只能在函数里用。zellij 块里还有一处顶层 `return 0`（同样非法，仅在非 x86_64/aarch64 时触发）。
- **修复**：
  - `local starship_arch` / `local starship_tmp` → `starship_arch=` / `starship_tmp=`（普通赋值）。
  - zellij 块同理；并去掉顶层 `return 0`，改用 `if [[ -n "$zellij_arch" ]]; then ... fi` 守卫下载逻辑（不支持该架构时跳过 zellij 而非崩溃）。
- **影响范围**：仅在「工具无捆绑二进制、需走 GitHub 下载」时触发——starship 有捆绑二进制（`bin/linux-x86_64/starship`）所以平时不触发；**zellij 无捆绑二进制，选 `y` 必崩**。

### 2. `configs/.zshrc`：Linux 下 `~/.local/bin` 未进 PATH 【已修复】

- **现象**：`cat`/`find` 别名（指向 `bat`/`fd`）失效，因为 `bat`/`fd` 是 setup.sh 在 `~/.local/bin` 建的符号链接，而该目录不在 PATH。
- **根因**：setup.sh 的 Homebrew→Linux 补丁 sed
  ```
  sed -i 's|export PATH="/opt/homebrew/bin:/opt/homebrew/sbin:$PATH"|# PATH — system paths on Linux\nexport PATH="$HOME/.local/bin:$PATH"|'
  ```
  把 `export PATH="$HOME/.local/bin:$PATH"` 插进了 `if [[ -d /opt/homebrew ]]; then` 分支内——**Linux 上该分支不执行**，所以这行永远不生效。
- **修复**：在 template `configs/.zshrc` 的 `else`（无 Homebrew）分支直接加：
  ```zsh
  else
      BREW_PREFIX=""
      # Linux / 无 Homebrew：~/.local/bin 放着 bat/fd 符号链接与用户级安装
      export PATH="$HOME/.local/bin:$PATH"
  fi
  ```
- **注**：本机当前 `~/.zshrc` 是修复**前**部署的，PATH 经 `~/.zshrc.local` 里的 `export PATH="$HOME/.local/bin:$PATH"` 补齐；template 的修复惠及**后续重新部署**。（原 setup.sh 那条 sed 保留未删，在 Linux 上已成无害空操作。）

---

## 三、Node 管理器（nvm → fnm 统一，迁移踩坑）

- **背景**：原机器用 **nvm** 管 Node（v16/v18），`claude` 等全局包装在 nvm v18 下。本仓库模板 `configs/.zshrc` 用的是 **fnm**（`eval "$(fnm env --use-on-cd --shell zsh)"`），部署后新 shell 激活 fnm 的 node。
- **现象**：`exec zsh` 进新环境后 `claude` 用不了——新 `.zshrc` 不加载 nvm，nvm v18（连同 claude）不在 PATH；`node` 落到 fnm 的 v24，而 claude 还在 nvm v18。
- **根因**：**两个 node 管理器并存**（nvm v18 有 claude / fnm v24 是默认激活）。`node`、`npm` 走 fnm v24，全局包却在 nvm v18，越用越乱（`npm -g` 装到 v24、claude 在 v18）。
- **处理（本机选择：统一到 fnm v24）**：
  1. 把 claude 装到 fnm v24（PATH 须让 fnm v24 在前，否则 npm 会跑到 nvm 的 node 下）：
     `~/.local/share/fnm/node-versions/v24.18.0/installation/bin/npm install -g @anthropic-ai/claude-code --allow-scripts`
     （`--allow-scripts`：Node 24 自带的 npm v11 默认拦 postinstall，需显式允许。）
  2. **不要**在 `~/.zshrc.local` 里加载 nvm——模板的 `fnm env` 已激活 v24，再加载 nvm 会抢 node、造成 claude/全局包错乱。
  3. 删掉 `~/.nvm`（本机 v16+v18，释放 547M）。
- **要点**：fnm 也读 `.nvmrc`/`.node-version`（`--use-on-cd` 自动切版本），需要别的版本就 `fnm install <ver>`，**不必装回 nvm**。

---

## 四、最终可用状态（本机）

| 项 | 状态 / 位置 |
|---|---|
| apt 代理 | `/etc/apt/apt.conf.d/95proxy` → `127.0.0.1:7890`（Clash 在则保留） |
| apt 源 | 清华 `mirrors.tuna.tsinghua.edu.cn` |
| CLI 工具 | `bat(cat) fd(find) rg(jq) fzf btop zoxide lazygit delta eza tldr`（apt + 捆绑二进制） |
| starship | `/usr/local/bin/starship` + `~/.config/starship.toml` |
| zsh 插件 | apt 装：`zsh-autosuggestions` / `zsh-syntax-highlighting`（`/usr/share/...`） |
| zellij | `~/.local/bin/zellij`（0.44.3，本轮走代理下载、免 sudo） |
| `~/.zshrc` | 模板部署 + Linux 补丁；`~/.zshrc.local` 保留并补了 `~/.local/bin` PATH |
| Node | **fnm v24.18.0** 统一管理（claude 装在 v24）；nvm 已移除（见第三节） |
| git-delta | 已配 `core.pager=delta` 等 |
| 字体 | MesloLGS NF 装在 WSL `~/.local/share/fonts`；**Windows 侧终端需另行安装该字体**才能显示 Nerd Font 图标 |

> 日常 shell 用 `autoProxy` 注入的 `http_proxy` 即可（curl/git/npm 等自动走 Clash），无需在 `.zshrc.local` 配代理。Node 统一用 **fnm v24**（claude 装在 v24），nvm 已移除——详见第三节。

---

## 五、命令速查（复现/补救）

```bash
# apt 走代理（Clash fake-ip 环境必备）
echo 'Acquire::http::Proxy "http://127.0.0.1:7890";
Acquire::https::Proxy "http://127.0.0.1:7890";' | sudo tee /etc/apt/apt.conf.d/95proxy

# 换清华源
sudo sed -i.bak 's@//.*archive.ubuntu.com@//mirrors.tuna.tsinghua.edu.cn@g; s@//security.ubuntu.com@//mirrors.tuna.tsinghua.edu.cn@g' /etc/apt/sources.list

# 关掉 Clash 后若 apt 失败 → 删代理配置
sudo rm /etc/apt/apt.conf.d/95proxy

# 免 sudo 装 zellij 到 ~/.local/bin（需 ~/.local/bin 在 PATH，已由 .zshrc.local 保证）
zt="$(mktemp -d)"
curl -fsSL https://github.com/zellij-org/zellij/releases/latest/download/zellij-x86_64-unknown-linux-musl.tar.gz | tar xz -C "$zt"
install "$zt/zellij" ~/.local/bin/zellij && rm -rf "$zt"
```
