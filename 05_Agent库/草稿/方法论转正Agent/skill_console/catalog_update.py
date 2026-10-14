"""Idempotent metadata enrichment; never installs or approves a skill."""
import json
from pathlib import Path
import app

def update(candidates):
    changes=[]
    with app.db() as c:
        for row in c.execute('SELECT * FROM skills').fetchall():
            b=json.loads(row['body']); before=json.loads(row['body'])
            if row['status']=='已接入':
                b['tags']=[t for t in b.get('tags',[]) if t!='未安装']
            b.setdefault('maintenance','上游维护日期尚待重新核验；不以历史安装成功推断当前维护情况。')
            b.setdefault('permission_risk','请核对依赖与既有安装凭据；本轮未增加权限或执行此资源。')
            b.setdefault('classification_reason','沿用既有用途分类：'+row['category'])
            b.setdefault('verified_at','2026-10-14（本地记录核对）')
            b.setdefault('validation_scope','本轮仅核对本地记录；历史运行结果见接入验证记录。')
            if b!=before:
                c.execute('UPDATE skills SET body=? WHERE id=?',(json.dumps(b,ensure_ascii=False),row['id']))
                c.execute('INSERT INTO events(skill_id,action,body,created) VALUES(?,?,?,?)',(row['id'],'元数据补充',json.dumps({'before':before,'after':b},ensure_ascii=False),app.now()))
                changes.append(row['id'])
    for item in candidates:
        with app.db() as c:
            existing=[json.loads(r[0]) for r in c.execute('SELECT body FROM skills')]
        if any(b.get('source_url','').rstrip('/')==item['source_url'].rstrip('/') and b.get('skill_path')==item['skill_path'] for b in existing):continue
        material=app.intake({'links':item['source_url'],'note':'官方来源候选；未安装，完整审查待完成。'})[0]
        changes.append(app.save_analysis({**item,'material_id':material['id']}))
    return changes

if __name__=='__main__':
    print(json.dumps(update(json.loads(Path(__file__).with_name('candidate_catalog.json').read_text())),ensure_ascii=False))
