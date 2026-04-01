# Pexels API 使用限制与并发建议

本文面向本项目在 `video_source=pexels` 场景下的实际使用。

## 1. 官方默认限额（以 Pexels 官方文档为准）

根据 Pexels API 文档中的 `Guidelines` 与 `Request Statistics`：

1. 默认速率限制：`200 requests/hour`
2. 默认月度限制：`20,000 requests/month`
3. 可申请更高额度：可联系 `api@pexels.com` 申请提升

说明：官方未公开一个明确的“固定并发上限数字”（例如“最多 N 并发连接”）。实际并发能力由你的请求模式、网络和风控判定共同决定。

## 2. 请求额度查看方式

成功请求（2xx）会返回以下响应头：

1. `X-Ratelimit-Limit`：月度总额度
2. `X-Ratelimit-Remaining`：月度剩余额度
3. `X-Ratelimit-Reset`：月度额度重置时间（Unix 时间戳）

注意：`429 Too Many Requests` 通常不会带这些头，因此建议在平时成功请求时就持续记录剩余额度。

## 3. 本项目推荐并发策略（实践建议）

当前项目里素材下载流程是“关键词搜索 + 逐条下载”，并不是高并发批量爬取；为了稳定和避免触发限流，建议：

1. 单 API Key 搜索请求并发控制在 `1-2`
2. 若使用多个 Key，按 Key 轮转分流，不要瞬时突发
3. 失败重试采用指数退避：例如 1s, 2s, 4s, 8s
4. 遇到 `429` 时立即降并发，不要无间隔重试

经验值：若你按“单任务每次 5 个关键词，每词 1 次搜索请求”的模式运行，纯搜索部分大约消耗 5 次请求；再考虑重试、补抓等场景，建议预留至少 20%-30% 额度缓冲。

## 4. 额度估算示例

假设：

1. 每个视频任务平均消耗 8 次 Pexels API 请求（含重试）
2. 每小时限制 200 次

则理论上每小时可跑任务数约为：

$$
\left\lfloor \frac{200}{8} \right\rfloor = 25
$$

实际建议按 60%-80% 利用率运行（约 15-20 个任务/小时）以减少限流风险。

## 5. 合规与归因

使用 Pexels 内容时，请遵循其 API 与内容使用条款，建议在产品中保留可见来源归因（如 `Photos provided by Pexels`）。

---

参考：

- Pexels API Documentation: https://www.pexels.com/api/documentation/