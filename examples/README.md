# bidding-skill：已验收示例

本目录只展示 **4 个完全通过的真实正向场景**（最低要求4例）。

每例均为真实、非空、非缓存调用；技术检查、独立业务检查和离线浏览器检查全部通过。报告保持原实测字节，不把空数据、报错处理或仅生成页面计作通过。

| 场景 | 真实使用需求 | 报告 |
|---|---|---|
| [施工总包企业招投标全景](01-contractor-bid-profile/README.md) | 请分析中国建筑第八工程局有限公司近年的中标、招标、采购参与和拟建项目情况。 | [HTML](01-contractor-bid-profile/report.html) / [MD](01-contractor-bid-profile/report.md) / [JSON](01-contractor-bid-profile/report.json) |
| [ICT 企业政企标讯画像](02-ict-bid-profile/README.md) | 请查看华为技术有限公司的招投标参与、主要标的和区域分布。 | [HTML](02-ict-bid-profile/report.html) / [MD](02-ict-bid-profile/report.md) / [JSON](02-ict-bid-profile/report.json) |
| [新能源招投标公告机会监测](09-renewable-announcement-monitor/README.md) | 请检索包含“新能源”的招投标公告，列出每条公告的标题和发布时间，并按实际可用字段补充公告类型或地区，用于项目机会初筛；不要根据缺失金额判断项目规模。 | [HTML](09-renewable-announcement-monitor/report.html) / [MD](09-renewable-announcement-monitor/report.md) / [JSON](09-renewable-announcement-monitor/report.json) |
| [ICT 企业拟建项目线索管道](10-ict-planned-project-pipeline/README.md) | 请基于华为技术有限公司的公开数据，单独整理拟建项目线索和招投标参与公告，区分两种数据口径，供政企业务团队排查潜在项目。 | [HTML](10-ict-planned-project-pipeline/report.html) / [MD](10-ict-planned-project-pipeline/report.md) / [JSON](10-ict-planned-project-pipeline/report.json) |

- [逐例验收结果](results.json) · [业务复核](review.json) · [证据摘要](evidence-index.json)
- [完整测试记录](../test-records/live-replaced-20261027/README.md)仅用于审计，不属于可展示示例。
- 当前数据与结论限于原查询时点及公开样本；覆盖率不代表准确率或低风险。
