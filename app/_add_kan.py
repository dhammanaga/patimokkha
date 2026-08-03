import json
from aksharamukha.transliterate import process
data = json.load(open('_test_ch1_data.json', encoding='utf-8'))
for s in data:
    out = []
    for w in s['pali'].split():
        w0 = w.strip(".,;:!?()[]{}")
        if not w0:
            continue
        try:
            out.append(process('IAST', 'Kannada', w0))
        except Exception:
            out.append(w0)
    s['kan'] = ' '.join(out)
json.dump(data, open('_test_ch1_data.json', 'w', encoding='utf-8'), ensure_ascii=False)
print('updated', len(data), 'sentences with kan field')
print('sample[0].kan =', data[0]['kan'])
