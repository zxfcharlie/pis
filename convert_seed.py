import pandas as pd
import re
import json

SRC = '/mnt/user-data/uploads/圣诞灯串提示词库__1_.xlsx'
OUT = '/home/claude/product-image-service/backend/seed_data/templates.json'

LABEL_MAP = {
    '主体': 'subject',
    '风格': 'style',
    '摄影': 'photography',
    '氛围': 'atmosphere',
    '背景': 'background',
    '光线': 'light',
    '负面': 'negative',
    '参数': 'parameters',
}

FIELD_ORDER = ['subject', 'style', 'photography', 'atmosphere', 'background', 'light', 'negative', 'parameters']

def parse_prompt_block(text: str) -> dict:
    text = text.strip()
    # split on 【label】 markers, keep labels
    parts = re.split(r'(【[^】]+】)', text)
    result = {v: '' for v in LABEL_MAP.values()}
    current_key = None
    for part in parts:
        part_stripped = part.strip()
        if not part_stripped:
            continue
        m = re.match(r'【([^】]+)】', part_stripped)
        if m and m.group(1) in LABEL_MAP:
            current_key = LABEL_MAP[m.group(1)]
            continue
        if current_key:
            result[current_key] = part_stripped.strip()
    return result

def main():
    df = pd.read_excel(SRC)
    df['季节'] = df['季节'].fillna('圣诞')
    templates = []
    for i, row in df.iterrows():
        fields = parse_prompt_block(str(row['主体描述']))
        tpl = {
            'name': f"{row['季节']}-{row['产品']}-{row['场景/细节']}-{row['区域']}",
            'season': str(row['季节']).strip(),
            'scene': str(row['场景/细节']).strip(),
            'product': str(row['产品']).strip(),
            'region': str(row['区域']).strip(),
        }
        tpl.update({k: fields.get(k, '') for k in FIELD_ORDER})
        templates.append(tpl)

    with open(OUT, 'w', encoding='utf-8') as f:
        json.dump(templates, f, ensure_ascii=False, indent=2)

    print(f'Wrote {len(templates)} templates to {OUT}')
    print(json.dumps(templates[0], ensure_ascii=False, indent=2))

if __name__ == '__main__':
    main()
