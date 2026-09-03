# raw_data

存放采集脚本抓下来的原始文件（JSON/HTML/PDF原样保存，不做任何清洗），跟标准化后的数据库物理分开——原始文件是"可回查的证据"，标准化数据是"可查询的结果"，两者不能混。

建议按险企分子目录，如：

```
raw_data/
├── aia/
│   └── fulfillment-ratio_2026-09-03.json
├── prudential/
│   ├── fulfillment-ratio-irr-track-record_2026-09-03.pdf
│   └── rbc-disclosure-statement-2024_2026-09-03.pdf
├── ctflife/
│   └── fulfillment-ratios-dividends_2026-09-03.html
└── ...
```

文件名带抓取日期，同一险企多次抓取不覆盖旧文件——年度披露数据每年会更新，保留历史抓取快照方便core对比"今年比去年是不是真的变了"。

Codex接手后，第一批10家险企的真实入口URL见 `../../01_初始化项目_Initialize_Project/需求定义.md` 第七节，直接用那份清单开始抓取即可。
