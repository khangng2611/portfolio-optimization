"""Typeset the verified Markdown report using bundled python-docx."""
from pathlib import Path
import re
from docx import Document
from docx.shared import Inches,Pt,RGBColor
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.enum.table import WD_TABLE_ALIGNMENT,WD_CELL_VERTICAL_ALIGNMENT

ROOT=Path(__file__).resolve().parents[1]
SOURCE=ROOT/'docs/core_experiment_report.md'
OUT=ROOT/'submission';OUT.mkdir(exist_ok=True)


def plain(s):
    s=re.sub(r'\[([^\]]+)\]\([^)]+\)',r'\1',s)
    return s.replace('**','').replace('`','')


def make_table(doc,lines):
    rows=[[plain(x.strip()) for x in line.strip().strip('|').split('|')] for line in lines]
    rows=[r for r in rows if not all(re.fullmatch(r':?-+:?',x) for x in r)]
    table=doc.add_table(rows=0,cols=len(rows[0]));table.alignment=WD_TABLE_ALIGNMENT.CENTER
    table.autofit=False
    n=len(rows[0]);first=1.55 if n>=6 else 2.5 if n==2 else 2.25 if n==4 else 1.8
    widths=[first]+[(6.55-first)/(n-1)]*(n-1)
    for i,row in enumerate(rows):
        cells=table.add_row().cells
        trPr=table.rows[-1]._tr.get_or_add_trPr()
        trPr.append(OxmlElement('w:cantSplit'))
        if i==0:
            repeat=OxmlElement('w:tblHeader');trPr.append(repeat)
        for j,value in enumerate(row):
            cell=cells[j];cell.width=Inches(widths[j]);cell.vertical_alignment=WD_CELL_VERTICAL_ALIGNMENT.CENTER
            cell.text=value;tcPr=cell._tc.get_or_add_tcPr()
            shade=OxmlElement('w:shd');shade.set(qn('w:fill'),'DCE6F1' if i==0 else 'F5F7FA' if i%2==0 else 'FFFFFF');tcPr.append(shade)
            borders=OxmlElement('w:tcBorders')
            for edge in ['top','left','bottom','right']:
                element=OxmlElement('w:'+edge);element.set(qn('w:val'),'single');element.set(qn('w:sz'),'4');element.set(qn('w:color'),'D9D9D9');borders.append(element)
            tcPr.append(borders)
            margins=OxmlElement('w:tcMar')
            for side in ['top','bottom','left','right']:
                element=OxmlElement('w:'+side);element.set(qn('w:w'),'65');element.set(qn('w:type'),'dxa');margins.append(element)
            tcPr.append(margins)
            for p in cell.paragraphs:
                p.paragraph_format.space_after=Pt(1);p.paragraph_format.line_spacing=1.05
                p.paragraph_format.keep_with_next=(i<len(rows)-1)
                for run in p.runs:run.font.size=Pt(9);run.bold=i==0
    doc.add_paragraph().paragraph_format.space_after=Pt(1)


def main():
    doc=Document();sec=doc.sections[0]
    sec.page_width=Inches(8.27);sec.page_height=Inches(11.69)
    sec.top_margin=sec.bottom_margin=Inches(.72);sec.left_margin=sec.right_margin=Inches(.85)
    for name in ['Normal','Title','Heading 1','Heading 2','List Bullet']:
        style=doc.styles[name];style.font.name='Times New Roman';style.font.color.rgb=RGBColor(0,0,0)
        style.font.size=Pt(11 if name in ['Normal','List Bullet'] else 20 if name=='Title' else 14)
    normal=doc.styles['Normal'].paragraph_format;normal.space_after=Pt(6);normal.line_spacing=1.12
    for name in ['Heading 1','Heading 2']:
        doc.styles[name].paragraph_format.space_before=Pt(11);doc.styles[name].paragraph_format.space_after=Pt(5)
    lines=SOURCE.read_text().splitlines();i=0;code=False
    while i<len(lines):
        line=lines[i]
        if line.startswith('```'):
            code=not code;i+=1;continue
        if not line.strip():i+=1;continue
        if line.startswith('|'):
            rows=[]
            while i<len(lines) and lines[i].startswith('|'):rows.append(lines[i]);i+=1
            make_table(doc,rows);continue
        if line.startswith('# '):doc.add_paragraph(plain(line[2:]),style='Title')
        elif line.startswith('## '):
            heading=doc.add_paragraph(plain(line[3:]),style='Heading 1')
        elif line.startswith('!['):
            match=re.match(r'!\[([^\]]*)\]\(([^)]+)\)',line)
            image=(SOURCE.parent/match.group(2)).resolve()
            doc.add_picture(str(image),width=Inches(6.55))
            cap=doc.add_paragraph(match.group(1));cap.paragraph_format.space_after=Pt(8)
            for run in cap.runs:run.italic=True;run.font.size=Pt(9)
        else:
            p=doc.add_paragraph(plain(line[2:] if line.startswith('- ') else line),style='List Bullet' if line.startswith('- ') else None)
            if code:
                p.paragraph_format.space_after=Pt(1)
                p.paragraph_format.keep_with_next=True
                for run in p.runs:run.font.name='Courier New';run.font.size=Pt(8)
        i+=1
    footer=sec.footer.paragraphs[0];footer.alignment=2
    field=OxmlElement('w:fldSimple');field.set(qn('w:instr'),'PAGE');footer._p.append(field)
    doc.core_properties.title='Báo cáo Step 2 về bằng chứng thực nghiệm cho xây dựng danh mục'
    doc.core_properties.subject='Core Evidence Sprint';doc.core_properties.author='Nguyen Phuc Khang'
    doc.save(OUT/'Step2_Core_Evidence_Report.draft.docx')
    print(OUT/'Step2_Core_Evidence_Report.draft.docx')


if __name__=='__main__':main()
