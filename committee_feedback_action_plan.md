# Committee Feedback — Action Plan & Recommendations

## Overview

This document addresses each committee concern point-by-point with concrete, actionable solutions Phongkrit can implement before the May final defense.

---

## 1. Professor Attaphongse (Prof. Pong)

### 1.1 Preservation of Meaning (NL → FOL → SHACL)

**Concern:** How do you ensure meaning is preserved across the multi-step translation?

**Recommended Action: Create a "Translation Trace Table"**

Build a table showing 5–10 representative rules through every stage. For example:

| Stage | Content |
|---|---|
| **NL (Original)** | "A student who has outstanding fees must not register for courses." |
| **Extracted Rule** | `PROHIBITION: student with outstanding_fees → cannot register_courses` |
| **FOL** | `∀x(Student(x) ∧ HasOutstandingFees(x) → ¬CanRegister(x))` |
| **SHACL** | `sh:targetClass :Student ; sh:property [ sh:path :hasOutstandingFees ; sh:maxCount 0 ; sh:severity sh:Violation ]` |
| **Validation** | Negative test: Student with fees → ✅ Violation detected |

**Why this matters:** This directly demonstrates **semantic traceability** — you can show at each stage what was preserved and what was transformed. Include this in both the thesis and the presentation.

**Implementation:**
- Pick rules from different deontic categories (obligation, prohibition, permission)
- Include at least one "tricky" rule where ambiguity was resolved
- Add this as a new section in Chapter 4 or Chapter 5

---

### 1.2 Logical Formalization Necessity (Why not NL → SHACL directly?)

**Concern:** Why not skip FOL and go NL → SHACL directly? What value does FOL add?

**Recommended Actions:**

1. **Run a direct NL→SHACL experiment.** Use the same LLM and a sample of rules. Prompt Mistral to generate SHACL directly from Natural Language. Compare:
   - Syntactic validity rate (does it parse?)
   - Semantic correctness (does it match the intended rule?)
   - Error types (what kinds of mistakes does it make?)

2. **Articulate the "Semantic Checkpoint" argument clearly:**
   - FOL is **human-verifiable** — domain experts and logicians can read `∀x(P(x) → Q(x))` and confirm it matches the intent, whereas raw SHACL/Turtle is not readable by non-technical stakeholders.
   - FOL catches **logical errors early** — an incorrect FOL formula is much easier to spot than an incorrect SHACL shape buried in RDF triples.
   - FOL provides **formalism independence** — the same FOL can be compiled to SHACL, SPARQL constraints, or OWL axioms. Skipping it couples you to one technology.
   - FOL enables **Assumption-Based Argumentation (ABA)** — you need FOL to reason about conflicting rules. Raw SHACL has no native conflict resolution mechanism.

3. **Expected result:** The direct NL→SHACL approach will likely produce syntactically valid but semantically incorrect shapes, especially for complex deontic rules. This empirically justifies the FOL layer.

---

### 1.3 Handling Ambiguity with ABA

**Concern:** How does ABA resolve linguistic ambiguity? Show concrete examples.

**Recommended Actions:**

1. **Pick 2–3 concrete ambiguity examples** from your dataset:
   - The **"should"** ambiguity (advisory vs. obligation) — you already have 4 disagreements on this
   - **"May"** ambiguity (permission vs. possibility) — you have 14 permission rules with 50% misclassification
   - **Scope ambiguity** (e.g., "Students must submit thesis AND pay fees before graduation" — does "before graduation" apply to both conditions?)

2. **Show the ABA framework in action:**
   - Define the **assumptions** (e.g., "assume 'should' means obligation unless context indicates advisory")
   - Show the **argumentation** (argument for obligation vs. argument for advisory)
   - Show the **resolution** (which argument wins under the preferred semantics and why)

3. **If ABA is not yet implemented**, be honest about it. Frame it as: "The framework architecture supports ABA integration at the FOL layer. In the current prototype, ambiguity is resolved via prompt engineering (few-shot examples). Future work will implement full ABA resolution."

---

### 1.4 Scaling to Multi-Condition Policies

**Concern:** Can the framework handle complex rules that check multiple conditions simultaneously?

**Recommended Actions:**

1. **Identify or create 3–5 multi-condition rules** from the AIT P&P documents:
   - "A student must have a GPA ≥ 3.0, no outstanding fees, AND completed all required courses to graduate."
   - "Registration is permitted only for students who have paid tuition, submitted health records, AND been approved by their advisor."

2. **Demonstrate the translation** through all stages for these complex rules. Show how:
   - FOL handles conjunction: `∀x(Student(x) ∧ GPA(x) ≥ 3.0 ∧ ¬OutstandingFees(x) ∧ CompletedCourses(x) → CanGraduate(x))`
   - SHACL handles it with **multiple `sh:property` constraints** within a single shape, or with **`sh:and`** for complex logical combinations

3. **Run your TDD test suite** against these multi-condition shapes to prove they validate correctly.

4. **Discuss limitations honestly** — if there are rule types the framework can't handle yet (e.g., temporal constraints, counting/aggregation), acknowledge them as future work.

---

## 2. Dr. Jutiporn (CS204)

### 2.1 Researcher Bias (Sole Annotator Problem)

**Concern:** You are both the annotator and the verifier. High accuracy is likely biased.

**This is the most critical issue.** Recommended Actions:

1. **Recruit 2–3 independent annotators** to re-annotate a subset (at least 30–50 rules):
   - Ideal: Staff from AIT Registrar's Office (domain experts)
   - Alternative: Fellow CS graduate students who understand policy documents
   - Minimum: One person who is NOT you

2. **Compute Inter-Annotator Agreement (IAA):**
   - Cohen's Kappa (2 annotators) or Fleiss' Kappa (3+ annotators)
   - Report for both rule detection AND type classification tasks
   - You already have the `calculate_irr.py` and `calculate_kappa.py` scripts — extend them for external annotators

3. **Re-evaluate the gold standard:**
   - Use majority vote from all annotators as the new gold standard
   - Re-run your LLM evaluation against this consensus gold standard
   - Report the difference: "Self-annotated: 95.88%, Consensus-annotated: XX%"

4. **Acknowledge the limitation** even if you can't find annotators — add a "Threats to Validity" section discussing annotator bias.

---

### 2.2 Reproducibility ≠ Correctness

**Concern:** Running 10 times without syntax errors doesn't prove the logic is correct.

**Recommended Actions:**

1. **Clearly separate two claims in the thesis:**
   - **Syntactic Reproducibility** (what your 10-run test measures): "The system produces parseable SHACL output consistently"
   - **Semantic Correctness** (what your TDD tests measure): "The generated SHACL shapes enforce the intended policy constraints"

2. **Rename/reframe the reproducibility test:**
   - Call it "Output Stability Test" or "Syntactic Consistency Test"
   - Do NOT claim it proves correctness

3. **Strengthen the correctness argument** by pointing to your TDD test suite:
   - 81 positive validation tests (conforming data passes)
   - 66 negative validation tests (violating data fails)
   - 81 deontic differentiation tests (correct severity levels)
   - These are the real correctness evidence, not the 10-run reproducibility test

---

### 2.3 Misleading Metrics and Comparisons

**Concern:** 99% accuracy is "too perfect" and comparisons across different datasets are invalid.

**Recommended Actions:**

1. **Add confidence intervals and error bars** to ALL reported metrics (you already have `statistical_analysis.py` — make sure these appear in tables):
   - Rule Detection: 95.88% [90.1%–98.9%]
   - Type Classification: 75.9% [69.4%–86.5%]
   - Note: 75.9% type classification is a much more honest number than 99%

2. **Rewrite the comparison section:**
   - Do NOT say "our method achieves 99% vs. their 77%"
   - Instead, create a table that clearly shows differences:

   | Study | Task | Dataset | Size | Method | Metric |
   |---|---|---|---|---|---|
   | Breaux (2008) | NL→requirements | Privacy policies | 100+ | Manual | 82% |
   | This work | NL→FOL→SHACL | AIT P&P | 97 sentences | LLM+TDD | 95.88% |

   - Emphasize: "Direct numerical comparison is not possible due to different datasets, annotation schemes, and evaluation protocols. We include these numbers for contextual reference only."

3. **Report the HONEST numbers:**
   - Rule Detection Accuracy: **95.88%** (not 99%)
   - Type Classification: **75.9%** (this is your most honest metric)
   - Include the confusion matrix showing where mistakes happen

---

### 2.4 Ablation Study Clarification

**Concern:** Is testing "without prompt tuning" really an ablation study?

**Recommended Actions:**

1. **Reframe as "Prompt Engineering Impact Analysis"** rather than "Ablation Study":
   - An ablation study systematically removes components to measure their individual contribution
   - What you did is closer to: "What happens with a naive prompt vs. our engineered prompt?"

2. **If you want a TRUE ablation study**, test these variants:
   - Full pipeline (NL → FOL → SHACL) with all prompt engineering ✅ (your current best)
   - Remove few-shot examples → measure impact
   - Remove role prompting → measure impact
   - Remove deontic type definitions → measure impact
   - Each removal measures one component's contribution

3. **The permission experiment IS a good ablation example** — you showed improvement from 0% to 70% by adding explicit permission definitions. Frame this correctly.

---

### 2.5 External Validation

**Concern:** Get real-world stakeholders to verify the output.

**Recommended Actions:**

1. **Contact the AIT Registrar's Office:**
   - Prepare 10–15 rules with their SHACL translations (in plain language explanation)
   - Ask them: "Does this rule, as encoded, match what you enforce in practice?"
   - Create a simple questionnaire (Likert scale 1–5: "How accurately does this capture the rule?")
   - Even 1–2 responses from registrar staff would be valuable

2. **Prepare materials for non-technical reviewers:**
   - Don't show them raw SHACL/Turtle
   - Show: Original text → Plain language interpretation → Yes/No validation result
   - Ask: "Is this interpretation correct?"

3. **Document the feedback** regardless of outcome — if they find errors, that's actually valuable data for the thesis (shows where the system needs improvement).

---

## 3. Priority Action Items (Timeline to May)

| Priority | Action | Time Needed | Impact |
|---|---|---|---|
| 🔴 **Critical** | Recruit external annotators + compute IAA | 2–3 weeks | Addresses bias concern |
| 🔴 **Critical** | Rewrite metrics — honest numbers + CIs | 1 week | Fixes "misleading" criticism |
| 🟡 **High** | Contact AIT Registrar for validation | 2–4 weeks | External validation |
| 🟡 **High** | Create Translation Trace Table | 3–5 days | Shows meaning preservation |
| 🟡 **High** | Run NL→SHACL direct experiment | 1 week | Justifies FOL layer |
| 🟢 **Medium** | Multi-condition rule examples | 1 week | Demonstrates scalability |
| 🟢 **Medium** | Reframe ablation study + add variants | 1 week | Methodological rigor |
| 🟢 **Medium** | Concrete ABA ambiguity examples | 3–5 days | Clarifies the approach |
| 🔵 **Nice-to-have** | Full ABA implementation | 2+ weeks | Theoretical contribution |

---

## 4. Key Thesis Sections to Add/Revise

1. **New Section: "Threats to Validity"** — Address annotator bias, dataset limitations, generalizability
2. **Revise: Results tables** — Add confidence intervals, remove misleading comparisons
3. **Revise: Ablation study** — Reframe as "Prompt Engineering Impact Analysis" or add true component-removal tests
4. **New Section: "Translation Traceability"** — The stage-by-stage trace table
5. **New Section: "External Validation"** — Registrar office feedback (even if preliminary)
6. **Revise: Comparison with Related Work** — Qualify that comparisons are contextual, not direct

---

## 5. Email Template to Committee

> Subject: Summary of Committee Feedback — Thesis Improvement Plan
>
> Dear Prof. Attaphongse, Dr. Jutiporn, and Dr. Chaklam,
>
> Thank you for the valuable feedback during my thesis defense. Below is my summary of the key concerns raised, along with my proposed action plan:
>
> **Prof. Attaphongse:**
> 1. Meaning preservation → I will create translation trace tables showing NL→FOL→SHACL at each stage
> 2. FOL layer justification → I will run a direct NL→SHACL comparison experiment
> 3. Ambiguity handling → I will provide concrete ABA examples for "should" and "may" ambiguity
> 4. Scalability → I will demonstrate multi-condition policy translations
>
> **Dr. Jutiporn:**
> 1. Annotator bias → I will recruit 2–3 external annotators and compute inter-annotator agreement
> 2. Reproducibility vs. correctness → I will clearly separate syntactic stability from semantic correctness claims
> 3. Metrics → I will add confidence intervals and remove misleading cross-study comparisons
> 4. Ablation study → I will reframe as prompt engineering analysis with proper component-removal testing
> 5. External validation → I will seek verification from the AIT Registrar's Office
>
> I aim to complete these improvements by [target date] for the final defense.
>
> Best regards,
> Phongkrit
