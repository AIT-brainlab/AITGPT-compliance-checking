# คู่มือโครงการ PolicyChecker — อธิบาย Source Code ทีละขั้นตอน

> **สำหรับนักศึกษาฝึกงาน** — เอกสารนี้จะพาคุณเดินทางตั้งแต่ต้นจนจบว่าโปรแกรม PolicyChecker ทำงานอย่างไร เขียนโดยใครก็ตามที่ต้องการส่งต่องานนี้ให้ผู้อื่น

---

## สารบัญ

1. [ภาพรวมโครงการ — PolicyChecker คืออะไร?](#1-ภาพรวมโครงการ)
2. [แผนภาพ Pipeline — ดูภาพรวมก่อน](#2-แผนภาพ-pipeline)
3. [การติดตั้งและเตรียมระบบ](#3-การติดตั้งและเตรียมระบบ)
4. [โครงสร้างโฟลเดอร์ทั้งหมด](#4-โครงสร้างโฟลเดอร์ทั้งหมด)
5. [วิธีรันโปรแกรม](#5-วิธีรันโปรแกรม)
6. [อธิบาย 9 ขั้นตอนของ Pipeline อย่างละเอียด](#6-อธิบาย-9-ขั้นตอนของ-pipeline-อย่างละเอียด)
   - [ขั้นที่ 1 — Extract: ดึงประโยคออกจาก PDF](#61-ขั้นที่-1--extract)
   - [ขั้นที่ 2 — Prefilter: กรองเบื้องต้น](#62-ขั้นที่-2--prefilter)
   - [ขั้นที่ 3 — Classify: จำแนกประเภทกฎ](#63-ขั้นที่-3--classify)
   - [ขั้นที่ 4 — Reclassify: จำแนกซ้ำด้วย LLM ตัวที่สอง](#64-ขั้นที่-4--reclassify)
   - [ขั้นที่ 5 — FOL: แปลงกฎเป็น First-Order Logic](#65-ขั้นที่-5--fol)
   - [ขั้นที่ 6 — SHACL: สร้าง SHACL Shape จาก FOL](#66-ขั้นที่-6--shacl)
   - [ขั้นที่ 7 — Direct SHACL: Fallback สร้าง SHACL โดยตรง](#67-ขั้นที่-7--direct-shacl)
   - [ขั้นที่ 8 — Validate: ตรวจสอบความถูกต้อง](#68-ขั้นที่-8--validate)
   - [ขั้นที่ 9 — Report: สร้างรายงานสรุป](#69-ขั้นที่-9--report)
7. [โครงสร้างพื้นฐานสนับสนุน (Infrastructure)](#7-โครงสร้างพื้นฐานสนับสนุน)
   - [State — ข้อมูลที่ไหลผ่าน Pipeline](#71-state--pipelinestate)
   - [Graph — แผนที่การเชื่อมต่อ Node](#72-graph--buildgraph)
   - [Routing — การตัดสินใจเลือกเส้นทาง](#73-routing--routeclassify)
   - [LLM — การเรียกใช้ภาษาโมเดล](#74-llm--getllm)
   - [LLM Cache — ประหยัดเวลาด้วยการแคช](#75-llm-cache)
   - [Corpus Config — การตั้งค่าแต่ละสถาบัน](#76-corpus-config)
8. [Web Dashboard](#8-web-dashboard)
9. [Ablation Studies — การทดสอบส่วนประกอบ](#9-ablation-studies)
10. [ฐานข้อมูล PostgreSQL และ Seeder](#10-ฐานข้อมูล-postgresql-และ-seeder)
11. [ไฟล์ Output ที่โปรแกรมสร้างขึ้น](#11-ไฟล์-output-ที่โปรแกรมสร้างขึ้น)
12. [Evaluation Harness — ใช้งานอย่างไร](#12-evaluation-harness--ใช้งานอย่างไร)
13. [คำศัพท์สำคัญ (Glossary)](#13-คำศัพท์สำคัญ)
14. [คำถาม-คำตอบที่พบบ่อย](#14-คำถามคำตอบที่พบบ่อย)

---

## 1. ภาพรวมโครงการ

### PolicyChecker คืออะไร?

PolicyChecker คือระบบ AI ที่ **อ่านเอกสารนโยบายสถาบัน** (ในรูปแบบ PDF) แล้ว **แปลงกฎข้อบังคับที่เขียนเป็นภาษาธรรมชาติ** ให้กลายเป็น **SHACL Shapes** (โครงสร้างข้อมูลที่เครื่องคอมพิวเตอร์อ่านได้) จากนั้นใช้ SHACL Shapes เหล่านั้นตรวจสอบว่าข้อมูลสถาบัน (RDF graph) สอดคล้องกับนโยบายหรือไม่

นี่คือวิทยานิพนธ์ระดับปริญญาโทปี 2026 ที่ AIT (Asian Institute of Technology)

### ตัวอย่างง่าย ๆ เพื่อให้เข้าใจภาพรวม

**ข้อความในเอกสาร PDF:**
> "Students must pay tuition fees before the semester begins."

**โปรแกรมจะแปลงเป็น:**

**ขั้น 1 — FOL (First-Order Logic):**
```
∀x (Student(x) → O(payFees(x)))
```
อ่านว่า: "สำหรับทุก x ถ้า x เป็นนักศึกษา แล้ว x มีหน้าที่ (Obligation) จ่ายค่าธรรมเนียม"

**ขั้น 2 — SHACL Shape (Turtle syntax):**
```turtle
ait:PayFeesShape a sh:NodeShape ;
    sh:targetClass ait:Student ;
    sh:property [
        sh:path ait:payFees ;
        sh:minCount 1 ;
        sh:name "payFees" ;
    ] .
```

**ขั้น 3 — ผลการตรวจสอบ:**
```
VIOLATION: Student ส.001 ไม่มีค่า ait:payFees → ละเมิดนโยบาย
```

ทั้งหมดนี้เกิดขึ้นโดยอัตโนมัติ โดยไม่ต้องเขียน SHACL ด้วยมือ

---

## 2. แผนภาพ Pipeline

```
PDF Files
    │
    ▼
┌─────────┐
│  EXTRACT │  ← อ่าน PDF แล้วแยกเป็นรายประโยค
└────┬────┘
     │
     ▼
┌───────────┐
│ PREFILTER │  ← กรองประโยคที่ไม่ใช่กฎออก (ลด noise)
└─────┬─────┘
      │
      ▼
┌──────────┐
│ CLASSIFY │  ← ถามว่าแต่ละประโยคเป็น "กฎ" จริงไหม
└─────┬────┘
      │
      ├─── [มีประโยคที่ไม่แน่ใจ] ──►┌────────────┐
      │                               │ RECLASSIFY │ ← ถามด้วย LLM ที่สองเพื่อยืนยัน
      │                               └─────┬──────┘
      │◄──────────────────────────────────┘
      │ [ไม่มีประโยคที่ไม่แน่ใจ]
      │ [มีแต่กฎที่ชัดเจน]
      ▼
┌─────┐
│ FOL │  ← แปลงกฎเป็นสูตร First-Order Logic
└──┬──┘
   │
   ├──────────────────┬─────────────────────────────┐
   ▼                  ▼                             
┌───────┐     ┌──────────────┐
│ SHACL │     │ DIRECT_SHACL │ ← ทั้งสองทำงานพร้อมกัน (parallel)
│ (FOL  │     │ (Fallback    │   SHACL: ใช้กฎที่ FOL สำเร็จ
│ ✓)    │     │  NL → SHACL) │   Direct: ใช้กฎที่ FOL ล้มเหลว
└───┬───┘     └──────┬───────┘
    │                │
    └────────┬───────┘
             ▼
        ┌──────────┐
        │ VALIDATE │  ← รัน pyshacl ตรวจสอบ
        └─────┬────┘
              ▼
         ┌────────┐
         │ REPORT │  ← สร้างรายงานสรุป
         └────────┘
```

**สิ่งที่ต้องเข้าใจในแผนภาพนี้:**
- **ทุก Node รับและส่ง `PipelineState`** — เหมือน "กระเป๋า" ที่ส่งต่อกันตลอด Pipeline
- **FOL → SHACL และ FOL → DIRECT_SHACL** เป็น Parallel Fan-out ทั้งสองทำงานพร้อมกัน
- **CLASSIFY มี Conditional Edge** — แยกเส้นทางตามความมั่นใจ

---

## 3. การติดตั้งและเตรียมระบบ

### สิ่งที่ต้องมีก่อนเริ่ม

| สิ่งที่ต้องการ | เวอร์ชันขั้นต่ำ | หมายเหตุ |
|---|---|---|
| Python | 3.11+ | ใช้ `python --version` เพื่อตรวจสอบ |
| Ollama | ล่าสุด | ดาวน์โหลดจาก https://ollama.com |
| Mistral 7B | ผ่าน Ollama | ดู command ด้านล่าง |
| pip packages | — | ดู requirements.txt |

### ขั้นตอนการติดตั้ง

**ขั้นที่ 1: ดาวน์โหลดโมเดล Mistral ลงในเครื่อง**
```bash
ollama pull mistral
```
คำสั่งนี้จะดาวน์โหลด Mistral 7B (~4GB) ลงเก็บในเครื่อง การรัน LLM ทั้งหมดเป็น **local** ไม่ส่งข้อมูลออกอินเทอร์เน็ต

**ขั้นที่ 2: สร้าง Virtual Environment**
```bash
cd Automatate_Compliance_Checking-v2
python -m venv .venv
.venv\Scripts\activate      # Windows
# source .venv/bin/activate  # macOS/Linux
```

**ขั้นที่ 3: ติดตั้ง Python packages**
```bash
pip install -r requirements.txt
```

**ขั้นที่ 4: ตรวจสอบว่า Ollama ทำงานอยู่**
```bash
ollama serve
# หรือตรวจสอบด้วย:
curl http://localhost:11434/api/tags
```

---

## 4. โครงสร้างโฟลเดอร์ทั้งหมด

```
Automatate_Compliance_Checking-v2/
│
├── config/                         # ตั้งค่า corpus
│   └── ait.yaml                    # ตั้งค่าสำหรับ AIT โดยเฉพาะ
│
├── core/                           # Logic หลักที่ไม่ผูกกับ LangGraph
│   ├── prefilter.py                # ตัวกรอง heuristic
│   └── llm_cache.py               # SQLite cache สำหรับ LLM
│
├── institutional_policy/
│   └── AIT/                        # PDF ต้นฉบับของ AIT
│
├── langgraph_agent/               # โค้ดหลักทั้งหมด
│   ├── run.py                     # จุดเริ่มต้น (CLI entry point)
│   ├── graph.py                   # สร้าง LangGraph StateGraph
│   ├── state.py                   # นิยาม PipelineState
│   ├── llm.py                     # สร้าง LLM instances
│   ├── corpus_config.py           # โหลด YAML config
│   │
│   ├── nodes/                     # แต่ละ node ใน Pipeline
│   │   ├── extract.py             # ขั้น 1: ดึงข้อความจาก PDF
│   │   ├── prefilter.py           # ขั้น 2: กรองประโยค
│   │   ├── classify.py            # ขั้น 3: จำแนกกฎ
│   │   ├── reclassify.py          # ขั้น 4: จำแนกซ้ำ
│   │   ├── fol.py                 # ขั้น 5: แปลงเป็น FOL
│   │   ├── shacl.py               # ขั้น 6: สร้าง SHACL จาก FOL
│   │   ├── direct_shacl.py        # ขั้น 7: Fallback SHACL
│   │   ├── validate.py            # ขั้น 8: ตรวจสอบ SHACL
│   │   └── report.py              # ขั้น 9: สรุปผล
│   │
│   └── edges/
│       └── route_classify.py      # ตัดสินใจเส้นทางหลัง classify
│
├── shacl/
│   ├── ontology/
│   │   ├── ait_policy_ontology.ttl # OWL ontology หลัก
│   │   └── property_list.txt      # คำศัพท์ property ที่อนุญาต
│   ├── shapes/
│   │   └── ait_policy_shapes.ttl  # Gold shapes (มือเขียน)
│   └── test_data/
│       └── tdd_test_data_fixed.ttl # ข้อมูลทดสอบ RDF
│
├── output/
│   └── ait/                       # ผลลัพธ์ทั้งหมด
│       ├── classified_rules.json
│       ├── fol_formulas.json
│       ├── shapes_generated.ttl
│       ├── validation_results.json
│       └── pipeline_report.json
│
├── web/
│   ├── app.py                     # FastAPI backend
│   └── frontend/                  # Vite + React frontend
│
└── cache/
    └── llm_cache.db               # SQLite cache
```

---

## 5. วิธีรันโปรแกรม

### การรันพื้นฐาน

```bash
python -m langgraph_agent.run --source ait
```

**อธิบาย argument:**
- `--source ait` — ชื่อ key ของ corpus ที่นิยามไว้ใน `langgraph_agent/run.py`  
  (ระบบจะโหลด config จาก `config/ait.yaml` และ PDF จาก `institutional_policy/AIT/` อัตโนมัติ)

### ดู Log แบบละเอียด

```bash
python -m langgraph_agent.run --source ait --verbose
```

### รัน Ablation Study (ทดสอบโดยปิดบางส่วน)

```bash
# ปิด Prefilter เพื่อดูว่าสำคัญแค่ไหน
python -m langgraph_agent.run --source ait --ablation no-prefilter

# ดู ablation อื่น ๆ ที่มีได้ในหัวข้อ 9 ด้านล่าง
```

### รัน Web Dashboard

```bash
# เปิด backend
uvicorn web.app:app --reload

# เปิด frontend (ใน terminal ใหม่)
cd web/frontend
npm install
npm run dev
```
จากนั้นเปิดเบราว์เซอร์ที่ `http://localhost:5173`

---

## 6. อธิบาย 9 ขั้นตอนของ Pipeline อย่างละเอียด

> **หมายเหตุสำคัญ:** ทุก node ใน Pipeline รับ `PipelineState` เป็น input และ return `dict` (ที่จะถูก merge เข้า state) เป็น output นี่คือ pattern หลักของ LangGraph

---

### 6.1 ขั้นที่ 1 — Extract

**ไฟล์:** `langgraph_agent/nodes/extract.py`

**หน้าที่:** อ่านไฟล์ PDF ทั้งหมดในโฟลเดอร์ แล้วแยกออกเป็นรายประโยค

#### สิ่งที่ node นี้ทำทีละขั้น:

**1. รับ path ของโฟลเดอร์ PDF จาก state**
```python
source_dir = state["source_dir"]
```

**2. หา PDF ทุกไฟล์ในโฟลเดอร์**
```python
pdf_files = list(Path(source_dir).glob("*.pdf"))
```

**3. อ่านแต่ละ PDF ด้วย `pdfplumber`**

`pdfplumber` เป็น library ที่ดีกว่า `PyPDF2` ตรงที่จัดการ layout ซับซ้อนได้ดีกว่า โค้ดจะวนลูปแต่ละหน้า แล้วดึงข้อความออกมา

**4. แยกข้อความเป็นประโยค**

ใช้ `nltk.sent_tokenize()` หรือ regex เพื่อแบ่งข้อความเป็นประโยคย่อย

**5. เก็บผลลัพธ์ในรูปแบบ dict**

แต่ละประโยคจะถูกเก็บเป็น `dict` แบบนี้:
```python
{
    "text": "Students must pay fees before registration.",
    "source": "AIT_Student_Handbook.pdf",
    "page": 12
}
```

**6. ส่งกลับเข้า state**
```python
return {"sentences": [
    {"text": "...", "source": "...", "page": 1},
    ...
]}
```

#### ตัวอย่างผลลัพธ์:

input: 3 PDF files, รวม ~200 หน้า
output: `sentences` มีประโยคประมาณ 5,000-10,000 รายการ

---

### 6.2 ขั้นที่ 2 — Prefilter

**ไฟล์:** `langgraph_agent/nodes/prefilter.py` (wrapper) และ `core/prefilter.py` (logic จริง)

**หน้าที่:** ลดจำนวนประโยคก่อนส่งให้ LLM โดยกรองประโยคที่แน่นอนว่าไม่ใช่กฎออก เพื่อประหยัดเวลาและค่าใช้จ่าย

#### ทำไมต้องมี Prefilter?

ถ้าส่งประโยคทุกประโยคให้ LLM ตรวจสอบ จะใช้เวลานานมาก (ประมาณ 10,000 ประโยค × 1 วินาที = ~3 ชั่วโมง) Prefilter ลดปริมาณลงเหลือแค่ประโยคที่ "น่าจะเป็นกฎ" เท่านั้น (~10-20%)

#### วิธีทำงานของ Heuristic Filter:

**ขั้นที่ 1: ตรวจหา Deontic Markers**

`core/prefilter.py` มี list ของ "คำบ่งชี้กฎ" ที่เรียกว่า `STRONG_DEONTIC_MARKERS`:
```python
STRONG_DEONTIC_MARKERS = {
    "must", "shall", "is required", "is required to",
    "is prohibited", "is not permitted", "may not",
    "is obligated", "must not", ...
}
```
ประโยคที่มีคำเหล่านี้จะได้ **คะแนนสูง** — น่าจะเป็นกฎ

**ขั้นที่ 2: ให้น้ำหนักตาม Section**

`SECTION_WEIGHTS` กำหนดว่า section ไหนน่าจะมีกฎมากกว่า:
```python
SECTION_WEIGHTS = {
    "regulations": 1.3,     # section นี้มีกฎเยอะ → น้ำหนักสูง
    "requirements": 1.2,
    "prohibited": 1.3,
    "introduction": 0.4,    # แค่อธิบาย → น้ำหนักต่ำ
    "glossary": 0.2,        # นิยามคำ ไม่ใช่กฎ
    "table of contents": 0.1,
}
```

**ขั้นที่ 3: May Disambiguation (แยกแยะ "may" สองความหมาย)**

คำว่า "may" มี 2 ความหมาย:
- **Epistemic "may"** = ความเป็นไปได้ เช่น "Fees may vary" → ไม่ใช่กฎ
- **Deontic "may"** = อนุญาต เช่น "Students may appeal" → เป็นกฎ

Prefilter ดูบริบทรอบข้างเพื่อแยก:
```python
# Pattern ที่บ่งชี้ Epistemic "may":
epistemic_patterns = [
    r"may (also|not|be|have|include|result)",
    r"(fees|prices|costs) may",
]
```

**ขั้นที่ 4: คำนวณ confidence score และตัดสินใจ**

แต่ละประโยคจะได้ `confidence_score` ระหว่าง 0-1:
- ≥ 0.5 → ผ่าน (ส่งต่อให้ classify)
- < 0.5 → กรองออก

**ขั้นที่ 5: Fail-safe**

หากเกิด exception ใด ๆ ใน prefilter, node นี้จะ **ส่งประโยคทุกตัวผ่าน** โดยไม่กรอง เพื่อไม่ให้ระบบพัง

#### ข้อมูลที่เพิ่มเข้าไปในแต่ละประโยค:

หลังผ่าน prefilter ประโยคแต่ละอันจะมีข้อมูลเพิ่ม:
```python
{
    "text": "Students must register by the deadline.",
    "source": "handbook.pdf",
    "page": 5,
    "deontic_strength": 0.9,       # ความแรงของ deontic marker
    "speech_act": "directive",      # ประเภท speech act
    "section_context": "registration requirements",
    "section_weight": 1.2,
    "confidence_boost": 0.1
}
```

#### Ablation Flag:
```bash
ABLATION_SKIP_PREFILTER=1  # ปิด prefilter → ส่งทุกประโยคให้ classify
```

---

### 6.3 ขั้นที่ 3 — Classify

**ไฟล์:** `langgraph_agent/nodes/classify.py`

**หน้าที่:** ถามว่าแต่ละประโยคเป็น "กฎข้อบังคับ" (policy rule) จริงหรือไม่ โดยใช้ LLM

#### วิธีทำงาน:

**ขั้นที่ 1: สร้าง Prompt**

Node นี้สร้าง prompt ที่บอก LLM ว่า:
> "ต่อไปนี้เป็นประโยคจากเอกสารนโยบายสถาบัน โปรดบอกว่าประโยคนี้เป็นกฎข้อบังคับหรือไม่ และถ้าใช่ เป็นประเภทไหน (obligation/permission/prohibition) ตอบใน JSON"

**ขั้นที่ 2: ส่งให้ LLM**

ใช้ `get_llm()` จาก `langgraph_agent/llm.py` ซึ่งคือ Mistral 7B รันบนเครื่องผ่าน Ollama

LLM ส่งกลับ JSON แบบนี้:
```json
{
    "is_rule": true,
    "deontic_type": "obligation",
    "confidence": 0.85,
    "subject": "student",
    "action": "register"
}
```

**ขั้นที่ 3: แยกตาม Confidence Threshold**

โปรแกรมใช้ threshold 2 ระดับ:
```python
HIGH_THRESHOLD = 0.6   # confident rule
LOW_THRESHOLD  = 0.4   # uncertain rule
```

- `confidence ≥ 0.6` → เพิ่มใน `state["rules"]` (กฎที่มั่นใจ)
- `0.4 ≤ confidence < 0.6` → เพิ่มใน `state["uncertain_rules"]` (ส่งให้ reclassify)
- `confidence < 0.4` หรือ `is_rule = false` → ทิ้ง

**ขั้นที่ 4: ตรวจสอบ LLM Cache**

ก่อนส่ง prompt ให้ LLM จริง ๆ โปรแกรมจะตรวจสอบ cache ก่อนเสมอ:
```python
cache_key = sha256(prompt + model + params)
cached_response = cache.get(cache_key)
if cached_response:
    return cached_response  # ไม่ต้องรัน LLM
```
ทำให้ run ซ้ำได้เร็วมากหากข้อมูลไม่เปลี่ยน

#### ตัวอย่างประโยคและผลการจำแนก:

| ประโยค | ผล | เหตุผล |
|--------|-----|--------|
| "Students must pay fees by Day 1." | rule (obligation, 0.92) | มี "must" ชัดเจน |
| "Fees are subject to change." | not rule (0.22) | เป็น statement ไม่ใช่ directive |
| "Students may request a deferral." | uncertain (0.55) | "may" ไม่ชัดว่าอนุญาตหรือบอกความเป็นไปได้ |

---

### 6.4 ขั้นที่ 4 — Reclassify

**ไฟล์:** `langgraph_agent/nodes/reclassify.py`

**หน้าที่:** ตรวจสอบซ้ำประโยคที่อยู่ใน `uncertain_rules` โดยใช้ LLM ตัวที่สอง (seed ต่างกัน)

#### ทำไมต้องใช้ LLM ตัวที่สอง?

เพื่อให้ได้ "second opinion" ที่เป็นอิสระจริง ๆ (independent) ถ้าใช้ LLM ตัวเดิมกับ seed เดิม จะได้คำตอบเดิมเสมอ

```python
# llm.py
def get_second_llm() -> ChatOllama:
    return get_llm(model=SECOND_MODEL, seed=SEED + 1)  # seed=43 ต่างจาก primary seed=42
```

#### Prompt ที่แตกต่าง:

Reclassify ใช้ prompt ที่ **directive มากกว่า** โดยระบุเกณฑ์ชัดเจน:

> "ต่อไปนี้เป็นกฎที่ยังไม่แน่ใจว่าเป็นกฎข้อบังคับหรือไม่ กฎข้อบังคับต้องมีลักษณะ:
> 1. มี deontic verb: must, shall, may, is required, is prohibited
> 2. มี subject ที่ชัดเจน: student, faculty, staff
> 3. กำหนดพฤติกรรมที่ต้องทำหรือห้ามทำ"

#### ผลลัพธ์ของ Reclassify:

- ถ้ายืนยันว่าเป็นกฎ → ย้ายเข้า `state["rules"]`
- ถ้ายืนยันว่าไม่ใช่กฎ → ทิ้ง
- `state["uncertain_rules"]` จะถูก clear ให้เป็น `[]` หลังจากนี้

#### Ablation Flag:
```bash
ABLATION_SKIP_RECLASSIFY=1  # ปิด reclassify → ทิ้ง uncertain_rules ทั้งหมด
```

---

### 6.5 ขั้นที่ 5 — FOL

**ไฟล์:** `langgraph_agent/nodes/fol.py`

**หน้าที่:** แปลงกฎข้อบังคับแต่ละข้อให้เป็นสูตร First-Order Logic (FOL)

#### FOL คืออะไร?

First-Order Logic เป็นภาษา formal สำหรับแสดงความสัมพันธ์เชิงตรรกะ ในที่นี้ใช้ระบบ deontic logic ที่มี operator 3 ตัว:

| Operator | ความหมาย | ตัวอย่าง |
|----------|----------|---------|
| `O(φ)` | Obligation — หน้าที่/ต้อง | `O(payFees(student))` |
| `P(φ)` | Permission — อนุญาต/อาจ | `P(requestExtension(student))` |
| `F(φ)` | Forbidden — ห้าม/ต้องไม่ | `F(keepPets(resident))` |

#### Prompt ที่ใช้:

FOL node สร้าง prompt ที่บอก LLM ว่า:
> "แปลงกฎต่อไปนี้เป็น FOL formula ในรูปแบบ deontic logic ตอบเป็น JSON"

พร้อมกับแนบ **ตัวอย่างจาก corpus config** (`ait.yaml`):
```yaml
fol_examples:
  - text: "Students must submit their thesis by the deadline."
    deontic_type: "obligation"
    formula: "O(submittitlepage(student))"
    expansion: "∀x (Student(x) → O(submittitlepage(x)))"
    action: "submittitlepage"
```

ตัวอย่างเหล่านี้เป็น **few-shot examples** ที่ช่วยให้ LLM เข้าใจ format ที่ต้องการ

#### LLM ส่งกลับ JSON แบบนี้:

```json
{
    "deontic_type": "obligation",
    "deontic_formula": "O(payFees(student))",
    "fol_expansion": "∀x (Student(x) → O(payFees(x)))",
    "predicates": {
        "subject": "student",
        "action": "payFees",
        "condition": "before registration"
    },
    "shacl_hint": "payFees property"
}
```

#### การใช้ Vocabulary Hint:

Node นี้ยังใช้ `cfg.vocabulary_hint()` เพื่อบอก LLM ว่า property ชื่ออะไรที่มีอยู่แล้ว:
```python
vocab = "payFees, submitThesis, attendClass, requestExtension, ..."
prompt += f"\nUse existing predicates where possible: {vocab}"
```
ป้องกันไม่ให้ LLM สร้างชื่อ property ใหม่ที่ไม่สอดคล้องกัน

#### การ Retry:

ถ้า LLM ตอบกลับมาไม่ถูก format (parse JSON ไม่ได้) โปรแกรมจะ **retry สูงสุด 3 ครั้ง**

ถ้า retry ครบแล้วยังไม่สำเร็จ → ประโยคนั้นจะถูกเพิ่มใน `state["fol_failed"]` เพื่อส่งให้ `direct_shacl` node

#### Ablation Flag:
```bash
ABLATION_NO_FOL_RETRY=1  # ไม่ retry → ถ้าล้มเหลวครั้งแรกให้เก็บไว้ใน fol_failed เลย
```

---

### 6.6 ขั้นที่ 6 — SHACL

**ไฟล์:** `langgraph_agent/nodes/shacl.py`

**หน้าที่:** แปลง FOL formula ที่สำเร็จแล้วให้เป็น SHACL Shape (Turtle syntax)

#### SHACL คืออะไร?

SHACL (Shapes Constraint Language) คือ W3C standard สำหรับ **กำหนดข้อกำหนดของ RDF data** คิดว่ามันเป็นเหมือน "schema validation" สำหรับ RDF graph

SHACL Shape ประกอบด้วย 2 ส่วนหลัก:

```turtle
# NodeShape: บอกว่าตรวจสอบ class ไหน
ait:PayFeesShape a sh:NodeShape ;
    sh:targetClass ait:Student ;       # ← ตรวจกับ instance ของ Student ทุกตัว
    sh:property [                      # ← PropertyShape ใน []
        sh:path ait:payFees ;          # ← ต้องมี property payFees
        sh:minCount 1 ;                # ← อย่างน้อย 1 ค่า
        sh:name "payFees" ;
        sh:description "Students must pay fees" ;
    ] .
```

#### วิธีที่ SHACL node ทำงาน:

**ขั้นที่ 1: สร้าง Prompt จาก FOL**

Node นี้รับ FOL formula แล้วสร้าง prompt:
> "จาก FOL formula นี้: `O(payFees(student))` สร้าง SHACL Shape ในรูปแบบ Turtle โดยใช้ namespace `ait:` ตอบแค่โค้ด Turtle เท่านั้น"

**ขั้นที่ 2: ระบุ Target Class ด้วย Corpus Config**

ใช้ `cfg.target_class_for(rule_text)` เพื่อดูว่า subject ในกฎคือ class อะไร:
```python
# จาก ait.yaml
target_class_patterns:
  - pattern: "student(s?)"
    class: "Student"
  - pattern: "faculty|instructor"
    class: "Faculty"
```

**ขั้นที่ 3: Parse และ Validate Turtle**

ใช้ `rdflib.Graph().parse(data=turtle_text, format="turtle")` เพื่อตรวจว่า Turtle syntax ถูกต้อง ถ้าผิด → retry

**ขั้นที่ 4: เพิ่ม Metadata**

Shape ที่ generate ได้จะถูก tag ด้วย:
```turtle
ait:PayFeesShape ait:generationMethod "fol_pipeline" ;
                 ait:sourceRule "Students must pay fees..." ;
                 ait:deonticType "obligation" .
```

**ขั้นที่ 5: เพิ่มใน state**

```python
return {"generated_shapes": existing_shapes + new_shape_turtle}
```

---

### 6.7 ขั้นที่ 7 — Direct SHACL

**ไฟล์:** `langgraph_agent/nodes/direct_shacl.py`

**หน้าที่:** สำหรับกฎที่ FOL node ล้มเหลว — แปลงจาก Natural Language เป็น SHACL โดยตรง (ไม่ผ่าน FOL)

#### ทำไมต้องมี Fallback นี้?

บาง rule ซับซ้อนเกินไปจนแปลงเป็น FOL formula ไม่ได้ เช่น rule ที่มีเงื่อนไขหลายชั้น Fallback นี้ใช้ LLM แปลง NL → SHACL โดยตรง

#### Prompt ที่ใช้ (`_DIRECT_PROMPT`):

```python
_DIRECT_PROMPT = """
You are a SHACL expert. Convert this policy rule directly to a SHACL NodeShape
in Turtle syntax. Use namespace prefix: {prefix}:

Rule: "{rule_text}"
Target class: {target_class}
Available properties: {vocabulary}

Output ONLY valid Turtle code. Do not explain.
"""
```

#### การซ่อมแซม Turtle (`_repair_turtle()`):

ถ้า LLM สร้าง Turtle ที่ syntax ผิด โปรแกรมจะพยายามซ่อมสูงสุด 2 รอบ:

**รอบที่ 1:** บอก LLM ว่าผิดตรงไหน แล้วขอให้แก้
```python
repair_prompt = f"The following Turtle is invalid:\n{broken_turtle}\nError: {error}\nFix it:"
```

**รอบที่ 2:** ถ้ายังไม่ได้ → ทิ้ง

#### `_strip_fences()`:

LLM มักใส่ markdown code fences เข้ามา:
````
```turtle
ait:Shape a sh:NodeShape .
```
````
ฟังก์ชันนี้ตัดออก เพื่อให้ได้แค่ Turtle บริสุทธิ์

#### Tag ที่ต่างจาก SHACL node:

Shape จาก direct_shacl จะถูก tag ว่า:
```turtle
ait:SomeShape ait:generationMethod "direct_nl" .
```
เพื่อให้ทราบว่ามาจาก fallback ไม่ผ่าน FOL

#### Ablation Flag:
```bash
ABLATION_SKIP_DIRECT_SHACL=1  # ปิด fallback → กฎที่ FOL ล้มเหลวจะหายไปเลย
```

---

### 6.8 ขั้นที่ 8 — Validate

**ไฟล์:** `langgraph_agent/nodes/validate.py`

**หน้าที่:** รัน SHACL validation จริง ๆ — ตรวจสอบว่า test data สอดคล้องกับ shapes หรือไม่

#### ขั้นตอนละเอียด:

**ขั้นที่ 1: โหลด Shapes ทั้งหมด**

โปรแกรมรวม shapes 2 แหล่ง:
1. **Gold shapes** — เขียนด้วยมือโดยผู้เชี่ยวชาญ (จาก `shacl/shapes/ait_policy_shapes.ttl`)
2. **Generated shapes** — สร้างโดย pipeline (จาก `state["generated_shapes"]`)

```python
all_shapes_graph = gold_shapes_graph + generated_shapes_graph
```

**ขั้นที่ 2: Pre-sanitize Shapes Graph**

ก่อน validate จริง โปรแกรมจะซ่อมแซม shapes ที่อาจมีปัญหา:

- **ลบ duplicate `sh:path`**: บน BNode เดียวกัน ถ้ามี `sh:path` มากกว่า 1 ตัว pyshacl จะ error → ลบซ้ำออก
- **แปลง `sh:maxCount`/`sh:minCount`**: ต้องเป็น `xsd:integer` ไม่ใช่ literal ธรรมดา

**ขั้นที่ 3: โหลด Test Data**

Test data คือ RDF entities จำลอง (เขียนด้วยมือ) อยู่ใน `shacl/test_data/tdd_test_data_fixed.ttl`:
```turtle
ait:student001 a ait:Student ;
    ait:studentId "S001" ;
    ait:enrolledIn ait:course001 .
# ← ไม่มี ait:payFees → จะ violate PayFeesShape!
```

**ขั้นที่ 4: รัน `pyshacl.validate()`**

```python
conforms, results_graph, results_text = pyshacl.validate(
    data_graph=test_data,
    shacl_graph=all_shapes,
    inference="rdfs",       # ใช้ RDFS reasoning ด้วย
    abort_on_first=False,   # ตรวจทั้งหมด ไม่หยุดที่ violation แรก
)
```

**ขั้นที่ 5: Parse Violations**

`results_graph` เป็น RDF graph ที่มีข้อมูล violation แต่ละ violation มี:
```
sh:resultSeverity sh:Violation
sh:focusNode ait:student001
sh:resultPath ait:payFees
sh:sourceShape ait:PayFeesShape
sh:resultMessage "Student must pay fees (minCount=1 violation)"
```

โปรแกรม parse ข้อมูลเหล่านี้แล้วแปลงเป็น Python dict

**ขั้นที่ 6: Resolve BNode PropertyShapes**

บาง shape ใช้ anonymous BNode สำหรับ PropertyShape:
```turtle
ait:SomeShape sh:property [ sh:path ait:foo ] .
#                         ↑ BNode ไม่มีชื่อ
```

ถ้า violation ชี้ไปที่ BNode โปรแกรมจะ **trace back** เพื่อหา parent NodeShape ที่มีชื่อ

**ขั้นที่ 7: บันทึกผล**

บันทึก violations ลงไฟล์ JSON (cap ที่ 50 violations เพื่อไม่ให้ไฟล์ใหญ่เกินไป)

---

### 6.9 ขั้นที่ 9 — Report

**ไฟล์:** `langgraph_agent/nodes/report.py`

**หน้าที่:** สร้างรายงานสรุปรวมสถิติทั้งหมดของการรัน pipeline

#### รายงานประกอบด้วย:

**1. สถิติ Pipeline:**
```json
{
    "total_sentences": 8432,
    "after_prefilter": 743,
    "rules_confident": 391,
    "rules_uncertain": 63,
    "rules_reclassified": 41,
    "fol_success": 390,
    "fol_failed": 1,
    "shapes_generated": 391,
    "shapes_direct": 1,
    "violations": 7,
    "shapes_conforming": 384
}
```

**2. Violation Triage (`_build_violation_triage()`):**

ฟังก์ชันนี้วิเคราะห์ว่า violation ไหน **น่าเชื่อถือ** และไหน **น่าจะเป็น False Positive**:

```python
FALSE_POSITIVE_THRESHOLD = 0.80  # ถ้า shape ยิง violation บน >80% ของ test entities

for shape_name, violations in violations_by_shape.items():
    hit_ratio = len(violations) / total_test_entities
    if hit_ratio > FALSE_POSITIVE_THRESHOLD:
        shape.flag = "LIKELY_FALSE_POSITIVE"
    else:
        shape.flag = "GENUINE_VIOLATION"
```

**ตรรกะ:** ถ้า shape ที่บอกว่า "Student ต้องมี payFees" ยิง violation บนนักศึกษา 95% ของ test data แสดงว่า shape นั้นอาจเขียนผิด ไม่ใช่นักศึกษาทุกคนละเมิด

**3. Environment Capture (`_capture_environment()`):**

บันทึก metadata เพื่อ reproducibility:
```json
{
    "python_version": "3.11.4",
    "os": "Windows-10",
    "ollama_model": "mistral",
    "ollama_model_digest": "sha256:abc123...",
    "git_sha": "a1b2c3d4",
    "timestamp": "2026-05-18T10:30:00"
}
```

**4. Console Summary:**

พิมพ์สรุปสวยงามใน terminal:
```
════════════════════════════════════════
  PolicyChecker Pipeline Report
════════════════════════════════════════
  Sentences extracted:    8,432
  After prefilter:          743  (8.8%)
  Rules classified:         432
  FOL success:              431  (99.8%)
  Shapes generated:         432
  Violations found:           7
────────────────────────────────────────
  GENUINE VIOLATIONS:         5
  LIKELY FALSE POSITIVES:     2
════════════════════════════════════════
```

---

## 7. โครงสร้างพื้นฐานสนับสนุน

### 7.1 State — PipelineState

**ไฟล์:** `langgraph_agent/state.py`

`PipelineState` คือ TypedDict ที่ทำหน้าที่เป็น "กระเป๋าข้อมูล" ส่งต่อระหว่าง node ทุกตัว

```python
from __future__ import annotations
import operator
from typing import Annotated, List, TypedDict

class PipelineState(TypedDict):
    # Input
    source_dir: str          # path ไปยังโฟลเดอร์ PDF
    corpus: str              # ชื่อ corpus เช่น "ait"

    # ขั้น Extract
    sentences: List[dict]    # ประโยคทั้งหมด

    # ขั้น Classify
    rules: Annotated[List[dict], operator.add]          # กฎที่มั่นใจ
    uncertain_rules: Annotated[List[dict], operator.add] # กฎที่ไม่แน่ใจ

    # ขั้น FOL
    fol_formulas: Annotated[List[dict], operator.add]   # FOL formulas สำเร็จ
    fol_failed: Annotated[List[dict], operator.add]     # FOL ล้มเหลว

    # ขั้น SHACL
    generated_shapes: str    # Turtle text รวม shapes ทั้งหมด

    # ขั้น Validate
    validation_results: dict # ผล validation

    # ขั้น Report
    report: dict             # สรุปสถิติ
```

#### `Annotated[List[dict], operator.add]` คืออะไร?

นี่คือ pattern ของ LangGraph สำหรับ **parallel merge**

เมื่อ 2 nodes ทำงานพร้อมกัน (เช่น `shacl` และ `direct_shacl`) และทั้งสองต่างก็ return ค่าในฟิลด์เดียวกัน (เช่น `generated_shapes`) LangGraph จะ **รวมทั้งสองเข้าด้วยกัน** โดยใช้ `operator.add` (append เข้า list)

ถ้าไม่ใช้ Annotated: อันใดอันหนึ่งจะเขียนทับอีกอัน

---

### 7.2 Graph — build_graph()

**ไฟล์:** `langgraph_agent/graph.py`

ไฟล์นี้ **กำหนดโครงสร้าง Pipeline ทั้งหมด** ว่า node ไหนเชื่อมต่อกับ node ไหน

```python
from langgraph.graph import END, StateGraph

def build_graph() -> StateGraph:
    g = StateGraph(PipelineState)

    # ── ลงทะเบียน Nodes ทั้ง 9 ตัว ──────────────────────────
    g.add_node("extract",      extract_node)
    g.add_node("prefilter",    prefilter_node)
    g.add_node("classify",     classify_node)
    g.add_node("reclassify",   reclassify_node)
    g.add_node("fol",          fol_node)
    g.add_node("shacl",        shacl_node)
    g.add_node("direct_shacl", direct_shacl_node)
    g.add_node("validate",     validate_node)
    g.add_node("report",       report_node)

    # ── กำหนด Edge คงที่ ──────────────────────────────────────
    g.set_entry_point("extract")
    g.add_edge("extract",      "prefilter")
    g.add_edge("prefilter",    "classify")
    g.add_edge("reclassify",   "fol")

    # Parallel Fan-out: fol → ทั้ง shacl และ direct_shacl พร้อมกัน
    g.add_edge("fol",          "shacl")
    g.add_edge("fol",          "direct_shacl")

    # ทั้งสองมารวมที่ validate
    g.add_edge("shacl",        "validate")
    g.add_edge("direct_shacl", "validate")

    g.add_edge("validate",     "report")
    g.add_edge("report",       END)

    # ── Conditional Edge ────────────────────────────────────
    g.add_conditional_edges(
        "classify",          # จาก node นี้
        route_classify,      # เรียกฟังก์ชันนี้เพื่อตัดสินใจ
        {
            "reclassify": "reclassify",  # ถ้าตอบ "reclassify" → ไป node reclassify
            "fol":        "fol",         # ถ้าตอบ "fol" → ไป node fol โดยตรง
            "end":        END,           # ถ้าตอบ "end" → จบการทำงาน
        },
    )

    return g.compile()
```

#### วิธีดู Mermaid Diagram ของ Graph:

```bash
python -m langgraph_agent.graph
```
จะพิมพ์ Mermaid diagram ออกมา copy ไป paste ที่ https://mermaid.live เพื่อดูเป็นรูปภาพ

---

### 7.3 Routing — route_classify

**ไฟล์:** `langgraph_agent/edges/route_classify.py`

ฟังก์ชันนี้เล็กมาก แต่สำคัญ — มันตัดสินใจว่าหลัง classify จะไปทิศทางไหน

```python
def route_classify(state: PipelineState) -> str:
    has_uncertain = bool(state.get("uncertain_rules"))
    has_rules = bool(state.get("rules"))

    if has_uncertain:
        return "reclassify"   # ← มีประโยคไม่แน่ใจ → ส่งให้ตรวจสอบซ้ำก่อน
    elif has_rules:
        return "fol"          # ← มีแต่กฎที่มั่นใจ → ไป FOL ได้เลย
    else:
        return "end"          # ← ไม่มีกฎเลย → จบ (ไม่มีอะไรทำ)
```

**ประเด็นสำคัญ:** ถ้ามี uncertain rules แม้แต่ตัวเดียว จะ route ไป reclassify ก่อนเสมอ แม้จะมี confident rules อยู่ด้วยก็ตาม

---

### 7.4 LLM — get_llm()

**ไฟล์:** `langgraph_agent/llm.py`

ไฟล์นี้จัดการการสร้าง LLM instances ทั้งหมด

```python
from langchain_ollama import ChatOllama

OLLAMA_HOST = os.getenv("OLLAMA_HOST", "http://localhost:11434")
DEFAULT_MODEL = os.getenv("OLLAMA_MODEL", "mistral")
SEED = int(os.getenv("OLLAMA_SEED", "42"))
LLM_TIMEOUT = int(os.getenv("OLLAMA_TIMEOUT", "120"))

def get_llm(model=None, temperature=0.0, seed=SEED, timeout=None):
    return ChatOllama(
        model=model or DEFAULT_MODEL,
        temperature=temperature,    # 0.0 = deterministic (ไม่สุ่ม)
        base_url=OLLAMA_HOST,
        client_kwargs={"timeout": httpx.Timeout(timeout, connect=30.0)},
        model_kwargs={
            "seed": seed,
            "num_predict": 512,   # จำกัดความยาว output
            "top_k": 1,           # greedy decoding
            "top_p": 1.0,
        },
    )
```

#### ทำไม temperature=0.0 และ seed=42?

- `temperature=0.0` → output deterministic ทุกครั้งที่รันด้วย input เดิมจะได้ output เดิม → reproducible
- `seed=42` → ยิ่งทำให้ reproducible มากขึ้น (random seed คงที่)
- `top_k=1` → greedy decoding เลือก token ที่มีความน่าจะเป็นสูงสุดเสมอ

#### Environment Variables ที่ปรับได้:

| Variable | Default | ความหมาย |
|----------|---------|---------|
| `OLLAMA_HOST` | `http://localhost:11434` | ที่อยู่ Ollama server |
| `OLLAMA_MODEL` | `mistral` | โมเดลหลัก |
| `OLLAMA_SECOND_MODEL` | `mistral` | โมเดลสำหรับ reclassify |
| `OLLAMA_SEED` | `42` | random seed |
| `OLLAMA_TIMEOUT` | `120` | timeout (วินาที) |

---

### 7.5 LLM Cache

**ไฟล์:** `core/llm_cache.py`

#### ทำไมต้องมี Cache?

การรัน LLM ใช้เวลา ~1-3 วินาทีต่อ prompt ถ้ามี 400 กฎ → ใช้เวลา 10-20 นาที ถ้า run ซ้ำด้วยข้อมูลเดิม ไม่ควรต้องรอใหม่

#### วิธีทำงาน:

**1. สร้าง Cache Key จาก SHA-256:**
```python
def _make_key(text, model, prompt_type, temperature, **extra):
    payload = json.dumps({
        "text": text,
        "model": model,
        "prompt_type": prompt_type,
        "temperature": temperature,
        **extra
    }, sort_keys=True)  # sort_keys ทำให้ key เดิมไม่ว่าจะเรียง dict ยังไง
    return hashlib.sha256(payload.encode()).hexdigest()
```

**2. เก็บใน SQLite:**
```python
CREATE TABLE cache (
    key TEXT PRIMARY KEY,
    response TEXT,
    timestamp INTEGER,
    hit_count INTEGER DEFAULT 0
);
```

**3. LRU Eviction:**
ถ้า cache มีมากกว่า 1,000 entries → ลบ 100 entries ที่เก่าที่สุดออก (Least Recently Used)

**4. WAL Mode:**
```python
conn.execute("PRAGMA journal_mode=WAL")
```
WAL (Write-Ahead Logging) ช่วยให้หลาย process อ่าน cache พร้อมกันได้โดยไม่ block กัน

**5. Singleton Pattern:**
```python
_cache_instance = None

def get_cache() -> LLMCache:
    global _cache_instance
    if _cache_instance is None:
        _cache_instance = LLMCache("cache/llm_cache.db")
    return _cache_instance
```
ทั้ง pipeline ใช้ cache instance เดียวกัน

---

### 7.6 Corpus Config

**ไฟล์:** `langgraph_agent/corpus_config.py` และ `config/ait.yaml`

#### ทำไมต้องมี Corpus Config?

ระบบนี้ออกแบบให้รองรับหลายสถาบัน (AIT, KMUTT, Chula ฯลฯ) แต่ละสถาบันมี:
- คำศัพท์ domain ต่างกัน
- ชื่อ class ใน ontology ต่างกัน
- ตัวอย่าง FOL ต่างกัน

แทนที่จะ hard-code ทุกอย่างในโค้ด จึงแยกไว้ใน YAML config

#### โครงสร้างของ `config/ait.yaml`:

```yaml
corpus:
  name: "ait"
  display_name: "Asian Institute of Technology"
  namespace: "http://example.org/ait-policy#"
  prefix: "ait"

paths:
  pdf_dir: "institutional_policy/AIT"
  ontology: "shacl/ontology/ait_policy_ontology.ttl"
  vocabulary: "shacl/ontology/property_list.txt"
  gold_shapes: "shacl/shapes/ait_policy_shapes.ttl"
  test_data: "shacl/test_data/tdd_test_data_fixed.ttl"

prompts:
  fol_examples:
    - text: "Students must submit their thesis by the deadline."
      deontic_type: "obligation"
      formula: "O(submittitlepage(student))"
      ...

target_class_patterns:
  - pattern: "student(s?)"
    class: "Student"
  - pattern: "faculty|instructor"
    class: "Faculty"
  ...

domain_words:
  - accommodation
  - dormitory
  - fee
  - payment
  ...

stop_words_extra:
  - student
  - ait
  - university
```

#### วิธีใช้งาน `CorpusConfig`:

```python
from langgraph_agent.corpus_config import get_corpus_config

cfg = get_corpus_config("ait")

# ดึง vocabulary สำหรับใส่ใน prompt
vocab = cfg.vocabulary_hint()
# → "payFees, submitThesis, attendClass, ..."

# หา OWL class จาก rule text
cls = cfg.target_class_for("Students must register before the deadline.")
# → "Student"

# ดึง FOL examples สำหรับ few-shot prompting
examples = cfg.fol_examples_block()
# → ข้อความ formatted หลาย paragraphs

# รับ full stop words
stop_words = cfg.full_stop_words()
# → frozenset รวม universal + corpus-specific
```

#### การ Cache Config:

```python
_CONFIG_CACHE: Dict[str, CorpusConfig] = {}

def get_corpus_config(corpus_name):
    if corpus_name not in _CONFIG_CACHE:
        _CONFIG_CACHE[corpus_name] = load_corpus_config(corpus_name)
    return _CONFIG_CACHE[corpus_name]
```

Config โหลดครั้งเดียว ครั้งต่อไปดึงจาก dict ทันที

---

## 8. Web Dashboard

**ไฟล์:** `web/app.py` (backend), `web/frontend/` (Vite + React)

### FastAPI Backend

Backend ทำหน้าที่แค่ **อ่านไฟล์ output** ที่ pipeline สร้างไว้แล้ว แล้ว serve ให้ frontend

```python
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(title="PolicyChecker Dashboard", version="2.0.0")

# อนุญาต Vite dev server (localhost:5173) เข้าถึง
app.add_middleware(CORSMiddleware, allow_origins=["http://localhost:5173"])

OUTPUT_DIR = Path("output/ait")
SHAPES_FILE      = OUTPUT_DIR / "shapes_generated.ttl"
RULES_FILE       = OUTPUT_DIR / "classified_rules.json"
FOL_FILE         = OUTPUT_DIR / "fol_formulas.json"
REPORT_FILE      = OUTPUT_DIR / "pipeline_report.json"
TEST_DATA_FILE   = Path("shacl/test_data/tdd_test_data_fixed.ttl")
ONTOLOGY_FILE    = Path("shacl/ontology/ait_policy_ontology.ttl")
```

### Endpoints หลัก:

| Method | Path | ส่งกลับอะไร |
|--------|------|------------|
| GET | `/api/report` | pipeline_report.json |
| GET | `/api/rules` | extracted_rules.json |
| GET | `/api/fol` | fol_formulas.json |
| GET | `/api/shapes` | generated_shapes.ttl (as text) |
| GET | `/api/validation` | validation_results.json |
| GET | `/api/ontology` | ontology.ttl (as text) |
| GET | `/api/test-data` | tdd_test_data_fixed.ttl (as text) |

### วิธีรัน:

```bash
# Terminal 1: Backend
uvicorn web.app:app --reload --port 8000

# Terminal 2: Frontend
cd web/frontend
npm install
npm run dev
# เปิดที่ http://localhost:5173
```

---

## 9. Ablation Studies

Ablation study คือการ **ทดสอบโดยปิดส่วนหนึ่งของระบบ** เพื่อดูว่าส่วนนั้นสำคัญแค่ไหน

### วิธีรัน Ablation:

```bash
python -m langgraph_agent.run --source ait --ablation no-prefilter
```

Output จะถูกเก็บแยกใน `output/ait_no-prefilter/` เพื่อไม่ทับ baseline

### รายการ Ablation ที่มี:

| ชื่อ | Environment Variable | ผลที่เกิดขึ้น |
|------|---------------------|-------------|
| `no-prefilter` | `ABLATION_SKIP_PREFILTER=1` | ส่งทุกประโยคให้ classify (ไม่กรองก่อน) |
| `no-hints` | `ABLATION_NO_HINTS=1` | ไม่บอก LLM เกี่ยวกับ vocabulary hint ของ corpus |
| `no-reclassify` | `ABLATION_SKIP_RECLASSIFY=1` | ทิ้ง uncertain_rules ทั้งหมด |
| `no-fallback` | `ABLATION_SKIP_DIRECT_SHACL=1` | ไม่สร้าง SHACL สำหรับกฎที่ FOL ล้มเหลว |
| `no-fol-retry` | `ABLATION_NO_FOL_RETRY=1` | ไม่ retry FOL เมื่อ parse ไม่ได้ |
| `no-may-disambig` | `ABLATION_NO_MAY_DISAMBIG=1` | ไม่แยก epistemic vs deontic "may" |

### การอ่านผล:

หลังรัน ablation เปรียบเทียบ `pipeline_report.json` ระหว่าง:
- `output/ait/` (baseline)
- `output/ait_no-prefilter/`

ดูว่า เมื่อปิด prefilter: จำนวนกฎที่พบเพิ่มหรือลด? คุณภาพ shapes ดีขึ้นหรือแย่ลง?

---

## 10. ฐานข้อมูล PostgreSQL และ Seeder

**ไฟล์:** `db/connection.py`, `db/schema.sql`, `db/seed.py`, `db/rdf_converter.py`

Web Dashboard รองรับการโหลดข้อมูล entity จริงจาก **PostgreSQL** แล้วแปลงเป็น RDF Turtle เพื่อนำไปตรวจสอบกับ SHACL shapes

### โครงสร้างตาราง (schema.sql)

```
students (PK: student_id)
  ├── fee_records        (FK → students, ค่าธรรมเนียมรายภาค + สถานะการชำระ)
  ├── accommodations     (FK → students, ข้อมูลหอพัก)
  ├── conduct_records    (FK → students, บันทึกความประพฤติ)
  ├── student_conduct    (FK → students, flag พฤติกรรม boolean)
  └── academic_records   (FK → students, flag การลงทะเบียนและงานวิจัย)

faculty      (faculty_id, grading/disciplinary/disclosure flags)
staff        (staff_id, gifts/settlements/ethics flags)
committees   (committee_name, grievance/tribunal flags)
```

### การ Seed ข้อมูลตัวอย่าง

```bash
# เริ่ม PostgreSQL ด้วย Docker
docker compose up -d postgres

# สร้างตารางและใส่ข้อมูลตัวอย่าง (นักศึกษา 6 คน, อาจารย์ 3 คน, เจ้าหน้าที่ 2 คน, คณะกรรมการ 2 ชุด)
python -m db.seed

# ล้างข้อมูลแล้วใส่ใหม่
python -m db.seed --reset
```

### RDF Converter

`db/rdf_converter.py` แปลงข้อมูลใน PostgreSQL เป็น Turtle RDF:

```python
# แสดงผล Turtle ออกทาง stdout
python -m db.rdf_converter
```

ตัวอย่างผลลัพธ์:
```turtle
ait:student001 a ait:Student ;
    ait:studentId "S001" ;
    ait:payFee true ;
    ait:livesInDorm true .
```

### การเชื่อมต่อ PostgreSQL (ตั้งค่าใน .env)

```env
POSTGRES_HOST=localhost
POSTGRES_PORT=5432
POSTGRES_DB=ait_database
POSTGRES_USER=postgres
POSTGRES_PASSWORD=mysecretpassword
```

### ใช้ผ่าน Web Dashboard

เมื่อ backend รันอยู่ ให้กด **"Load from Database"** บนหน้า Dashboard — ระบบจะ query PostgreSQL, แปลงเป็น Turtle, แล้วกรอกลงใน editor โดยอัตโนมัติ จากนั้นกด **"Check Compliance"** เพื่อรัน SHACL validation

---

## 11. ไฟล์ Output ที่โปรแกรมสร้างขึ้น

ทุกอย่างอยู่ใน `output/ait/`:

### `classified_rules.json`

กฎทั้งหมดที่ pipeline extract ได้ พร้อม metadata:
```json
[
    {
        "text": "Students must pay tuition fees before the semester begins.",
        "source": "AIT_Student_Handbook.pdf",
        "page": 12,
        "deontic_type": "obligation",
        "confidence": 0.92,
        "section_context": "Financial Requirements"
    }
]
```

### `fol_formulas.json`

FOL formulas สำหรับแต่ละกฎ:
```json
[
    {
        "rule_text": "Students must pay tuition fees...",
        "deontic_type": "obligation",
        "deontic_formula": "O(payFees(student))",
        "fol_expansion": "∀x (Student(x) → O(payFees(x)))",
        "predicates": {
            "subject": "student",
            "action": "payFees",
            "condition": "before semester"
        }
    }
]
```

### `shapes_generated.ttl`

SHACL Shapes ทั้งหมดในรูปแบบ Turtle:
```turtle
@prefix ait: <http://example.org/ait-policy#> .
@prefix sh: <http://www.w3.org/ns/shacl#> .
@prefix xsd: <http://www.w3.org/2001/XMLSchema#> .

ait:PayFeesShape a sh:NodeShape ;
    sh:targetClass ait:Student ;
    sh:property [
        sh:path ait:payFees ;
        sh:minCount 1 ;
        sh:name "payFees" ;
    ] ;
    ait:generationMethod "fol_pipeline" ;
    ait:sourceRule "Students must pay tuition fees..." .
```

### `validation_results.json`

ผล SHACL validation:
```json
{
    "conforms": false,
    "total_violations": 7,
    "violations": [
        {
            "focus_node": "ait:student001",
            "result_path": "ait:payFees",
            "source_shape": "ait:PayFeesShape",
            "severity": "Violation",
            "message": "Less than 1 values on ait:student001->ait:payFees"
        }
    ]
}
```

### `pipeline_report.json`

สรุปสถิติทั้งหมด รวมถึง violation triage และ environment info

---

## 12. Evaluation Harness — ใช้งานอย่างไร

**ไฟล์:** `evaluation/` directory

โปรแกรมมีชุด evaluation scripts สำหรับวัดคุณภาพของ pipeline ในแง่ต่าง ๆ

### ไฟล์ใน evaluation/

| ไฟล์ | สถานะ | ทำอะไร |
|------|--------|---------|
| `external_annotator_agreement.py` | ✅ ใช้งานอยู่ | คำนวณ Fleiss' κ (IRR) และ LLM accuracy จาก annotation ของมนุษย์ 3 คน |
| `confidence_intervals.py` | ✅ ใช้งานอยู่ | Bootstrap 95% CI สำหรับทุก metric → `thesis_metrics_with_ci.json` |
| `report.py` | ✅ ใช้งานอยู่ | รวมผล D3 metrics แสดงในรูปแบบ table |
| `align.py` | ⛔ เลิกใช้ | M1 extraction coverage (ต้องใช้ D1 gold ที่ไม่มีแล้ว) |
| `per_rule_eval.py` | ⛔ เลิกใช้ | M4 shape correctness (ต้องใช้ D2 gold ที่ไม่มีแล้ว) |

### คำสั่งรัน Evaluation

```bash
# 1. คำนวณ IRR + LLM accuracy (ต้องใช้ไฟล์ annotation ก่อน)
python -m evaluation.external_annotator_agreement
# → สร้าง output/ait/external_annotator_agreement.json

# 2. Bootstrap 95% Confidence Intervals
python -m evaluation.confidence_intervals
# → สร้าง output/ait/thesis_metrics_with_ci.json

# 3. ดูสรุป D3 metrics บน console
python -m evaluation.report --source ait

# 4. แสดงผลเป็น Markdown table (copy ไปใส่ thesis ได้เลย)
python -m evaluation.report --source ait --md

# 5. บันทึก thesis_metrics.json
python -m evaluation.report --source ait --save
```

### Metrics สำคัญและผลที่ได้

| Metric | ผลปัจจุบัน | ความหมาย |
|--------|-----------|---------|
| **IRR Fleiss' κ** | **0.8436** (Almost Perfect) | ความสอดคล้องระหว่าง annotator 3 คน (author, Kittipat, Mayuree) บน 50 ประโยค |
| **LLM Accuracy** | **84.0%** (42/50) | ความถูกต้องของ LLM เทียบกับ majority-vote human gold |
| **LLM Cohen's κ** | **0.629** (Substantial) | ความสอดคล้องระหว่าง LLM กับ human gold |
| **M3 FOL Quality** | **100%** (351/351) | FOL formulas ที่มี semantic predicates ถูกต้อง |
| **M5 Output Stability** | **PASS** | SHACL output hash-identical ทุกครั้งที่รันด้วย fixed seed |

### ไฟล์ Annotation ที่ต้องมี

`evaluation/external_annotator_agreement.py` ต้องการไฟล์ annotation จาก annotator ทั้ง 3 คน ในรูปแบบที่กำหนดไว้ในโค้ด ถ้าไม่มีไฟล์ดังกล่าว ให้รัน `confidence_intervals.py` โดยตรงแทน ซึ่งใช้ข้อมูลจาก `thesis_metrics_with_ci.json` ที่มีอยู่แล้วใน `output/ait/`

---

## 13. คำศัพท์สำคัญ

| คำศัพท์ | คำอธิบาย |
|---------|---------|
| **Deontic Logic** | ระบบตรรกะที่จัดการกับ "หน้าที่" "การอนุญาต" และ "การห้าม" |
| **FOL (First-Order Logic)** | ภาษา formal สำหรับแสดงความสัมพันธ์เชิงตรรกะ เช่น `∀x (Student(x) → O(payFees(x)))` |
| **O(φ)** | Obligation — หน้าที่ที่ต้องทำ |
| **P(φ)** | Permission — ได้รับอนุญาตให้ทำ |
| **F(φ)** | Forbidden/Prohibition — ห้ามทำ |
| **SHACL** | Shapes Constraint Language — W3C standard สำหรับ validate RDF data |
| **NodeShape** | SHACL shape ที่ apply กับ class ทั้งหมด (เช่น ทุก instance ของ Student) |
| **PropertyShape** | SHACL shape ที่กำหนดข้อกำหนดของ property หนึ่ง ๆ |
| **RDF** | Resource Description Framework — โครงสร้างข้อมูลแบบ graph ใช้ triple: subject-predicate-object |
| **Turtle (.ttl)** | รูปแบบการเขียน RDF ที่อ่านง่ายสำหรับมนุษย์ |
| **OWL Ontology** | นิยาม class และ property ที่ถูกต้องสำหรับ domain |
| **pyshacl** | Python library สำหรับรัน SHACL validation |
| **rdflib** | Python library สำหรับสร้าง parse และ query RDF graphs |
| **LangGraph** | Framework สำหรับสร้าง stateful AI pipelines ในรูปแบบ directed graph |
| **StateGraph** | LangGraph class หลักสำหรับสร้าง graph |
| **PipelineState** | TypedDict ที่ทำหน้าที่เป็น "กระเป๋าข้อมูล" ส่งต่อระหว่าง node |
| **Parallel Fan-out** | รูปแบบที่ node เดียวส่งงานให้หลาย node พร้อมกัน |
| **Ollama** | ซอฟต์แวร์สำหรับรัน LLM บนเครื่องตัวเอง (local) |
| **Mistral 7B** | LLM ที่ใช้ใน project นี้ 7 billion parameters |
| **temperature=0.0** | ทำให้ LLM output deterministic ไม่สุ่ม |
| **Few-shot Prompting** | การใส่ตัวอย่างในตัว prompt เพื่อสอน LLM ว่าต้องการ output แบบไหน |
| **Gold Shapes** | SHACL shapes ที่เขียนด้วยมือโดยผู้เชี่ยวชาญ ใช้เป็น ground truth |
| **Ablation Study** | การทดสอบโดยปิดส่วนหนึ่งของระบบเพื่อวัดผลกระทบ |
| **IRR (Inter-Rater Reliability)** | ค่าวัดความสอดคล้องระหว่าง annotator หลายคน |
| **Fleiss' κ** | สถิติ IRR ค่า 0.8436 = สอดคล้องสูงมาก |
| **Epistemic "may"** | "may" ในความหมาย "อาจจะ" (ความเป็นไปได้) → ไม่ใช่กฎ |
| **Deontic "may"** | "may" ในความหมาย "อนุญาตให้" → เป็นกฎ |
| **SHA-256** | hash function ใช้สร้าง cache key ที่ unique |
| **LRU Eviction** | กลยุทธ์ลบ cache โดยลบที่เก่า/ใช้น้อยที่สุดออก |
| **WAL Mode** | SQLite mode ที่รองรับการ concurrent read ได้ดีขึ้น |
| **BNode (Blank Node)** | node ใน RDF ที่ไม่มี URI ไม่สามารถอ้างอิงจากภายนอกได้ |
| **False Positive** | Shape ที่ยิง violation ผิด ๆ บน data ที่ถูกต้องจริง |
| **TDD (Test-Driven Development)** | approach ที่เขียน test ก่อนแล้วค่อยเขียน code |

---

## 14. คำถาม-คำตอบที่พบบ่อย

### Q1: ทำไมถึงใช้ LangGraph แทน pipeline ธรรมดา?

**A:** LangGraph ให้ความสามารถที่ pipeline ธรรมดาทำได้ยาก:
1. **Conditional routing** — เลือกเส้นทางตาม state ได้
2. **Parallel execution** — รัน SHACL และ Direct SHACL พร้อมกัน
3. **State persistence** — track ข้อมูลทั้ง pipeline ใน type-safe dict
4. **Built-in streaming** — ดูผลลัพธ์ทีละ node ได้ระหว่าง run
5. **Visualization** — generate Mermaid diagram ได้อัตโนมัติ

### Q2: ทำไม LLM ให้ผลต่างกันในแต่ละรัน?

**A:** ถ้าตั้งค่าถูกต้อง (`temperature=0.0`, `seed=42`) ผลควรเหมือนกันทุกครั้ง ถ้าต่างกันให้ตรวจสอบ:
1. ใช้ Ollama model version เดียวกันไหม?
2. `OLLAMA_SEED` env var ถูกตั้งไหม?
3. LLM cache ถูก clear ระหว่าง run ไหม?

### Q3: ทำไมต้องมี Gold Shapes ด้วย?

**A:** Gold shapes คือ "ground truth" ที่เขียนโดยผู้เชี่ยวชาญ ซึ่งใช้ใน 2 วัตถุประสงค์:
1. **Validation ที่ครอบคลุม** — ให้ pipeline-generated shapes validate ร่วมกับ gold shapes
2. **Comparison** — ดูว่า pipeline สร้าง shape คล้าย gold shapes แค่ไหน (วัด quality)

### Q4: False Positive คืออะไร และเกิดได้อย่างไร?

**A:** False positive คือ SHACL shape ที่ยิง "violation" ทั้งที่ data ถูกต้องจริง

**ตัวอย่าง:** LLM สร้าง shape ที่บอกว่า "ทุก Person ต้องมี payFees" ทั้งที่จริง ๆ แค่ Student เท่านั้นที่ต้องจ่าย → shape จะ fire บน Faculty, Staff ด้วย ซึ่งเป็น false positive

**วิธี detect:** ถ้า shape ยิง violation บน >80% ของ test entities → flagged เป็น likely false positive

### Q5: Pipeline ใช้เวลานานแค่ไหน?

**A:** ขึ้นอยู่กับขนาดเอกสาร:
- Documents ขนาดเล็ก (~50 หน้า): 10-15 นาที
- AIT full corpus (~200 หน้า): 30-45 นาที (first run)
- Subsequent runs: 2-5 นาที (เพราะใช้ LLM cache)

### Q6: จะเพิ่ม corpus สถาบันใหม่ได้อย่างไร?

**A:** ทำตามขั้นตอนนี้:
1. Copy `config/ait.yaml` → `config/newuni.yaml`
2. แก้ไข: `corpus.name`, `corpus.namespace`, `corpus.prefix`
3. แก้ไข paths ให้ชี้ไปยังไฟล์ที่ถูกต้อง
4. ปรับ `target_class_patterns`, `domain_words`, `fol_examples`
5. รัน: `python -m langgraph_agent.run --corpus newuni --source path/to/pdfs`

### Q7: LLM Cache เก็บอยู่ที่ไหน จะล้างได้อย่างไร?

**A:** Cache อยู่ที่ `cache/llm_cache.db`

ล้าง cache:
```bash
# ลบทั้งหมด
rm cache/llm_cache.db

# หรือใน Python:
from core.llm_cache import get_cache
get_cache().clear_all()
```

### Q8: ถ้า Ollama ไม่ตอบสนอง Pipeline จะเกิดอะไรขึ้น?

**A:** `get_llm()` ตั้ง timeout ไว้ที่ 120 วินาที (ปรับได้ด้วย `OLLAMA_TIMEOUT`) ถ้า timeout เกิน → จะ raise `httpx.TimeoutException` → node จะ log error และประโยคนั้นจะถูกข้ามไป

### Q9: validation_results.json มี violations เยอะมาก ปกติไหม?

**A:** ขึ้นกับขนาดของ test data และ shapes ที่สร้างได้ violations หลายตัวอาจเป็น false positives (shape เขียนผิด) ให้ดูที่ `pipeline_report.json` ส่วน `violation_triage` ว่า violations ไหนถูก flag ว่า `LIKELY_FALSE_POSITIVE`

### Q10: ความหมายของ IRR Fleiss' κ = 0.8436?

**A:** Fleiss' κ วัดว่า annotator หลายคนเห็นด้วยกันแค่ไหน (มากกว่าที่คาดจากการเดาสุ่ม):
- κ < 0.2: ไม่สอดคล้อง
- 0.4-0.6: สอดคล้องปานกลาง
- 0.6-0.8: สอดคล้องดี
- **0.8+ สอดคล้องดีมาก** ← ค่าของเรา 0.8436 อยู่ในระดับนี้

หมายความว่าเมื่อให้ผู้คน 3 คนดู 50 ประโยค แล้วบอกว่าแต่ละอันเป็น "กฎ" หรือ "ไม่ใช่กฎ" พวกเขาเห็นด้วยกัน 84.36% ซึ่งสูงมาก → annotation ที่ใช้ train/test pipeline น่าเชื่อถือ

### Q11: จะ debug ได้อย่างไรถ้า shape ที่ generate ผิด?

**A:** ทำตามลำดับนี้:
1. เปิด `output/ait/fol_formulas.json` → ดูว่า FOL formula ถูกต้องไหม
2. เปิด `output/ait/generated_shapes.ttl` → ดูว่า Turtle syntax ถูกต้องไหม
3. ลอง parse Turtle ด้วยตัวเอง:
   ```python
   from rdflib import Graph
   g = Graph()
   g.parse("output/ait/generated_shapes.ttl", format="turtle")
   # ถ้าไม่ error = valid Turtle
   ```
4. ดู log ใน terminal ว่ามี warning อะไรหรือไม่ (รันด้วย `--verbose`)

### Q12: ต้องการ GPU ไหม?

**A:** ไม่จำเป็น แต่แนะนำถ้ามี:
- **CPU only:** Mistral 7B รันได้ แต่ช้า (~10-30 วินาที/inference)
- **GPU (NVIDIA 8GB+):** เร็วกว่ามาก (~1-3 วินาที/inference)
- Ollama ตรวจจับ GPU อัตโนมัติ ไม่ต้องตั้งค่าพิเศษ

---

## สรุปสุดท้าย — ภาพรวมทั้งหมดในหนึ่งย่อหน้า

PolicyChecker รับ **PDF เอกสารนโยบาย** แล้วผ่านกระบวนการ 9 ขั้นตอน: (1) Extract ดึงประโยค, (2) Prefilter กรอง heuristic, (3) Classify ถามว่าเป็นกฎไหม, (4) Reclassify ยืนยันด้วย LLM ที่สอง, (5) FOL แปลงเป็น First-Order Logic, (6) SHACL สร้าง shape จาก FOL, (7) Direct SHACL สำหรับ fallback, (8) Validate รัน pyshacl, (9) Report สรุปผล ทั้ง pipeline ขับเคลื่อนด้วย **LangGraph** ที่ใช้ **PipelineState** เป็นตัวส่งข้อมูล ใช้ **Mistral 7B** ผ่าน **Ollama** เป็น LLM และใช้ **SQLite cache** เพื่อประหยัดเวลา รองรับหลายสถาบันผ่าน **corpus config YAML** และมี **Web Dashboard** สำหรับดูผลลัพธ์

---

*เอกสารนี้เขียนขึ้นเพื่อถ่ายทอดงานให้ นศ. intern — หากมีข้อสงสัยใด ๆ ให้อ่าน source code ควบคู่กับเอกสารนี้*

*วันที่อัปเดต: 18 พฤษภาคม 2569*
