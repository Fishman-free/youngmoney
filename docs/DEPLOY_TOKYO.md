# 东京服务器部署指南（低延迟 + 固定出口 IP）

## 为什么是东京

币安（Binance）的撮合引擎部署在 **AWS ap-northeast-1（东京）**。物理距离决定延迟下限：

| 位置 | 到币安 API 的往返 | 能否做超短/高频 |
|---|---|---|
| 本机（家宽 + 轮换代理） | 550–1500 ms（且经常 451/不可达） | ❌ |
| 东京 VPS（同城机房） | **1–5 ms** | ✅ 可以谈 |

**附带好处（同等重要）**：VPS 是**固定 IP**，白名单一次配好永久有效——彻底消灭
`-2015`（IP 漂移）和 `451`（地域风控）这两个反复断线的病根。

## 一、选哪家（按优先级）

| 选项 | 配置 | 参考价 | 付款 | 适合 |
|---|---|---|---|---|
| **AWS Lightsail 东京** | 2 vCPU / 2G | ~$10/月 | 信用卡 / 支付宝（部分区） | 最省事，一键开 |
| **Vultr 东京** | 1–2 vCPU / 1–2G | $6–18/月 | **支付宝** | 国内用户友好，可随时换机房 |
| **阿里云国际 东京** | 1–2 vCPU / 2G | ¥60–120/月 | **支付宝** | 中文控制台，最熟悉 |
| **腾讯云国际 东京** | 1–2 vCPU / 2G | ¥60–120/月 | **支付宝** | 同上 |
| Oracle Cloud 东京 | ARM 4 核 / 24G | **免费** | 信用卡 | 省钱，但常抢不到容量 |
| AWS EC2 c7i 东京 | 专用算力 | $30+/月 | 信用卡 | 真上高频再考虑 |

**起步建议**：Vultr 或阿里云国际东京，最低配即可——我们的平台是纯 Python 中低频，
瓶颈在**网络距离**不在算力。系统选 **Ubuntu 24.04 LTS**。

> 提醒：开机器时选「东京」，不要选新加坡/香港（离撮合引擎远）。
> 机房内还要看区域：AWS 选 `ap-northeast-1`。

## 二、五步部署

### 1. 开机器 + SSH 密钥

创建实例时选 SSH 公钥登录（不要密码登录）。拿到固定公网 IP，记为 `$VPS_IP`。

本机生成密钥（如果还没有）：

```powershell
ssh-keygen -t ed25519 -C "bnbot-tokyo"
# 公钥在 ~/.ssh/id_ed25519.pub，创建实例时粘贴进去
ssh root@$VPS_IP          # 首登
```

### 2. 基础加固（上服务器后立刻做）

```bash
# 建普通用户，禁 root 直登
adduser trader && usermod -aG sudo trader
mkdir -p /home/trader/.ssh && cp ~/.ssh/authorized_keys /home/trader/.ssh/
chown -R trader:trader /home/trader/.ssh && chmod 700 /home/trader/.ssh
chmod 600 /home/trader/.ssh/authorized_keys

# 只开 SSH，其余全关
ufw allow 22/tcp && ufw --force enable
sed -i 's/^#\?PermitRootLogin.*/PermitRootLogin no/;s/^#\?PasswordAuthentication.*/PasswordAuthentication no/' /etc/ssh/sshd_config
systemctl restart ssh
```

### 3. 一键引导（装环境 + 拉代码 + 起服务）

把本仓库推到你的 GitHub（已开源：`Fishman-free/youngmoney`），然后：

```bash
sudo bash -c "$(curl -fsSL https://raw.githubusercontent.com/Fishman-free/youngmoney/master/scripts/vps-bootstrap.sh)"
```

或手动：

```bash
sudo apt update && sudo apt install -y python3 python3-venv python3-pip git
git clone https://github.com/Fishman-free/youngmoney.git /opt/bnbot
cd /opt/bnbot
python3 -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt 2>/dev/null || pip install laya   # laya 可选
```

### 4. 配凭据（只在这台机器上）

```bash
cd /opt/bnbot
printf 'BN_API_KEY=%s\nBN_API_SECRET=%s\n' '你的Key' '你的Secret' > .env
chmod 600 .env          # 只有属主可读
```

**不要把 key 提交进 git**（`.env` 已在 `.gitignore`）。

### 5. 验证延迟（这才是开这台机器的意义）

```bash
python3 scripts/vps-latency-check.py
```

预期在东京应该看到 **个位数毫秒**。若仍 > 50ms，说明机器不在东京或走了绕路。

## 三、常驻两条服务（systemd）

```bash
sudo tee /etc/systemd/system/bnbot-paper.service >/dev/null <<'EOF'
[Unit]
Description=bnbot three-sleeve paper loop
After=network-online.target
[Service]
User=trader
WorkingDirectory=/opt/bnbot
ExecStart=/opt/bnbot/.venv/bin/python -m bnbot.live --sleeves --proxy ""
Restart=always
RestartSec=30
[Install]
WantedBy=multi-user.target
EOF

sudo tee /etc/systemd/system/bnbot-status.service >/dev/null <<'EOF'
[Unit]
Description=bnbot status dashboard
After=network-online.target
[Service]
User=trader
WorkingDirectory=/opt/bnbot
ExecStart=/opt/bnbot/.venv/bin/python -m bnbot.server --port 8787 --host 0.0.0.0
Restart=always
[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable --now bnbot-paper bnbot-status
systemctl status bnbot-paper --no-pager
```

看面板：`http://$VPS_IP:8787/dashboard`（记得给 VPS 开 8787 端口，或用 SSH 隧道：
`ssh -L 8787:localhost:8787 trader@$VPS_IP`，更安全，推荐）。

## 四、迁移检查清单

- [ ] 机器在东京（`curl -s ipinfo.io/city`）
- [ ] 延迟达标（`scripts/vps-latency-check.py` 个位数 ms）
- [ ] 币安 API 白名单改成 **VPS 固定 IP**（并删掉旧的漂移 IP 条目）
- [ ] `.env` 权限 600、未入 git
- [ ] `systemctl is-enabled bnbot-paper` 为 enabled（重启自恢复）
- [ ] 三仓门禁报告可正常生成（`python -m bnbot.gate --sleeve C`）
- [ ] 本机旧循环停掉（避免两个进程同时写同一份状态）

## 五、成本与收益

| 项 | 数 |
|---|---|
| 月成本 | $6–18（最低配足够） |
| 延迟改善 | 550–1500ms → **1–5ms**（约 200–1000×） |
| 附带解决 | IP 漂移、地域 451、本机开关机导致的中断 |

**重要提醒**：延迟降下来只是**让你的策略能按设计执行**，不会凭空造出 edge。
C 仓回测已证明快参数在山寨币上没有样本内优势——真实的 alpha 仍需靠因子验证和
门禁数据说话。服务器是必要条件，不是充分条件。
