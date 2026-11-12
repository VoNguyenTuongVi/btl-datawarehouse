
from __future__ import annotations
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'src'/'powerbi'))
from dss_measures import DSS_MEASURES


def require(test, message):
    if not test:
        raise AssertionError(message)


def test_measures():
    tmdl = (ROOT/'powerbi/CarSalesDSS.SemanticModel/definition/tables/_Measures.tmdl').read_text(encoding='utf-8')
    names = re.findall(r"^\s*measure '([^']+)'\s*=", tmdl, flags=re.M)
    require(len(names) == len(set(names)), 'Measure trùng tên trong TMDL')
    known = set(names)
    for name, dax, fmt, folder, desc in DSS_MEASURES:
        require(names.count(name) == 1, f'Measure DSS thiếu/trùng: {name}')
        require(not dax.lstrip().upper().startswith('RETURN '), f'RETURN không có VAR: {name}')
        require(dax.count('(') == dax.count(')'), f'Ngoặc () không khớp: {name}')
        require(dax.count('{') == dax.count('}'), f'Ngoặc {{}} không khớp: {name}')
        for ref in re.findall(r'(?<!\w)\[([^\]]+)\]', dax):
            # [Value] xuất hiện trong [Param...] nhưng là cột, không phải measure
            if ref != 'Value':
                require(ref in known or ref in {'Units Sold','Demand CV Hist','Demand CV for Member',
                    'ASP for Member','Demand Change Value','Safety Factor Value'},
                    f'{name} tham chiếu measure chưa định nghĩa: {ref}')
    print(f'OK: {len(DSS_MEASURES)} DSS measures, không trùng và tham chiếu hợp lệ')


def test_parameters():
    tb=ROOT/'powerbi/CarSalesDSS.SemanticModel/definition/tables'
    rel=(ROOT/'powerbi/CarSalesDSS.SemanticModel/definition/relationships.tmdl').read_text(encoding='utf-8')
    for name in ('Param_Growth','Param_Share','Param_Stability','Param_Accuracy'):
        txt=(tb/(name+'.tmdl')).read_text(encoding='utf-8')
        require('GENERATESERIES ( 0, 100, 5 )' in txt, name+' sai bước 5')
        require('dataType: int64' in txt, name+' sai kiểu dữ liệu')
        require(name not in rel, name+' không được có relationship với DW')
    print('OK: bốn bảng tham số tách rời và đúng phạm vi')


def test_report():
    d=ROOT/'powerbi/CarSalesDSS.Report/definition/pages'
    pages=json.loads((d/'pages.json').read_text(encoding='utf-8'))['pageOrder']
    for page in ('ReportSection','DSS_Priority','DSS_WhatIf'):
        require(page in pages, 'Thiếu trang '+page)
    for page in ('DSS_Priority','DSS_WhatIf'):
        files=list((d/page/'visuals').glob('*/visual.json'))
        require(len(files)>=5, 'Thiếu visual '+page)
        for p in files:
            v=json.loads(p.read_text(encoding='utf-8'))
            require(v['name']==p.parent.name, 'Visual name/path mismatch: '+str(p))
            require('visualType' in v['visual'], 'Thiếu visualType '+str(p))
            require(v['position']['x']+v['position']['width'] <= 1280, 'Visual tràn chiều ngang')
            require(v['position']['y']+v['position']['height'] <= 720, 'Visual tràn chiều dọc')
    print('OK: hai trang DSS có JSON hợp lệ, không tràn khung 1280×720')


def test_sanity_math():
    for values in ((25,25,25,25),(50,25,25,25),(100,0,0,0),(0,0,0,0)):
        t=sum(values)
        ws=tuple(v/t for v in values) if t else (0.25,)*4
        assert abs(sum(ws)-1)<1e-10
    f,cv,asp=100.5,0.2,25000
    from math import ceil
    order_base=ceil(f*(1+cv))
    order_scen=ceil(f*(1+0.2)*(1+1*cv))
    assert order_scen >= order_base
    assert f*(1+0.2)*asp>f*asp
    print('OK: các tình huống đại số Weight và S6')


if __name__=='__main__':
    test_measures()
    test_parameters()
    test_report()
    test_sanity_math()
    print('Tất cả kiểm thử tĩnh DSS đạt. Vẫn cần mở Power BI Desktop + Refresh.')
