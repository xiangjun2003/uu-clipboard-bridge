# UUClipboardBridge

通过 **UU 远程 TCP 端口映射**同步两台 Mac 的文字和图片剪贴板。无需 iCloud 存储、无需 CrossPaste、无需两端能直接访问彼此的局域网地址。

A small macOS clipboard bridge over a UU Remote TCP port forward. Bidirectional plain text and PNG images, per-user login agents, shared-secret authentication, and no clipboard history stored by the bridge. This is an independent community project, not an official UU or Apple product.

> 这是两台受信任 Mac 之间的轻量工具，不是公网剪贴板服务器。HTTP 本身不加密；传输保护依赖 UU 隧道。请勿将服务端口暴露到公网或将配对文件上传到 GitHub。

## 工作方式

```text
Mac A（控制端 / client）                      Mac B（被控端 / server）
系统剪贴板 ⇄ Python + Swift                   Python + Swift ⇄ 系统剪贴板
                 ⇅                                 ⇅
          127.0.0.1:24131 ─── UU TCP 映射 ─── 127.0.0.1:24130
```

- 只需 **一条 A → B 的映射**。A 主动推送本机内容并轮询 B 的变化，实现双向同步，不需要反向端口映射。
- 服务端仅监听 `127.0.0.1`；客户端固定使用本机回环地址，不会回退到局域网直连。
- 支持 UTF-8 纯文本和实际图片内容；图片以 PNG 传输，接收端提供 PNG/TIFF 格式。
- 每条内容最多 20 MiB；不支持 Finder 文件引用、目录、富文本格式或多个剪贴板项目。
- 约每 0.35 秒检查剪贴板，远端长轮询等待最多 1 秒；实际延迟取决于网络和内容大小。
- 两端安装为当前用户的 LaunchAgent：**登录后自启动**，不是开机登录前的系统服务。

## 1. 准备两台 Mac

以下步骤中的 **A 是控制端，B 是被控端**。两端都需要：

1. 已登录 macOS 图形桌面，不要使用 root 或 `sudo` 安装本项目。
2. 已安装 UU 远程，并能从 A 连接 B；A 的 UU 客户端支持 TCP 端口映射。功能可用性以自己的 UU 版本和账号为准。
3. Python 3.9 或更新版本，以及 Apple Command Line Tools（提供 Git、Swift 编译器）。Python 只使用标准库，无需 `pip install`。

在两端终端检查：

```sh
python3 --version
xcrun --find swiftc
git --version
```

缺少 Command Line Tools 时运行以下命令，完成系统弹出的安装流程后再继续：

```sh
xcode-select --install
```

缺少 Python 时可从 [Python 官方网站](https://www.python.org/downloads/macos/)安装，或使用已有 Homebrew：

```sh
brew install python
```

确保 `python3 --version` 正常。安装器会记录当前 Python 可执行文件的绝对路径；以后删除或升级这个 Python 导致路径失效时，应重新执行安装步骤。

已实测 Apple Silicon Mac。Swift helper 在每台机器上本地编译，不分发预编译文件；Intel Mac 尚未实测。

## 2. 两端下载源码并编译

在 **A、B 各执行一次**：

```sh
mkdir -p "$HOME/Projects"
cd "$HOME/Projects"
git clone https://github.com/xiangjun2003/uu-clipboard-bridge.git
cd uu-clipboard-bridge
sh build.sh
python3 -m unittest -v test_bridge.py test_setup.py
```

如果已经克隆过，不要重复 clone；进入已有目录即可。编译生成的 `pasteboard` 只适用于本机架构，不需要复制到另一台。

协议测试使用模拟剪贴板和本机回环网络，不读取或修改真实剪贴板。真正的双端功能仍需按第 6 节验证。

## 3. 生成并安全传递配对文件

**只在 A 生成一次**：

```sh
cd "$HOME/Projects/uu-clipboard-bridge"
python3 generate_pairing.py
```

这会创建仅当前用户可读写的 `pairing.json`，其中是随机 256-bit 共享密钥。已有文件时命令会拒绝覆盖，避免误改现有部署。

通过 UU 的文件传输，把 A 的 `pairing.json` 私下发送到 B，再在 B 将它移动到源码目录。例如 B 收到文件的位置是“下载”时：

```sh
mv "$HOME/Downloads/pairing.json" "$HOME/Projects/uu-clipboard-bridge/pairing.json"
chmod 600 "$HOME/Projects/uu-clipboard-bridge/pairing.json"
```

**两端必须使用同一个文件，不要在 B 再生成一个新密钥。** 不要把文件内容贴到聊天、Issue、日志或公开仓库。`.gitignore` 已排除默认文件名，但不能保护你手动改名或强制提交的副本。

## 4. 安装两端后台服务

先在 **B（被控端）** 执行：

```sh
cd "$HOME/Projects/uu-clipboard-bridge"
python3 install.py server
python3 status.py server
```

正常输出包含 `"helperAlive": true`。

再在 **A（控制端）** 执行：

```sh
cd "$HOME/Projects/uu-clipboard-bridge"
python3 install.py client
```

安装会立即启动服务，并设置当前用户以后登录时自动启动。A 在映射启用前会等待连接，这是正常的。安装器只允许每个用户保留一个角色，重复安装会停止旧角色、替换程序和配置再启动。

文件位置：

| 文件 | 位置 |
| --- | --- |
| 程序、配置、日志 | `~/Library/Application Support/UUClipboardBridge/` |
| A 自启动项 | `~/Library/LaunchAgents/local.uuclipboardbridge.client.plist` |
| B 自启动项 | `~/Library/LaunchAgents/local.uuclipboardbridge.server.plist` |
| 配对密钥副本 | 安装目录内 `config.json`（权限 600） |

服务读取安装目录内的配置，安装完成后不依赖源码目录是否保留。保留一份私密配对文件用于更新，或更新时通过 `--pairing` 使用原安装配置：

```sh
# 示例：更新 A 时复用原密钥
python3 install.py client --pairing "$HOME/Library/Application Support/UUClipboardBridge/config.json"
```

不要盲目授权系统权限。本工具通过 AppKit 访问当前用户的剪贴板；它本身不模拟键盘或读取屏幕。若 macOS 显示剪贴板访问提示，请核对程序和用途。UU 远控自身的权限按 UU 提示配置。

## 5. 在 A 的 UU 中配置映射

在 A 的 UU 远程中选择 B，打开 **端口映射 → 添加**：

| 设置 | 值 |
| --- | --- |
| 名称 | `UUClipboardBridge` |
| 本地端口 | `24131` |
| 目标地址 | `127.0.0.1` |
| 目标端口 | `24130` |
| 协议（如可选） | TCP |

点击保存并启用，确认显示“成功”。这里的目标 `127.0.0.1` 是 **B 自己的回环地址**，不是 A，也不是 B 的局域网 IP。

不要把其他服务已有的端口改成这些值。如果端口被占用，先排查已有进程；本教程和安装器采用上述固定端口，修改端口需要同步更新安装配置和 UU 映射。

在 A 验证：

```sh
cd "$HOME/Projects/uu-clipboard-bridge"
python3 status.py client
```

显示 `"helperAlive": true` 表示 A 通过映射访问到了 B 的桥接服务，且 B 的剪贴板 helper 仍运行。**此检查不单独证明 A 的后台客户端正在工作**，还需进行实际复制测试。

## 6. 验证双向文字、图片与重连

测试会替换两端当前剪贴板，请先保存仍需要的内容。

1. 在 A 复制一段独特的文字，稍等后在 B 的文本编辑器里粘贴。
2. 在 B 复制另一段文字，在 A 粘贴。
3. 在 A 按 `Control + Shift + Command + 4` 截取小区域到剪贴板，在 B 支持图片粘贴的应用中粘贴；然后反向测试一次。
4. 在 A 关闭 UU 的 `UUClipboardBridge` 映射。`python3 status.py client` 应失败，客户端日志应出现 `disconnected`。
5. 映射关闭期间，在 A 复制新的测试内容；在 **120 秒内**重新开启映射，客户端应自动连接并发送最新待传内容。

微信等应用可能同时提供文件 URL 和 TIFF/PNG 图片。桥接优先发送剪贴板内的图片数据，不读取 URL 指向的文件。仅复制 Finder 里的图片文件通常属于“文件引用”，本工具不会发送。请复制图片本身或使用上述截图快捷键。

### 避免多个同步工具互相干扰

- 不需要 CrossPaste；建议退出或关闭它的同步功能。
- Apple 通用剪贴板依赖“接力”。可只在 B 的“系统设置 → 通用 → 隔空投送与连续互通（或隔空投送与接力）”中关闭“允许在这台 Mac 和 iCloud 设备之间使用接力”。这也会关闭该 Mac 的其他接力功能。[Apple 说明](https://support.apple.com/zh-cn/102430)
- 如果 UU 自身也提供剪贴板同步，可按需要关闭它，避免文字同时由多个通道传送。
- 本工具通过写入标记、剪贴板变化计数和内容哈希抑制自身回传，但不能保证其他同步工具改写内容后不会造成循环。

## 7. 日常使用、暂停和重新启动

**日常使用：** 两端开机并登录 → UU 连接 B → 确认映射成功 → 复制、粘贴。无需再次执行安装命令。

**只暂停网络同步：** 在 A 关闭这条 UU 映射。后台服务仍运行，仍观察剪贴板；映射恢复后自动重连。UU 退出时同理。

**完全停止当前用户的桥接：** 在对应机器执行，A 的角色为 `client`，B 为 `server`：

```sh
# A
launchctl bootout "gui/$(id -u)/local.uuclipboardbridge.client"
# B（在 B 上运行）
launchctl bootout "gui/$(id -u)/local.uuclipboardbridge.server"
```

这只停止当前登录会话；plist 仍存在，下次登录仍会自启动。若要恢复，无需重新安装：

```sh
# A
launchctl bootstrap "gui/$(id -u)" "$HOME/Library/LaunchAgents/local.uuclipboardbridge.client.plist"
# B（在 B 上运行）
launchctl bootstrap "gui/$(id -u)" "$HOME/Library/LaunchAgents/local.uuclipboardbridge.server.plist"
```

已加载但异常时可重启对应服务：

```sh
# A；B 将 client 改为 server
launchctl kickstart -k "gui/$(id -u)/local.uuclipboardbridge.client"
```

注销会停止用户服务；休眠会暂停执行。服务恢复、网络可达后重新连接。KeepAlive 会重启退出的主进程，但如果只有 helper 故障而主进程仍在，需要手动重启服务。

## 8. 排查问题

```sh
# A 上检查 LaunchAgent；B 将 client 改为 server
launchctl print "gui/$(id -u)/local.uuclipboardbridge.client"
tail -n 40 "$HOME/Library/Application Support/UUClipboardBridge/client.log"
tail -n 40 "$HOME/Library/Application Support/UUClipboardBridge/client.error.log"

# A 的 UU 映射监听
lsof -nP -iTCP:24131 -sTCP:LISTEN
# B 的桥接服务监听（在 B 执行）
lsof -nP -iTCP:24130 -sTCP:LISTEN
```

| 现象 | 检查方式 |
| --- | --- |
| B 的 status 失败 | 检查 server 的 LaunchAgent、Python 路径、helper 是否已编译、端口是否被占用 |
| B 正常，A status 失败 | 检查 UU 映射是否成功，是否映射到正确机器、正确端口 |
| status 返回 HTTPError | 检查两端是否安装同一份配对文件；密钥不一致会返回 401 |
| status 正常但不复制 | 检查 client 进程和日志；复制一段新的纯文本；启动时不会发送原剪贴板内容 |
| 图片不复制 | 确认复制的是实际图片而不是 Finder 文件引用，大小不超过 20 MiB |
| `helperAlive` 为 false | 重启对应服务，检查编译架构和 helper 错误日志 |
| 更新 Python 后无法启动 | 使用可用的 Python 重新安装该角色，复用原 config.json 密钥 |
| 一直相互覆盖 | 停用其他剪贴板同步通道，一次只在一端复制 |

日志仅记录类型、字节数和连接状态，不记录剪贴板正文或密钥。无需公开 `config.json` 排错；分享其他日志前也请先检查本机路径等个人信息。当前日志不自动轮转，可停止服务后定期清理。

## 9. 更新与卸载

更新时在两端分别执行：

```sh
cd "$HOME/Projects/uu-clipboard-bridge"
git pull --ff-only
sh build.sh
python3 -m unittest -v test_bridge.py test_setup.py
# A；B 改为 server
python3 install.py client --pairing "$HOME/Library/Application Support/UUClipboardBridge/config.json"
```

**卸载后台服务和自启动项：** 在每台要卸载的 Mac 上运行：

```sh
cd "$HOME/Projects/uu-clipboard-bridge"
python3 uninstall.py
```

验证 `launchctl print "gui/$(id -u)/local.uuclipboardbridge.client"`（B 改为 `server`）提示找不到服务。配置、程序和日志会保留，方便恢复；如不再需要，可在 Finder“前往文件夹”中打开 `~/Library/Application Support/`，将 `UUClipboardBridge` 文件夹移到废纸篓。同时删除源码目录里的私密 `pairing.json` 副本、移除 UU 中对应映射即可。不要删除其他 UU 映射。

## 安全边界与已知限制

- 持有密钥并能访问端口的进程可以读取或写入该桥接剪贴板；只用于自己信任的两台机器。服务没有 TLS、用户账号、多设备隔离或公网抗滥用能力。
- 仅服务端绑定回环并不代表 UU 的本地映射一定只在回环监听；请通过 `lsof` 检查 A 的实际监听地址，并限制不必要的局域网访问。
- 密钥泄漏时，停止两端服务，移走旧配对文件，生成新的同一份文件并重新安装两端。不要继续使用泄漏密钥。
- 标记为 concealed/transient 的剪贴板内容会跳过；**普通文本中的密码、验证码等无法自动识别**。需要隔离敏感操作时完全停止两端服务。
- 桥接不把剪贴板正文写入磁盘，但其他应用、剪贴板历史工具和操作系统可能另行保存。内容在进程内存中保留最新一项。
- 首次连接或重连跳过 B 的已有剪贴板；A 在离线期间新复制的最后一项最多待发送 120 秒。B 离线期间的内容不会补发，恢复后请重新复制。
- 两端同时复制可能互相覆盖。本工具没有冲突合并、历史队列或可靠的每次复制送达保证。
- 2026-11-11 已实测两台 Apple Silicon Mac 的双向文字/PNG、关闭映射后断开、开启后自动恢复；修复短连接兼容性后连续 30 次状态请求成功。实测使用 UU 映射路径，**没有实际切换到两个不同外网**。

## 项目文件

- `bridge.py`：认证、双向传输、重连和元数据日志。
- `pasteboard.swift`：AppKit 剪贴板读写，`build.sh` 在本机编译。
- `generate_pairing.py`：生成私密共享密钥，不覆盖已有文件。
- `install.py` / `uninstall.py`：安装、停止和移除用户自启动项。
- `status.py`：认证连通性检查，不输出正文和密钥。
- `test_bridge.py` / `test_setup.py`：协议及配对文件测试。

MIT License，详见 [LICENSE](LICENSE)。
