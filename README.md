# 大湾区绿色通关与碳足迹评估系统

输入携带物品的自然语言描述与「出发地 → 目的地」，返回红/黄/绿通关裁决、物品 + 跨境交通的碳足迹，
以及澳门/香港本地低碳平替与合作方推荐。覆盖内地、澳门、香港三地 6 条路线。

- 香港法域：配方粉离境 1.8kg 限额、肉类/家禽/蛋类检疫、AFCD 植物进口证
- 内地入境内地：自港澳进境居民旅客 12000 元免税额度（与口岸免税店合并上限 15000 元）
- 跨境交通：广深港高铁 / 中旅大巴 / 喷射飞航 / 金光飞航，按里程×人均因子计入全链路碳排
- 低碳推荐：中旅生态游、香港本地农场/手信、澳门本土商品（数据可溯源）

业务规则与判定红线见 [AGENTS.md](AGENTS.md)，本文件只记录如何跑起来。

## 运行

```bash
# 首次准备（Python 3.11，装在 D 盘项目内）
D:\python3119\python.exe -m venv .venv
.venv\Scripts\pip.exe install -r requirements-portable.txt

# 演示页（http://localhost:8501）
.venv\Scripts\streamlit.exe run app.py

# FastAPI 服务（http://127.0.0.1:8000，文档 /docs）
.venv\Scripts\python.exe -m uvicorn api_server:app --host 127.0.0.1 --port 8000

# 命令行单次判定 / 离线兜底
.venv\Scripts\python.exe agent_brain.py "我带了2公斤含肉松的饼干" --pretty
.venv\Scripts\python.exe agent_brain.py "我带了2公斤含肉松的饼干" --offline
```

国内网络慢可在 pip 命令后加 `-i https://pypi.tuna.tsinghua.edu.cn/simple`。

## 环境变量

| 变量 | 默认 | 说明 |
|---|---|---|
| `DEEPSEEK_API_KEY` | 无 | 必填；缺失时自动本地降级（不报错，不判绿） |
| `DEEPSEEK_MODEL` | `deepseek-chat` | 兼容别名，当前命中 deepseek-flash；可选 `deepseek-v4-pro` |
| `DEEPSEEK_BASE_URL` | `https://api.deepseek.com` | OpenAI 兼容端点 |
| `DEEPSEEK_MAX_TOKENS` | `3500` | V4 会消耗 reasoning tokens，过低会得到空正文 |
| `DEEPSEEK_TIMEOUT` | `60` | 单次调用超时（秒） |
| `WEB_SEARCH_ENABLED` | `true` | 设为 `0/false/off` 关闭联网补充线索 |
| `WEB_SEARCH_MAX_RESULTS` | `5` | 联网结果条数上限 |

`config.yaml` 可选（本地兜底，已在 `.gitignore` 中排除）；环境变量优先。

## API

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/health` | 健康检查，返回 Key 来源与就绪状态（不回显密钥） |
| GET/POST | `/api/analyze` | 入参 `item_desc`、`direction`；`direction` 支持 6 条路线标签（如 `香港入境内地`），也接受 `内地→香港` 写法 |

```python
import requests

r = requests.get("http://127.0.0.1:8000/api/analyze",
                 params={"item_desc": "一斤苹果", "direction": "内地入境澳门"},
                 timeout=120)
print(r.json())
```

Windows 下用 curl 传中文参数会按 GBK 编码发出、被服务端当 UTF-8 解析成乱码，
请用上面的 Python 方式，或先 `chcp 65001` 再 curl。

## 数据

| 路径 | 内容 |
|---|---|
| `data/macau.sqlite` | 主库：`customs_rules`（含 region）/ `carbon_factors` / `transport_factors` / `search_logs` / `local_products` / `known_products` / `pending_products` |
| `knowledge/*.txt` | RAG 语料，启动时自动加载 |
| `knowledge/customs_rules_hk.jsonl` | 香港法条（奶粉/肉类/植物/烟酒/现金/电子烟/活体动物）与港澳 12000 元免税公告 |
| `knowledge/transport_factors.jsonl` | 跨境交通因子（含里程与来源） |
| `knowledge/carbon_factors_extra.jsonl` | 补充碳因子（配方粉/茶叶/鱼虾，均带文献来源） |
| `knowledge/partner_offers.jsonl` | 香港低碳品牌、WWF 环保海味、中旅生态游推荐 |
| `scripts/schema_macau.sql` | 建表 DDL；`scripts/init_db_macau.py` 幂等建库 |
| `scripts/migrate_hk_region.py` | 存量库升级（region + 香港方向 + 交通表，自动备份） |
| `tools/` | 法条导入（含 `fetch_hk_rules.py`）、交通因子、商品库、UGC 审核、烟测 |

## 测试

```bash
# 离线（默认，不花钱、不联网）
.venv\Scripts\python.exe tools\smoke_test.py

# 在线（真实调用 DeepSeek，验证模型名 / JSON mode / max_tokens）
set DEEPSEEK_API_KEY=sk-...
.venv\Scripts\python.exe tools\smoke_test.py --online
```

烟测默认不写 `search_logs`，避免污染线上查询历史；覆盖 12 个用例（含香港奶粉/生肉、中旅大巴联程）。

## 免责声明

系统输出仅供参考，最终以海关现场判定为准，不构成法律意见。
