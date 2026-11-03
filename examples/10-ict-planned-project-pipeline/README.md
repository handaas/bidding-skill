# ICT 企业拟建项目线索管道

- 用户需求：请基于华为技术有限公司的公开数据，单独整理拟建项目线索和招投标参与公告，区分两种数据口径，供政企业务团队排查潜在项目。
- 决策用途：把拟建项目与招投标参与公告分层形成可复核线索管道。
- 本轮结果：**本轮检查通过**
- 实际工具调用：5；失败 0
- 章节覆盖率：86%（不代表证据质量）

## 预期业务检查（不自动宣称通过）

- 拟建项目调用必须成功并返回非空项目记录
- 招投标参与明细调用必须成功并返回非空公告记录
- 拟建项目与参与公告分别展示各自实际项目名或标题及可用时间/地区字段
- 不得把拟建线索表述为已立项、已采购或已授标

## 本轮自动检查发现


## 使用局限

- 拟建项目为外部线索，可能重复、延期或取消
- 公开标讯不覆盖企业全部商业合同

## 证据与复现

- [审计结果](result.json)
- [工具调用、结果形态与响应摘要哈希](calls.json)
- [JSON](report.json) / [HTML](report.html) / [Markdown](report.md)

```bash
python3 bidding-skill/scripts/compose_report.py --enterprise '华为技术有限公司' --page-size 5 --planned-page-size 10 --output bidding-skill/output/10-ict-planned-project-pipeline/report.json --report-output bidding-skill/output/10-ict-planned-project-pipeline/report.html
```

## 逐场景业务复核

当前真实产物逐项复核通过；结论限于本次上游公开样本与报告声明口径。

- **pass** 拟建项目调用必须成功并返回非空项目记录：已证明“拟建项目调用必须成功并返回非空项目记录”。 实际调用=[{"tool":"bid_bigdata_bid_win_stats","status":"data","row_count":null,"reported_total":null,"arguments":{"matchKeyword":"华为技术有限公司","keywordType":"name"}},{"tool":"bid_bigdata_tender_stats","status":"data","row_count":null,"reported_total":null,"arguments":{"matchKeyword":"华为技术有限公司","keywordType":"name"}},{"tool":"bid_bigdata_procurement_stats","status":"empty","row_count":null,"reported_total":null,"arguments":{"matchKeyword":"华为技术有限公司","keywordType":"name"}},{"tool":"bid_bigdata_bidding_info","status":"data","row_count":5,"reported_total":1000,"arguments":{"matchKeyword":"华为技术有限公司","keywordType":"name","pageSize":5}},{"tool":"bid_bigdata_planned_projects","status":"data","row_count":10,"reported_total":1005,"a… subject={"enterprise":"华为技术有限公司","matchKeyword":"华为技术有限公司","keywordType":"name","match_raw":"华为技术有限公司","resolved":true,"resolve_reason":"视为企业全称"} 口径={"match_target":"华为技术有限公司","match_type":"标讯统计按企业主体匹配（keywordType=name）","data_scope":"中标信息统计、招标信息统计、采购信息统计、招投标信息、拟建公告","products":["中标信息统计","招标信息统计","采购信息统计","招投标信息","拟建公告"],"limit":"数据来自公开招投标与采购公示；少量项目可能存在录入延迟或信息不全。"} 实际记录样本={"win_subject":[{"名称":"扩容工程","数量":"77","占比":"1.07"},{"名称":"交换机","数量":"65","占比":"0.9"}],"win_amount":[{"名称":"10万以下","数量":"125","占比":"7.84"},{"名称":"10万~50万","数量":"187","占比":"11.72"}],"win_area":[{"名称":"北京","数量":"878","占比":"-"},{"名称":"山西省","数量":"211","占比":"-"}],"win_trend":[{"年份":"2026","数量":"397"},{"年份":"2025","数量":"587"}],"tender_subject":[{"名称":"研发装备提升","数量":"39","占比":"15.54"},{"名称":"无线产品研发","数量":"35","占比":"13.94"}],"tender_amount":[{"名称":"10万以下","数量":"14","占比":"10.37"},{"名称":"10万~50万","数量":"12","占比":"8.89"}],"tender_area":[{"名称":"河南省","数量":"1","占比":"-"},{"名称":"宁夏回族自治区","数量":"1","占比":"-"}],"tender_trend":[{"年份":"2026","数量":"18"},{"年份":"2025","数量":"17"}],"customer_top":[{"客户/采购方":"中国铁塔湖南省分公司","出现次数":1},{"客户/采购方":"中国移动通信集团上海有限公司","出现次数":1}],"role_dist":[{"角色":"中标","数量":5}],"info_type_dist":[{"信息类型":"中标公告","数量":4},{"信息类型":"招标公告","数量":1}],"info_records":[{"公告标题":"中国移动内蒙古公司2024年XC云一二期工程云平台软件及集成服务采购项目_中标结果公示","公告类型":"中标公告","招投标角色":"中标","项目地区":"内蒙古自治区","项目金额":"-","公告时间":"2024-12-06","标的物":""},{"公告标题":"中国铁塔湖南省分公司黔张常铁路湖南段公网通信覆盖工程POI、合路器、天线材料采购项目-中标候选人公示","公告类型":"中标公告","招投标角色":"中标","项目地区":"湖南省 长沙市","项目金额":"201.48 万元","公告时间":"2019-04-18","标的物":"POI、合路器、天线材料、公网通信覆盖工程"}],"planned_records":[{"项目… 可见章节=[{"title":"中标标的分布","note":"按标的物统计中标数量与占比"},{"title":"中标金额分布","note":"按金额区间统计中标占比"},{"title":"中标区域分布","note":"按区域统计中标数量"},{"title":"中标趋势","note":"按年度统计中标数量"},{"title":"招标标的分布","note":"按标的物统计招标数量与占比"},{"title":"招标金额分布","note":"按金额区间统计招标占比"},{"title":"招标区域分布","note":"按区域统计招标数量"},{"title":"招标趋势","note":"按年度统计招标数量"},{"title":"采购产品分布","note":"按产品统计采购数量与占比"},{"title":"采购区域分布","note":"按地区统计采购客户数"},{"title":"主要客户/采购方","note":"按招投标公告中出现的采购方/客户聚合（出现次数）"},{"title":"角色结构","note":"招标/中标/候选 角色占比"},{"title":"招投标参与明细","note":"本次展示 5 条；上游总量 1000"},{"title":"拟建项目","note":"本次展示拟建公告 10 条；上游总量 1005"}] 三件套=True，空tbody=False，quality={"total_sections":14,"populated_sections":12,"empty_sections":2,"coverage_pct":86}
- **pass** 招投标参与明细调用必须成功并返回非空公告记录：已证明“招投标参与明细调用必须成功并返回非空公告记录”。 实际调用=[{"tool":"bid_bigdata_bid_win_stats","status":"data","row_count":null,"reported_total":null,"arguments":{"matchKeyword":"华为技术有限公司","keywordType":"name"}},{"tool":"bid_bigdata_tender_stats","status":"data","row_count":null,"reported_total":null,"arguments":{"matchKeyword":"华为技术有限公司","keywordType":"name"}},{"tool":"bid_bigdata_procurement_stats","status":"empty","row_count":null,"reported_total":null,"arguments":{"matchKeyword":"华为技术有限公司","keywordType":"name"}},{"tool":"bid_bigdata_bidding_info","status":"data","row_count":5,"reported_total":1000,"arguments":{"matchKeyword":"华为技术有限公司","keywordType":"name","pageSize":5}},{"tool":"bid_bigdata_planned_projects","status":"data","row_count":10,"reported_total":1005,"a… subject={"enterprise":"华为技术有限公司","matchKeyword":"华为技术有限公司","keywordType":"name","match_raw":"华为技术有限公司","resolved":true,"resolve_reason":"视为企业全称"} 口径={"match_target":"华为技术有限公司","match_type":"标讯统计按企业主体匹配（keywordType=name）","data_scope":"中标信息统计、招标信息统计、采购信息统计、招投标信息、拟建公告","products":["中标信息统计","招标信息统计","采购信息统计","招投标信息","拟建公告"],"limit":"数据来自公开招投标与采购公示；少量项目可能存在录入延迟或信息不全。"} 实际记录样本={"win_subject":[{"名称":"扩容工程","数量":"77","占比":"1.07"},{"名称":"交换机","数量":"65","占比":"0.9"}],"win_amount":[{"名称":"10万以下","数量":"125","占比":"7.84"},{"名称":"10万~50万","数量":"187","占比":"11.72"}],"win_area":[{"名称":"北京","数量":"878","占比":"-"},{"名称":"山西省","数量":"211","占比":"-"}],"win_trend":[{"年份":"2026","数量":"397"},{"年份":"2025","数量":"587"}],"tender_subject":[{"名称":"研发装备提升","数量":"39","占比":"15.54"},{"名称":"无线产品研发","数量":"35","占比":"13.94"}],"tender_amount":[{"名称":"10万以下","数量":"14","占比":"10.37"},{"名称":"10万~50万","数量":"12","占比":"8.89"}],"tender_area":[{"名称":"河南省","数量":"1","占比":"-"},{"名称":"宁夏回族自治区","数量":"1","占比":"-"}],"tender_trend":[{"年份":"2026","数量":"18"},{"年份":"2025","数量":"17"}],"customer_top":[{"客户/采购方":"中国铁塔湖南省分公司","出现次数":1},{"客户/采购方":"中国移动通信集团上海有限公司","出现次数":1}],"role_dist":[{"角色":"中标","数量":5}],"info_type_dist":[{"信息类型":"中标公告","数量":4},{"信息类型":"招标公告","数量":1}],"info_records":[{"公告标题":"中国移动内蒙古公司2024年XC云一二期工程云平台软件及集成服务采购项目_中标结果公示","公告类型":"中标公告","招投标角色":"中标","项目地区":"内蒙古自治区","项目金额":"-","公告时间":"2024-12-06","标的物":""},{"公告标题":"中国铁塔湖南省分公司黔张常铁路湖南段公网通信覆盖工程POI、合路器、天线材料采购项目-中标候选人公示","公告类型":"中标公告","招投标角色":"中标","项目地区":"湖南省 长沙市","项目金额":"201.48 万元","公告时间":"2019-04-18","标的物":"POI、合路器、天线材料、公网通信覆盖工程"}],"planned_records":[{"项目… 可见章节=[{"title":"中标标的分布","note":"按标的物统计中标数量与占比"},{"title":"中标金额分布","note":"按金额区间统计中标占比"},{"title":"中标区域分布","note":"按区域统计中标数量"},{"title":"中标趋势","note":"按年度统计中标数量"},{"title":"招标标的分布","note":"按标的物统计招标数量与占比"},{"title":"招标金额分布","note":"按金额区间统计招标占比"},{"title":"招标区域分布","note":"按区域统计招标数量"},{"title":"招标趋势","note":"按年度统计招标数量"},{"title":"采购产品分布","note":"按产品统计采购数量与占比"},{"title":"采购区域分布","note":"按地区统计采购客户数"},{"title":"主要客户/采购方","note":"按招投标公告中出现的采购方/客户聚合（出现次数）"},{"title":"角色结构","note":"招标/中标/候选 角色占比"},{"title":"招投标参与明细","note":"本次展示 5 条；上游总量 1000"},{"title":"拟建项目","note":"本次展示拟建公告 10 条；上游总量 1005"}] 三件套=True，空tbody=False，quality={"total_sections":14,"populated_sections":12,"empty_sections":2,"coverage_pct":86}
- **pass** 拟建项目与参与公告分别展示各自实际项目名或标题及可用时间/地区字段：拟建项目表实际记录“无线产品研发项目2026No59”，建设地点“广东省 深圳市”，发布时间“2026-10-09”；参与公告表实际记录“中国移动内蒙古公司2024年XC云一二期工程云平台软件及集成服务采购项目_中标结果公示”，项目地区“内蒙古自治区”，公告时间“2024-12-06”。两类名称及时间/地区均来自各自同一实际记录。
- **pass** 不得把拟建线索表述为已立项、已采购或已授标：报告将上游记录置于“拟建项目”章节，摘要和指标均称“拟建项目”；记录内“立项类型备案”是上游项目内容原值，报告没有据此将拟建线索推断为已采购或已授标。

## 离线浏览器检查

[Ego Lite 离线图表、页面溢出和脚本检查](browser-check.json)