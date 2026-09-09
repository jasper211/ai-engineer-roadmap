# HKIA统一查询适配层v1.1·安装态验收

结论：**PASS，可供其他Python模型运行环境安装接入。**

## 被测制品

- 文件：`dist/hkia_query_adapter-1.1.0-py3-none-any.whl`
- SHA256：`c6f252894c1c9991e126b12f545c61ddd8a17e8ca93605e3697cc1cf5ec90fcb`
- Python要求：3.9+
- 第三方运行依赖：无

## 隔离验证方法

wheel安装到`/private/tmp/hkia_install_test`，随后切换到`/private/tmp`运行，确保没有从源码目录加载配置或模块。

## 验收结果

- 包版本：1.1.0。
- 包内`data_sources.json`与源码配置一致。
- 包内`metric_catalog.json`与源码配置一致。
- 6库健康检查通过：master 59,516；standard 5,022；annual 7,097；annual_market 2,942；provisional2025 414；financial 408。
- L1年度新造保费序列：成功，5个观察年。
- L5终止率序列：成功，5个观察年，单位`percentage_point`。
- L7年金及其他业务序列：成功，3个观察年。
- L16公司整付组件：成功；AIA International 2024返回10,677,251千港元。
- 2024 L16与2025 L1直接比较：正确阻断，`NOT_COMPARABLE_SCOPE`。
- 源码测试24/24通过；最终响应契约8/8通过。

## 接入前提

wheel封装查询代码与配置，不复制监管数据库。目标环境必须能访问`data_sources.json`所指向的HKIA目录；迁移到其他机器时，应通过`HKIAClient.open_readonly(hkia_root=...)`传入新根目录。

## 仍未等于“全维度开放”

L1–L7底层2,942条事实均已接入，但v1.1指标目录只开放经过验收的代表性分析口径。剩余产品、分红属性、缴费方式、业务类别组合需要逐项注册或通过受控维度查询协议开放，不能让模型直接传SQL筛选。
