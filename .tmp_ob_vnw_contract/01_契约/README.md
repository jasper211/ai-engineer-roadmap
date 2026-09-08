# 契约使用说明

OB Agent 将发布文件写入 `../02_OB发布/input_manifest.json`。VNW Agent执行：

```bash
python3 validate_manifest.py ../02_OB发布/input_manifest.json --receipt ../03_VNW回执/latest_receipt.json
```

校验器只读源文件并写回执；不会修改OB文件、VNW快照或前端。JSON Schema是字段规范，校验器使用Python标准库执行关键约束和实际文件Hash检查。

退出码：`0` 全部有效；`1` 有校验错误；`2` 清单本身无法读取。
