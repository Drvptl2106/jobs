#!/usr/bin/env python3
"""Render a tailored CV (JSON) into a small, ATS-friendly Word .docx.

The .docx is written by hand (no template) so the file stays ~5-8 KB, which
keeps it cheap to attach to an email.

Usage:
    python scripts/make_cv.py path/to/cv.json path/to/output.docx

JSON shape (every key except "name" is optional):
{
  "name": "Dhruv Patil",
  "contact": ["London, UK", "email", "linkedin.com/in/... (optional)"],
  "headline": "Business & Data Analyst",
  "summary": "2-4 sentence profile tailored to the job",
  "skills": [{"label": "Analytics", "items": "SQL, Python, Power BI"}],
  "experience": [{"title": "", "org": "", "location": "", "dates": "", "bullets": [""]}],
  "projects":   [{"title": "", "org": "", "dates": "", "bullets": [""]}],
  "education":  [{"degree": "", "org": "", "location": "", "dates": "", "bullets": [""]}],
  "certifications": [""],
  "extras": [{"label": "Right to work", "text": "..."}]
}
"""
import json
import sys
import zipfile
from xml.sax.saxutils import escape

W = 'xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"'
FONT = "Calibri"
ACCENT = "1F3A5F"

CONTENT_TYPES = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
<Default Extension="xml" ContentType="application/xml"/>
<Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>
<Override PartName="/word/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.styles+xml"/>
<Override PartName="/word/numbering.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.numbering+xml"/>
<Override PartName="/docProps/core.xml" ContentType="application/vnd.openxmlformats-package.core-properties+xml"/>
</Types>"""

ROOT_RELS = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>
<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/package/2006/relationships/metadata/core-properties" Target="docProps/core.xml"/>
</Relationships>"""

DOC_RELS = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>
<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/numbering" Target="numbering.xml"/>
</Relationships>"""

STYLES = f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:styles {W}>
<w:docDefaults>
 <w:rPrDefault><w:rPr><w:rFonts w:ascii="{FONT}" w:hAnsi="{FONT}" w:cs="{FONT}" w:eastAsia="{FONT}"/><w:sz w:val="21"/><w:szCs w:val="21"/><w:lang w:val="en-GB"/></w:rPr></w:rPrDefault>
 <w:pPrDefault><w:pPr><w:spacing w:after="40" w:line="252" w:lineRule="auto"/></w:pPr></w:pPrDefault>
</w:docDefaults>
<w:style w:type="paragraph" w:default="1" w:styleId="Normal"><w:name w:val="Normal"/><w:qFormat/></w:style>
<w:style w:type="paragraph" w:styleId="Title"><w:name w:val="Title"/><w:basedOn w:val="Normal"/><w:qFormat/>
 <w:pPr><w:jc w:val="center"/><w:spacing w:after="20"/></w:pPr><w:rPr><w:b/><w:color w:val="{ACCENT}"/><w:sz w:val="36"/></w:rPr></w:style>
<w:style w:type="paragraph" w:styleId="Contact"><w:name w:val="Contact"/><w:basedOn w:val="Normal"/>
 <w:pPr><w:jc w:val="center"/><w:spacing w:after="60"/></w:pPr><w:rPr><w:color w:val="404040"/><w:sz w:val="19"/></w:rPr></w:style>
<w:style w:type="paragraph" w:styleId="Heading1"><w:name w:val="heading 1"/><w:basedOn w:val="Normal"/><w:next w:val="Normal"/><w:qFormat/>
 <w:pPr><w:keepNext/><w:spacing w:before="160" w:after="60"/><w:pBdr><w:bottom w:val="single" w:sz="6" w:space="1" w:color="{ACCENT}"/></w:pBdr><w:outlineLvl w:val="0"/></w:pPr>
 <w:rPr><w:b/><w:caps/><w:color w:val="{ACCENT}"/><w:sz w:val="22"/></w:rPr></w:style>
<w:style w:type="paragraph" w:styleId="RoleLine"><w:name w:val="Role Line"/><w:basedOn w:val="Normal"/>
 <w:pPr><w:keepNext/><w:tabs><w:tab w:val="right" w:pos="10466"/></w:tabs><w:spacing w:before="80" w:after="20"/></w:pPr></w:style>
<w:style w:type="paragraph" w:styleId="ListBullet"><w:name w:val="List Bullet"/><w:basedOn w:val="Normal"/>
 <w:pPr><w:numPr><w:ilvl w:val="0"/><w:numId w:val="1"/></w:numPr><w:spacing w:after="20"/></w:pPr></w:style>
</w:styles>"""

NUMBERING = f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:numbering {W}>
<w:abstractNum w:abstractNumId="0"><w:multiLevelType w:val="singleLevel"/>
 <w:lvl w:ilvl="0"><w:start w:val="1"/><w:numFmt w:val="bullet"/><w:lvlText w:val="•"/><w:lvlJc w:val="left"/>
  <w:pPr><w:ind w:left="284" w:hanging="227"/></w:pPr><w:rPr><w:rFonts w:ascii="{FONT}" w:hAnsi="{FONT}"/></w:rPr></w:lvl>
</w:abstractNum>
<w:num w:numId="1"><w:abstractNumId w:val="0"/></w:num>
</w:numbering>"""


def core(title):
    return f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties" xmlns:dc="http://purl.org/dc/elements/1.1/">
<dc:title>{escape(title)}</dc:title><dc:creator>{escape(title)}</dc:creator></cp:coreProperties>"""


def run(text, bold=False, italic=False, color=None):
    if not text:
        return ""
    props = ""
    if bold:
        props += "<w:b/>"
    if italic:
        props += "<w:i/>"
    if color:
        props += f'<w:color w:val="{color}"/>'
    rpr = f"<w:rPr>{props}</w:rPr>" if props else ""
    return f'<w:r>{rpr}<w:t xml:space="preserve">{escape(str(text))}</w:t></w:r>'


def para(runs, style=None):
    ppr = f'<w:pPr><w:pStyle w:val="{style}"/></w:pPr>' if style else ""
    return f"<w:p>{ppr}{runs}</w:p>"


def rich(text):
    """Allow **bold** fragments inside bullet text."""
    parts = str(text).split("**")
    return "".join(run(p, bold=(i % 2 == 1)) for i, p in enumerate(parts))


def entry(item, title_key="title", org_key="org"):
    out = []
    left = run(item.get(title_key, ""), bold=True)
    org = ", ".join(x for x in [item.get(org_key, ""), item.get("location", "")] if x)
    if org:
        left += run(" | " + org)
    dates = item.get("dates", "")
    right = ('<w:r><w:tab/></w:r>' + run(dates, italic=True, color="404040")) if dates else ""
    out.append(para(left + right, "RoleLine"))
    for b in item.get("bullets", []) or []:
        out.append(para(rich(b), "ListBullet"))
    return out


def build(cv):
    body = [para(run(cv["name"]), "Title")]
    if cv.get("headline"):
        body.append(para(run(cv["headline"], bold=True, color="404040"), "Contact"))
    if cv.get("contact"):
        body.append(para(run("  |  ".join(cv["contact"])), "Contact"))

    def section(title):
        body.append(para(run(title), "Heading1"))

    if cv.get("summary"):
        section("Profile")
        body.append(para(rich(cv["summary"])))
    if cv.get("skills"):
        section("Key Skills")
        for s in cv["skills"]:
            body.append(para(run(s.get("label", "") + ": ", bold=True) + run(s.get("items", "")), "ListBullet"))
    if cv.get("experience"):
        section("Professional Experience")
        for e in cv["experience"]:
            body.extend(entry(e))
    if cv.get("projects"):
        section("Projects")
        for p in cv["projects"]:
            body.extend(entry(p))
    if cv.get("education"):
        section("Education")
        for e in cv["education"]:
            body.extend(entry(e, "degree"))
    if cv.get("certifications"):
        section("Certifications")
        for c in cv["certifications"]:
            body.append(para(rich(c), "ListBullet"))
    for x in cv.get("extras", []) or []:
        section(x.get("label", "Additional"))
        body.append(para(rich(x.get("text", ""))))

    sect = ('<w:sectPr><w:pgSz w:w="11906" w:h="16838"/>'
            '<w:pgMar w:top="720" w:right="720" w:bottom="720" w:left="720" w:header="0" w:footer="0" w:gutter="0"/></w:sectPr>')
    return (f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
            f'<w:document {W}><w:body>{"".join(body)}{sect}</w:body></w:document>')


def write_docx(cv, path):
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml", CONTENT_TYPES)
        z.writestr("_rels/.rels", ROOT_RELS)
        z.writestr("word/_rels/document.xml.rels", DOC_RELS)
        z.writestr("word/document.xml", build(cv))
        z.writestr("word/styles.xml", STYLES)
        z.writestr("word/numbering.xml", NUMBERING)
        z.writestr("docProps/core.xml", core(cv["name"] + " - CV"))


if __name__ == "__main__":
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    with open(sys.argv[1], encoding="utf-8") as f:
        data = json.load(f)
    write_docx(data, sys.argv[2])
    print(sys.argv[2])
